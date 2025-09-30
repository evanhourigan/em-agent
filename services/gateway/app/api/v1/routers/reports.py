from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ....api.v1.routers.signals import _evaluate_rule
from ....services.slack_client import SlackClient
from ...deps import get_db_session

router = APIRouter(prefix="/v1/reports", tags=["reports"])


def build_standup(session: Session, older_than_hours: int = 48) -> Dict[str, Any]:
    # Signals
    stale = _evaluate_rule(session, {"kind": "stale_pr", "older_than_hours": older_than_hours})
    wip_list = _evaluate_rule(session, {"kind": "wip_limit_exceeded"})
    pr_no_review = _evaluate_rule(session, {"kind": "pr_without_review", "older_than_hours": 12})

    # Deploys last 24h (successes)
    deploys_24h = session.execute(
        text(
            """
            select count(*) as c
            from events_raw
            where source='github'
              and event_type='deployment_status'
              and payload like '%"state": "success"%'
              and received_at > now() - interval '24 hours'
            """
        )
    ).scalar_one()

    # Compose summary
    top_stale = [str(x.get("delivery_id") or x) for x in stale[:5]]
    wip = int(wip_list[0]["wip"]) if wip_list and "wip" in wip_list[0] else len(wip_list)
    report = {
        "stale_pr_count": len(stale),
        "stale_pr_top": top_stale,
        "wip_open_prs": wip,
        "pr_without_review_count": len(pr_no_review),
        "deployments_last_24h": int(deploys_24h or 0),
    }
    return report


@router.post("/standup")
def standup(
    body: Dict[str, Any] | None = None, session: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    older = int((body or {}).get("older_than_hours", 48))
    return {"report": build_standup(session, older)}


@router.post("/standup/post")
def standup_post(
    body: Dict[str, Any] | None = None, session: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    older = int((body or {}).get("older_than_hours", 48))
    channel = (body or {}).get("channel")
    r = build_standup(session, older)
    text = "Daily Standup"
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "Daily Standup"}},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Stale PRs:* {r['stale_pr_count']}"},
                {"type": "mrkdwn", "text": f"*WIP:* {r['wip_open_prs']}"},
                {"type": "mrkdwn", "text": f"*No Review:* {r['pr_without_review_count']}"},
                {"type": "mrkdwn", "text": f"*Deploys 24h:* {r['deployments_last_24h']}"},
            ],
        },
    ]
    if r["stale_pr_top"]:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Top Stale:* " + ", ".join(r["stale_pr_top"]),
                },
            }
        )
    client = SlackClient()
    res = client.post_blocks(text=text, blocks=blocks, channel=channel)
    return {"posted": res}


def build_sprint_health(session: Session, days: int = 14) -> Dict[str, Any]:
    # Deployments in last N days and average per day
    total_deploys = session.execute(
        text(
            """
            select coalesce(sum(deployments), 0)
            from public.deployment_frequency
            where day >= current_date - :days::int
            """
        ),
        {"days": days},
    ).scalar_one()

    avg_daily_deploys = session.execute(
        text(
            """
            select coalesce(avg(deployments), 0)
            from public.deployment_frequency
            where day >= current_date - :days::int
            """
        ),
        {"days": days},
    ).scalar_one()

    # Change fail rate (average over window)
    avg_cfr = session.execute(
        text(
            """
            select coalesce(avg(change_fail_rate), 0)
            from public.change_fail_rate
            where day >= current_date - :days::int
            """
        ),
        {"days": days},
    ).scalar_one()

    # WIP (latest and average over window)
    latest_wip_row = (
        session.execute(text("select wip from public.wip order by day desc limit 1"))
        .mappings()
        .first()
    )
    latest_wip = int(latest_wip_row["wip"]) if latest_wip_row else 0
    avg_wip = session.execute(
        text(
            """
            select coalesce(avg(wip), 0)
            from public.wip
            where day >= current_date - :days::int
            """
        ),
        {"days": days},
    ).scalar_one()

    return {
        "window_days": days,
        "total_deploys": int(total_deploys or 0),
        "avg_daily_deploys": float(avg_daily_deploys or 0),
        "avg_change_fail_rate": float(avg_cfr or 0),
        "latest_wip": int(latest_wip),
        "avg_wip": float(avg_wip or 0),
    }


@router.post("/sprint-health")
def sprint_health(
    body: Dict[str, Any] | None = None, session: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    days = int((body or {}).get("days", 14))
    return {"report": build_sprint_health(session, days)}


@router.post("/sprint-health/post")
def sprint_health_post(
    body: Dict[str, Any] | None = None, session: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    days = int((body or {}).get("days", 14))
    channel = (body or {}).get("channel")
    r = build_sprint_health(session, days)
    text_lbl = "Sprint Health"
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": text_lbl}},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Window:* {r['window_days']} days"},
                {"type": "mrkdwn", "text": f"*Deploys:* {r['total_deploys']} (avg {r['avg_daily_deploys']:.2f}/day)"},
                {"type": "mrkdwn", "text": f"*CFR:* {r['avg_change_fail_rate']:.2f}"},
                {"type": "mrkdwn", "text": f"*WIP:* latest {r['latest_wip']} (avg {r['avg_wip']:.2f})"},
            ],
        },
    ]
    client = SlackClient()
    res = client.post_blocks(text=text_lbl, blocks=blocks, channel=channel)
    return {"posted": res}
