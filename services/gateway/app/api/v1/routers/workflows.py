from __future__ import annotations

from typing import Any, Dict, List

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ....api.v1.routers.approvals import propose_action
from ....api.v1.routers.policy import _load_policy
from ....core.config import get_settings
from ....models.action_log import ActionLog
from ....models.workflow_jobs import WorkflowJob
from ...deps import get_db_session

router = APIRouter(prefix="/v1/workflows", tags=["workflows"])


@router.post("/run")
def run_workflow(
    payload: Dict[str, Any], session: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    # Policy-gated execution: determine default action for a rule kind
    rule = payload.get("rule", payload.get("kind", "manual"))
    subject = payload.get("subject", "n/a")
    action = payload.get("action")
    if not action:
        kind = payload.get("kind", rule)
        settings = get_settings()
        # prefer OPA if configured
        if settings.opa_url:
            try:
                with httpx.Client(timeout=5) as client:
                    resp = client.post(
                        settings.opa_url.rstrip("/") + "/v1/data/em_agent/decision",
                        json={"input": {"kind": kind, **payload}},
                    )
                    resp.raise_for_status()
                    data = resp.json().get("result") or {}
                    action = data.get("action") or ("allow" if data.get("allow", True) else "block")
            except httpx.HTTPError:
                action = None
        if not action:
            policy = _load_policy().get(kind)
            action = (policy or {}).get("action", "nudge")

    if action == "block":
        # Instead of hard-failing, propose an approval for human decision
        proposal = {
            "subject": subject,
            "action": rule,
            "payload": payload,
            "reason": "blocked by policy",
        }
        res = propose_action(proposal)
        return {"status": "awaiting_approval", **res}
    log = ActionLog(rule_name=rule, subject=subject, action=action, payload=str(payload))
    session.add(log)
    session.add(
        WorkflowJob(
            status="queued",
            rule_kind=payload.get("kind", rule),
            subject=subject,
            payload=str(payload),
        )
    )
    session.commit()
    return {"status": "queued", "id": log.id, "action": action}


@router.get("/jobs")
def list_jobs(session: Session = Depends(get_db_session)) -> List[Dict[str, Any]]:
    rows = session.query(WorkflowJob).order_by(WorkflowJob.id.desc()).limit(100).all()
    return [
        {
            "id": j.id,
            "status": j.status,
            "rule_kind": j.rule_kind,
            "subject": j.subject,
        }
        for j in rows
    ]


@router.get("/jobs/{id}")
def get_job(id: int, session: Session = Depends(get_db_session)) -> Dict[str, Any]:
    j = session.get(WorkflowJob, id)
    if not j:
        raise HTTPException(status_code=404, detail="not found")
    return {
        "id": j.id,
        "status": j.status,
        "rule_kind": j.rule_kind,
        "subject": j.subject,
    }
