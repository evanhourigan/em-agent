from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ....api.v1.routers.signals import _evaluate_rule
from ...deps import get_db_session


router = APIRouter(prefix="/v1/reports", tags=["reports"])


def build_standup(session: Session, older_than_hours: int = 48) -> Dict[str, Any]:
    # Signals
    stale = _evaluate_rule(session, {"kind": "stale_pr", "older_than_hours": older_than_hours})
    wip_list = _evaluate_rule(session, {"kind": "wip_limit_exceeded"})
    pr_no_review = _evaluate_rule(
        session, {"kind": "pr_without_review", "older_than_hours": 12}
    )

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


