from __future__ import annotations

from typing import Any, Dict, List

import yaml
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from ...deps import get_db_session

router = APIRouter(prefix="/v1/signals", tags=["signals"])


def _evaluate_rule(session: Session, rule: dict[str, Any]) -> List[dict[str, Any]]:
    kind = rule.get("kind")
    if kind == "stale_pr":
        hours = int(rule.get("older_than_hours", 48))
        sql = (
            "select delivery_id, min(received_at) as opened_at "
            "from events_raw where source='github' and event_type='pull_request' "
            "group by delivery_id having now() - min(received_at) > interval '%d hours'" % hours
        )
        rows = session.execute(text(sql)).mappings().all()
        return [dict(r) for r in rows]

    if kind == "wip_limit_exceeded":
        limit = int(rule.get("limit", 5))
        sql = (
            "select date_trunc('day', now()) as day, count(*) as wip "
            "from (select delivery_id, min(received_at) as opened_at from events_raw "
            "where source='github' and event_type='pull_request' group by delivery_id) o "
            "left join (select delivery_id, min(received_at) as closed_at from events_raw "
            "where source='github' and event_type='deployment_status' and payload like '%"
            "state"
            ": "
            "success"
            "%' group by delivery_id) c "
            "using (delivery_id) where c.closed_at is null"
        )
        row = session.execute(text(sql)).mappings().first()
        wip = int(row["wip"]) if row else 0
        return [{"day": str(row["day"]) if row else None, "wip": wip, "exceeded": wip > limit}]

    if kind == "no_ticket_link":
        # Detect PRs whose payload does not match a ticket pattern (very rough placeholder)
        pattern = rule.get("ticket_pattern", "[A-Z]+-[0-9]+")
        sql = (
            "select delivery_id, min(received_at) as opened_at from events_raw "
            "where source='github' and event_type='pull_request' and payload !~ :pattern "
            "group by delivery_id order by opened_at desc limit 200"
        )
        rows = session.execute(text(sql), {"pattern": pattern}).mappings().all()
        return [dict(r) for r in rows]

    if kind == "pr_without_review":
        hours = int(rule.get("older_than_hours", 12))
        sql = (
            "with prs as (select delivery_id, min(received_at) opened_at from events_raw "
            "where source='github' and event_type='pull_request' group by delivery_id), "
            "reviews as (select delivery_id, min(received_at) reviewed_at from events_raw "
            "where source='github' and event_type in ('pull_request_review','pull_request_review_comment') group by delivery_id) "
            "select prs.delivery_id, prs.opened_at from prs left join reviews using (delivery_id) "
            "where reviews.reviewed_at is null and now() - prs.opened_at > interval '%d hours'"
            % hours
        )
        rows = session.execute(text(sql)).mappings().all()
        return [dict(r) for r in rows]

    raise HTTPException(status_code=400, detail=f"unsupported rule kind: {kind}")


@router.post("/evaluate")
def evaluate_signals(
    body: Dict[str, Any], session: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    # Accept either JSON rules or a YAML string under { yaml: "..." }
    rules: List[dict[str, Any]]
    if "yaml" in body:
        rules = yaml.safe_load(body["yaml"]) or []
    else:
        rules = body.get("rules", [])

    results: Dict[str, Any] = {}
    for rule in rules:
        name = rule.get("name", rule.get("kind", "rule"))
        results[name] = _evaluate_rule(session, rule)
    return {"results": results}
