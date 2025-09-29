from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ....api.v1.routers.policy import DEFAULT_POLICY
from ....api.v1.routers.approvals import propose_action
from ....models.action_log import ActionLog
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
        policy = DEFAULT_POLICY.get(kind)
        if not policy:
            action = "nudge"
        else:
            action = policy.get("action", "nudge")

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
    session.commit()
    return {"status": "queued", "id": log.id, "action": action}
