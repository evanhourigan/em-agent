from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any, Dict, List
from urllib.parse import parse_qs

from fastapi import APIRouter, Header, HTTPException, Request

from ....api.v1.routers.approvals import decide as approvals_decide
from ....api.v1.routers.reports import build_standup
from ....api.v1.routers.signals import _evaluate_rule
from ....core.config import get_settings
from ....db import get_sessionmaker
from ....models.approvals import Approval
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

    if text.startswith("signals"):
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

    if text.startswith("approvals"):
        # "approvals post [channel]" or just "approvals"
        if text.startswith("approvals post"):
            from ....services.slack_client import SlackClient

            parts = text.split()
            channel = parts[2] if len(parts) > 2 else None
            SessionLocal = get_sessionmaker()
            with SessionLocal() as session:
                rows = (
                    session.query(Approval)
                    .filter(Approval.status == "pending")
                    .order_by(Approval.id.desc())
                    .limit(10)
                    .all()
                )
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
        else:
            SessionLocal = get_sessionmaker()
            with SessionLocal() as session:
                rows = (
                    session.query(Approval)
                    .filter(Approval.status == "pending")
                    .order_by(Approval.id.desc())
                    .limit(10)
                    .all()
                )
                if not rows:
                    return {"ok": True, "message": "No pending approvals"}
                items = [f"#{a.id} {a.action} {a.subject}" for a in rows]
                return {"ok": True, "message": "; ".join(items)}

    if text.startswith("approve ") or text.startswith("decline "):
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
        from ....api.v1.routers.reports import build_standup
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
        try:
            import httpx

            with httpx.Client(timeout=30) as client:
                resp = client.post(
                    "http://localhost:8000/v1/agent/run", json={"query": query}
                )
                resp.raise_for_status()
                r = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc))
        steps = r.get("steps") or []
        return {"ok": True, "message": f"agent steps:{len(steps)} proposed:{'proposed_approval' in r}"}

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
    raise HTTPException(status_code=400, detail="unsupported interaction")
