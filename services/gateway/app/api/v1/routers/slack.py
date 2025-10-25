from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any, Dict, List
from urllib.parse import parse_qs

from fastapi import APIRouter, Header, HTTPException, Request

from ....api.v1.routers.approvals import decide as approvals_decide
from ....api.v1.routers.approvals import propose_action as approvals_propose
from ....api.v1.routers.reports import build_standup
from ....api.v1.routers.signals import _evaluate_rule
from ....core.config import get_settings
from ....db import get_sessionmaker
from ....models.approvals import Approval
from ....models.incidents import Incident, IncidentTimeline
from ....models.workflow_jobs import WorkflowJob

router = APIRouter(prefix="/v1/slack", tags=["slack"])


def _verify_slack(request: Request, body: bytes, ts: str | None, sig: str | None) -> None:
    settings = get_settings()
    if not settings.slack_signing_required:
        return
    if not settings.slack_signing_secret:
        raise HTTPException(status_code=401, detail="slack signing secret not set")
    if not ts or not sig:
        raise HTTPException(status_code=401, detail="missing slack headers")
    try:
        ts_int = int(ts)
    except Exception:
        raise HTTPException(status_code=401, detail="bad timestamp")
    if abs(int(time.time()) - ts_int) > 60 * 5:
        raise HTTPException(status_code=401, detail="timestamp too old")
    basestring = f"v0:{ts}:{body.decode()}".encode()
    mac = hmac.new(settings.slack_signing_secret.encode(), basestring, hashlib.sha256)
    expected = f"v0={mac.hexdigest()}"
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(status_code=401, detail="invalid signature")


# Helper functions to reduce code duplication
def _make_http_request(url: str, method: str = "POST", json_data: Dict[str, Any] | None = None, timeout: int = 30) -> Dict[str, Any]:
    """Make HTTP request with consistent error handling."""
    import httpx
    try:
        with httpx.Client(timeout=timeout) as client:
            if method == "POST":
                resp = client.post(url, json=json_data or {})
            else:
                resp = client.get(url)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc))


def _get_pending_approvals(session, limit: int = 10) -> List[Approval]:
    """Get pending approvals from database."""
    return (
        session.query(Approval)
        .filter(Approval.status == "pending")
        .order_by(Approval.id.desc())
        .limit(limit)
        .all()
    )


# Command Handlers
def _handle_signals(text: str) -> Dict[str, Any]:
    """Handle 'signals' command."""
    parts = text.split()
    kinds: List[str]
    if len(parts) > 1:
        kinds = [parts[1]]
    else:
        kinds = ["stale_pr", "wip_limit_exceeded", "pr_without_review"]

    SessionLocal = get_sessionmaker()
    out: List[str] = []
    with SessionLocal() as session:
        for kind in kinds:
            try:
                results = _evaluate_rule(session, {"kind": kind})
            except HTTPException as exc:
                out.append(f"{kind}: error {exc.detail}")
                continue
            count = len(results)
            subjects = []
            for r in results[:5]:
                subj = str(r.get("delivery_id") or r.get("subject") or r)
                subjects.append(subj)
            out.append(f"{kind}: {count} found; top: {', '.join(subjects)}")
    return {"ok": True, "message": " | ".join(out)}


def _handle_approvals_list(text: str) -> Dict[str, Any]:
    """Handle 'approvals' command (list pending)."""
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        rows = _get_pending_approvals(session)
        if not rows:
            return {"ok": True, "message": "No pending approvals"}
        items = [f"#{a.id} {a.action} {a.subject}" for a in rows]
        return {"ok": True, "message": "; ".join(items)}


def _handle_approvals_post(text: str) -> Dict[str, Any]:
    """Handle 'approvals post' command."""
    from ....services.slack_client import SlackClient

    parts = text.split()
    channel = parts[2] if len(parts) > 2 else None
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        rows = _get_pending_approvals(session)
        if not rows:
            return {"ok": True, "message": "No pending approvals"}
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "Pending Approvals"},
            }
        ]
        for a in rows:
            blocks.extend(
                [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*#{a.id}* {a.action} — {a.subject}",
                        },
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "Approve"},
                                "style": "primary",
                                "value": f"approve:{a.id}",
                            },
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "Decline"},
                                "style": "danger",
                                "value": f"decline:{a.id}",
                            },
                        ],
                    },
                    {"type": "divider"},
                ]
            )
        res = SlackClient().post_blocks(
            text="Pending Approvals", blocks=blocks, channel=channel
        )
        return {"ok": True, "posted": res}


def _handle_approve_decline(text: str) -> Dict[str, Any]:
    """Handle 'approve <id>' or 'decline <id>' commands."""
    parts = text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        raise HTTPException(status_code=400, detail="usage: approve <id> | decline <id>")
    approval_id = int(parts[1])
    decision = "approve" if parts[0] == "approve" else "decline"
    res = approvals_decide(approval_id, {"decision": decision, "reason": "slack"})
    msg = f"approval #{approval_id} {res['status']}"
    if "job_id" in res:
        msg += f"; job_id={res['job_id']}"
    return {"ok": True, "message": msg}


@router.post("/commands")
async def commands(
    request: Request,
    x_slack_request_timestamp: str | None = Header(default=None),
    x_slack_signature: str | None = Header(default=None),
) -> Dict[str, Any]:
    raw = await request.body()
    _verify_slack(request, raw, x_slack_request_timestamp, x_slack_signature)
    content_type = request.headers.get("content-type", "")
    payload: Dict[str, Any]
    if "application/json" in content_type:
        try:
            payload = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            payload = {}
    else:
        form = parse_qs(raw.decode())
        payload = {k: v[0] for k, v in form.items()}
    text = (payload.get("text") or "").strip()
    if not text:
        return {
            "ok": True,
            "message": "Usage: signals [kind]|approvals|approve <id>|decline <id>",
        }

    # Dispatch to handler functions
    if text.startswith("signals"):
        return _handle_signals(text)

    if text.startswith("approvals post"):
        return _handle_approvals_post(text)

    if text.startswith("approvals"):
        return _handle_approvals_list(text)

    if text.startswith("approve ") or text.startswith("decline "):
        return _handle_approve_decline(text)

    # Continue with remaining inline handlers

    if text.startswith("standup"):
        parts = text.split()
        older = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 48
        SessionLocal = get_sessionmaker()
        with SessionLocal() as session:
            r = build_standup(session, older)
            msg = (
                f"stale_prs:{r['stale_pr_count']} top:{', '.join(r['stale_pr_top'])} | "
                f"wip:{r['wip_open_prs']} | pr_no_review:{r['pr_without_review_count']} | "
                f"deploys_24h:{r['deployments_last_24h']}"
            )
            return {"ok": True, "message": msg}

    if text.startswith("triage post") or text.startswith("triage"):
        # Summarize triage items using existing signal evaluation helpers
        parts = text.split()
        channel = None
        if text.startswith("triage post"):
            channel = parts[2] if len(parts) > 2 else None
        SessionLocal = get_sessionmaker()
        with SessionLocal() as session:
            try:
                stale = _evaluate_rule(session, {"kind": "stale_pr", "older_than_hours": 48})
                no_review = _evaluate_rule(
                    session, {"kind": "pr_without_review", "older_than_hours": 12}
                )
            except HTTPException as exc:
                return {"ok": False, "message": f"error: {exc.detail}"}
            top_stale = [str(x.get("delivery_id") or x) for x in stale[:5]]
            top_no_review = [str(x.get("delivery_id") or x) for x in no_review[:5]]
            msg = (
                f"triage: stale_prs:{len(stale)} top:{', '.join(top_stale)} | "
                f"no_review:{len(no_review)} top:{', '.join(top_no_review)}"
            )
            if text.startswith("triage post"):
                from ....services.slack_client import SlackClient

                blocks = [
                    {"type": "header", "text": {"type": "plain_text", "text": "Triage"}},
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*Stale PRs:* {len(stale)}"},
                            {"type": "mrkdwn", "text": f"*No Review:* {len(no_review)}"},
                        ],
                    },
                ]
                if top_stale:
                    blocks.append(
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "*Top Stale:* " + ", ".join(top_stale),
                            },
                        }
                    )
                if top_no_review:
                    blocks.append(
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "*Needs Review:* " + ", ".join(top_no_review),
                            },
                        }
                    )
                res = SlackClient().post_blocks(text="Triage", blocks=blocks, channel=channel)
                return {"ok": True, "posted": res}
            return {"ok": True, "message": msg}

    if text.startswith("standup post"):
        parts = text.split()
        channel = parts[2] if len(parts) > 2 else None
        older = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 48
        from ....services.slack_client import SlackClient

        SessionLocal = get_sessionmaker()
        with SessionLocal() as session:
            r = build_standup(session, older)
            msg = (
                f"Standup: stale_prs:{r['stale_pr_count']} top:{', '.join(r['stale_pr_top'])} | "
                f"wip:{r['wip_open_prs']} | pr_no_review:{r['pr_without_review_count']} | "
                f"deploys_24h:{r['deployments_last_24h']}"
            )
            res = SlackClient().post_text(msg, channel=channel)
            return {"ok": True, "posted": res}

    if text.startswith("sprint post"):
        parts = text.split()
        channel = parts[2] if len(parts) > 2 else None
        days = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 14
        from ....api.v1.routers.reports import build_sprint_health
        from ....services.slack_client import SlackClient

        SessionLocal = get_sessionmaker()
        with SessionLocal() as session:
            r = build_sprint_health(session, days)
            msg = (
                f"Sprint Health: window {r['window_days']}d | "
                f"deploys:{r['total_deploys']} avg/day:{r['avg_daily_deploys']:.2f} | "
                f"CFR:{r['avg_change_fail_rate']:.2f} | WIP latest:{r['latest_wip']} avg:{r['avg_wip']:.2f}"
            )
            res = SlackClient().post_text(msg, channel=channel)
            return {"ok": True, "posted": res}

    if text.startswith("sprint"):
        parts = text.split()
        days = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 14
        from ....api.v1.routers.reports import build_sprint_health

        SessionLocal = get_sessionmaker()
        with SessionLocal() as session:
            r = build_sprint_health(session, days)
            msg = (
                f"sprint[{r['window_days']}d] deploys:{r['total_deploys']} avg/day:{r['avg_daily_deploys']:.2f} | "
                f"CFR:{r['avg_change_fail_rate']:.2f} | WIP latest:{r['latest_wip']} avg:{r['avg_wip']:.2f}"
            )
            return {"ok": True, "message": msg}

    if text.startswith("agent "):
        query = text[len("agent ") :].strip()
        if not query:
            return {"ok": False, "message": "usage: agent <query>"}
        r = _make_http_request("http://localhost:8000/v1/agent/run", json_data={"query": query}, timeout=30)
        plan = r.get("plan") or []
        result = r.get("result") or {}
        msg = f"agent plan:{[p.get('tool') for p in plan]}"
        if "results" in result:
            msg += f" | results:{len(result['results'])}"
        return {"ok": True, "message": msg}

    if text.startswith("incident start"):
        title = text[len("incident start"):].strip() or "Untitled Incident"
        inc = _make_http_request("http://localhost:8000/v1/incidents", json_data={"title": title}, timeout=10)
        return {"ok": True, "message": f"incident #{inc.get('id')} started: {title}"}

    if text.startswith("incident note "):
        parts = text.split(maxsplit=3)
        if len(parts) < 4 or not parts[2].isdigit():
            return {"ok": False, "message": "usage: incident note <id> <text>"}
        inc_id = int(parts[2])
        note = parts[3]
        _make_http_request(f"http://localhost:8000/v1/incidents/{inc_id}/note", json_data={"text": note}, timeout=10)
        return {"ok": True, "message": f"noted on incident #{inc_id}"}

    if text.startswith("incident post"):
        # usage: incident post <id> [#channel]
        parts = text.split()
        if len(parts) < 3 or not parts[2].isdigit():
            return {"ok": False, "message": "usage: incident post <id> [#channel]"}
        inc_id = int(parts[2])
        channel = parts[3] if len(parts) > 3 and parts[3].startswith("#") else None
        SessionLocal = get_sessionmaker()
        with SessionLocal() as session:
            inc = session.get(Incident, inc_id)
            if not inc:
                raise HTTPException(status_code=404, detail="incident not found")
            rows = (
                session.query(IncidentTimeline)
                .filter(IncidentTimeline.incident_id == inc_id)
                .order_by(IncidentTimeline.ts.asc())
                .all()
            )
        from ....services.slack_client import SlackClient

        blocks: List[Dict[str, Any]] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"Incident #{inc_id} — {inc.title}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Status:* {inc.status}"},
                    {"type": "mrkdwn", "text": f"*Severity:* {inc.severity or '-'}"},
                ],
            },
            {"type": "divider"},
        ]
        for tl in rows[-10:]:
            ts = tl.ts.isoformat() if hasattr(tl.ts, "isoformat") else str(tl.ts)
            who = f" by {tl.author}" if tl.author else ""
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{ts}*{who}: {tl.text}",
                    },
                }
            )
        res = SlackClient().post_blocks(text=f"Incident #{inc_id}", blocks=blocks, channel=channel)
        return {"ok": True, "posted": res}

    if text.startswith("incident close "):
        parts = text.split(maxsplit=2)
        if len(parts) < 3 or not parts[2].isdigit():
            return {"ok": False, "message": "usage: incident close <id>"}
        inc_id = int(parts[2])
        _make_http_request(f"http://localhost:8000/v1/incidents/{inc_id}/close", timeout=10)
        return {"ok": True, "message": f"incident #{inc_id} closed"}

    if text.startswith("incident sev "):
        # usage: incident sev <id> <S0|S1|S2|S3>
        parts = text.split(maxsplit=3)
        if len(parts) < 4 or not parts[2].isdigit():
            return {"ok": False, "message": "usage: incident sev <id> <S0|S1|S2|S3>"}
        inc_id = int(parts[2])
        sev = parts[3]
        _make_http_request(f"http://localhost:8000/v1/incidents/{inc_id}/severity", json_data={"severity": sev}, timeout=10)
        return {"ok": True, "message": f"incident #{inc_id} severity -> {sev}"}

    if text.startswith("onboarding plan "):
        # usage: onboarding plan <title>
        title = text[len("onboarding plan "):].strip() or "New Hire Plan"
        plan = _make_http_request("http://localhost:8000/v1/onboarding/plans", json_data={"title": title}, timeout=10)
        return {"ok": True, "message": f"onboarding plan #{plan.get('id')} created"}

    if text.startswith("onboarding task "):
        # usage: onboarding task <plan_id> <title>
        parts = text.split(maxsplit=3)
        if len(parts) < 4 or not parts[2].isdigit():
            return {"ok": False, "message": "usage: onboarding task <plan_id> <title>"}
        pid = int(parts[2])
        t = parts[3]
        _make_http_request(f"http://localhost:8000/v1/onboarding/plans/{pid}/tasks", json_data={"title": t}, timeout=10)
        return {"ok": True, "message": f"task added to plan #{pid}"}

    if text.startswith("okr new "):
        # usage: okr new <title>
        title = text[len("okr new "):].strip()
        if not title:
            return {"ok": False, "message": "usage: okr new <title>"}
        obj = _make_http_request("http://localhost:8000/v1/okr/objectives", json_data={"title": title}, timeout=10)
        return {"ok": True, "message": f"objective #{obj.get('id')} created"}

    if text.startswith("okr kr "):
        # usage: okr kr <objective_id> <title>
        parts = text.split(maxsplit=3)
        if len(parts) < 4 or not parts[2].isdigit():
            return {"ok": False, "message": "usage: okr kr <objective_id> <title>"}
        oid = int(parts[2])
        krt = parts[3]
        _make_http_request(f"http://localhost:8000/v1/okr/objectives/{oid}/krs", json_data={"title": krt}, timeout=10)
        return {"ok": True, "message": f"kr added to objective #{oid}"}

    if text.strip().startswith("agent label-missing-ticket"):
        # Trigger agent flow to propose labeling PRs without ticket links
        r = _make_http_request("http://localhost:8000/v1/agent/run", json_data={"query": "label missing ticket PRs"}, timeout=30)
        prop = r.get("proposed") or {}
        action_id = prop.get("action_id")
        candidates = r.get("candidates")
        if not action_id:
            return {"ok": False, "message": "agent proposal failed"}
        return {
            "ok": True,
            "message": f"proposed approval #{action_id} for label needs-ticket; candidates:{candidates}",
        }

    if text.strip().startswith("agent create-missing-ticket-issues"):
        r = _make_http_request("http://localhost:8000/v1/agent/run", json_data={"query": "create issues for missing ticket links"}, timeout=30)
        prop = r.get("proposed") or {}
        action_id = prop.get("action_id")
        candidates = r.get("candidates")
        if not action_id:
            return {"ok": False, "message": "agent proposal failed"}
        return {
            "ok": True,
            "message": f"proposed approval #{action_id} to create issues; candidates:{candidates}",
        }

    if text.startswith("agent assign-reviewers"):
        # syntax: agent assign-reviewers <reviewer> [older_than_hours]
        parts = text.split()
        reviewer = parts[2] if len(parts) > 2 else None
        older = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 12
        if not reviewer:
            return {"ok": False, "message": "usage: agent assign-reviewers <reviewer> [older_than_hours]"}
        rules = [{"kind": "pr_without_review", "older_than_hours": older}]
        SessionLocal = get_sessionmaker()
        with SessionLocal() as session:
            try:
                no_review = _evaluate_rule(session, rules[0])
            except HTTPException as exc:
                return {"ok": False, "message": f"error: {exc.detail}"}
        targets = [str(r.get("delivery_id") or r) for r in no_review[:20]]
        approval = {
            "subject": "pr:assign_reviewer",
            "action": "assign_reviewer",
            "reason": "Slack command to assign reviewers",
            "payload": {"reviewer": reviewer, "targets": targets},
        }
        from ....api.v1.routers.approvals import propose_action as approvals_propose

        res = approvals_propose(approval)
        return {"ok": True, "proposed": res, "candidates": len(targets)}

    if text.startswith("agent triage post"):
        parts = text.split()
        channel = parts[3] if len(parts) > 3 and parts[2] == "post" and parts[3].startswith("#") else None
        SessionLocal = get_sessionmaker()
        with SessionLocal() as session:
            try:
                stale = _evaluate_rule(session, {"kind": "stale_pr", "older_than_hours": 48})
                no_review = _evaluate_rule(
                    session, {"kind": "pr_without_review", "older_than_hours": 12}
                )
            except HTTPException as exc:
                return {"ok": False, "message": f"error: {exc.detail}"}
        from ....services.slack_client import SlackClient

        blocks: List[Dict[str, Any]] = [
            {"type": "header", "text": {"type": "plain_text", "text": "Agent Triage"}},
        ]
        if stale:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Stale PRs (>48h):* {len(stale)}",
                    },
                }
            )
            for r in stale[:5]:
                subj = str(r.get("delivery_id") or r)
                blocks.extend(
                    [
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": subj},
                        },
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {"type": "plain_text", "text": "Propose Nudge"},
                                    "value": f"propose:nudge:{subj}",
                                }
                            ],
                        },
                    ]
                )
        if no_review:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*PRs Without Review (>12h):* {len(no_review)}",
                    },
                }
            )
            for r in no_review[:5]:
                subj = str(r.get("delivery_id") or r)
                blocks.extend(
                    [
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": subj},
                        },
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {"type": "plain_text", "text": "Propose Nudge"},
                                    "value": f"propose:nudge:{subj}",
                                }
                            ],
                        },
                    ]
                )
        res = SlackClient().post_blocks(text="Agent Triage", blocks=blocks, channel=channel)
        return {"ok": True, "posted": res}

    if text.startswith("agent ask ") or text.startswith("agent ask post"):
        parts = text.split()
        channel = None
        if text.startswith("agent ask post"):
            if len(parts) >= 4 and parts[3].startswith("#"):
                channel = parts[3]
                query = " ".join(parts[4:])
            else:
                query = " ".join(parts[3:])
        else:
            query = " ".join(parts[2:])
        query = query.strip()
        if not query:
            return {"ok": False, "message": "usage: agent ask <query> | agent ask post [channel] <query>"}
        # Use existing ask pathway to get results
        data = _make_http_request("http://localhost:8000/v1/rag/search", json_data={"q": query, "top_k": 3}, timeout=15)
        results = data.get("results") or []
        if not results:
            return {"ok": True, "message": "No results"}
        from ....services.slack_client import SlackClient

        blocks: List[Dict[str, Any]] = [
            {"type": "header", "text": {"type": "plain_text", "text": "Agent Ask"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Query:* {query}"}},
        ]
        for r in results[:3]:
            title = r.get("id") or r.get("parent_id") or "doc"
            snippet = (r.get("snippet") or "").strip()
            target = r.get("meta", {}).get("url") or title
            blocks.extend(
                [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*{title}*\n{snippet[:300]}"},
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "Propose Nudge"},
                                "value": f"propose:nudge:{target}",
                            },
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "Open"},
                                "url": target if isinstance(target, str) and target.startswith("http") else None,
                            },
                        ],
                    },
                ]
            )
        res = SlackClient().post_blocks(text="Agent Ask", blocks=blocks, channel=channel)
        return {"ok": True, "posted": res}

    # ask: query RAG and summarize top results
    if text.startswith("ask post") or text.startswith("ask "):
        parts = text.split()
        channel = None
        query = ""
        if text.startswith("ask post"):
            # format: ask post [channel] <query...>
            if len(parts) >= 3 and parts[2].startswith("#"):
                channel = parts[2]
                query = " ".join(parts[3:])
            else:
                query = " ".join(parts[2:])
        else:
            query = " ".join(parts[1:])
        query = query.strip()
        if not query:
            raise HTTPException(
                status_code=400, detail="usage: ask <query> | ask post [channel] <query>"
            )

        # call RAG through gateway proxy
        try:
            import httpx

            from ....core.config import get_settings

            gateway_base = ""  # same service
            with httpx.Client(timeout=15) as client:
                resp = client.post(
                    f"http://localhost:8000/v1/rag/search", json={"q": query, "top_k": 3}
                )
                # When running inside container, localhost resolves; if behind proxy, router handles it
                if resp.status_code >= 400:
                    # fallback to internal include
                    from ....api.v1.routers.rag import proxy_search  # type: ignore

                    data = proxy_search({"q": query, "top_k": 3})
                else:
                    data = resp.json()
        except Exception:
            # final fallback
            from ....api.v1.routers.rag import proxy_search  # type: ignore

            data = proxy_search({"q": query, "top_k": 3})

        results = data.get("results") or []
        if not results:
            return {"ok": True, "message": "No results"}
        lines = []
        for r in results[:3]:
            title = r.get("id") or r.get("parent_id") or "doc"
            snippet = (r.get("snippet") or "").strip().replace("\n", " ")
            score = r.get("score")
            lines.append(f"• {title} (score {score:.3f}): {snippet[:180]}")
        msg = f"Results for: {query}\n" + "\n".join(lines)
        if text.startswith("ask post"):
            from ....services.slack_client import SlackClient

            blocks = [
                {"type": "header", "text": {"type": "plain_text", "text": "Ask"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": f"*Query:* {query}"}},
            ]
            for r in results[:3]:
                title = r.get("id") or r.get("parent_id") or "doc"
                snippet = (r.get("snippet") or "").strip()
                blocks.append(
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{title}*\n{snippet[:300]}",
                        },
                    }
                )
                blocks.append({"type": "divider"})
            res = SlackClient().post_blocks(text="Ask", blocks=blocks, channel=channel)
            return {"ok": True, "posted": res}
        return {"ok": True, "message": msg}

    return {
        "ok": True,
        "message": "Usage: signals [kind]|approvals|approve <id>|decline <id>",
    }


@router.post("/interactions")
async def interactions(
    request: Request,
    x_slack_request_timestamp: str | None = Header(default=None),
    x_slack_signature: str | None = Header(default=None),
) -> Dict[str, Any]:
    raw = await request.body()
    _verify_slack(request, raw, x_slack_request_timestamp, x_slack_signature)
    content_type = request.headers.get("content-type", "")
    payload: Dict[str, Any]
    if "application/json" in content_type:
        try:
            payload = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            payload = {}
    else:
        form = parse_qs(raw.decode())
        if "payload" in form:
            try:
                payload = json.loads(form["payload"][0])
            except Exception:
                payload = {}
            # button actions payload: route approve/decline
            actions = payload.get("actions") or []
            if actions and isinstance(actions, list):
                val = actions[0].get("value")
                if isinstance(val, str) and ":" in val:
                    verb, ident = val.split(":", 1)
                    if verb in {"approve", "decline"} and ident.isdigit():
                        payload = {
                            "action": "approval-decision",
                            "id": int(ident),
                            "decision": "approve" if verb == "approve" else "decline",
                        }
                    elif verb == "propose" and ":" in ident:
                        # propose:<kind>:<target>
                        kind, target = ident.split(":", 1)
                        payload = {
                            "action": "approval-propose",
                            "kind": kind,
                            "target": target,
                        }
        else:
            payload = {k: v[0] for k, v in form.items()}
    action = payload.get("action")
    if action == "approve-job":
        job_id = int(payload.get("job_id"))
        SessionLocal = get_sessionmaker()
        with SessionLocal() as session:
            job = session.get(WorkflowJob, job_id)
            if not job:
                raise HTTPException(status_code=404, detail="job not found")
            job.status = "queued"
            session.add(job)
            session.commit()
            return {"ok": True, "message": f"Job {job_id} queued"}
    if action == "approval-decision":
        approval_id = int(payload.get("id"))
        decision = payload.get("decision")
        if decision not in {"approve", "decline", "modify"}:
            raise HTTPException(status_code=400, detail="invalid decision")
        res = approvals_decide(approval_id, {"decision": decision, "reason": "slack"})
        return {"ok": True, "result": res}
    if action == "approval-propose":
        kind = payload.get("kind") or "nudge"
        target = payload.get("target") or "n/a"
        if kind not in {"nudge", "label"}:
            raise HTTPException(status_code=400, detail="unsupported propose kind")
        # create approval
        data = {
            "subject": f"slack:{kind}",
            "action": kind,
            "reason": "Slack propose",
            "payload": {"targets": [target]},
        }
        try:
            res = approvals_propose(data)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc))
        return {"ok": True, "proposed": res}
    raise HTTPException(status_code=400, detail="unsupported interaction")
