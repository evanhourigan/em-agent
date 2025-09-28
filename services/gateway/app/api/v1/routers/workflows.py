from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...deps import get_db_session
from ...models.action_log import ActionLog

router = APIRouter(prefix="/v1/workflows", tags=["workflows"])


@router.post("/run")
def run_workflow(payload: Dict[str, Any], session: Session = Depends(get_db_session)) -> Dict[str, Any]:
    # Placeholder: log an action as a side effect
    rule = payload.get("rule", "manual")
    subject = payload.get("subject", "n/a")
    action = payload.get("action", "nudge")
    log = ActionLog(rule_name=rule, subject=subject, action=action, payload=str(payload))
    session.add(log)
    session.commit()
    return {"status": "queued", "id": log.id}


