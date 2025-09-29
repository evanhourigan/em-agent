from __future__ import annotations

from typing import Any, Dict
from uuid import uuid4

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/v1/approvals", tags=["approvals"])

APPROVALS: Dict[str, Dict[str, Any]] = {}


@router.post("/propose")
def propose_action(payload: Dict[str, Any]) -> Dict[str, Any]:
    # Stub: echo back proposed action with a fake id
    if "action" not in payload:
        raise HTTPException(status_code=400, detail="missing action")
    action_id = f"appr-{uuid4().hex[:8]}"
    APPROVALS[action_id] = {"id": action_id, "status": "pending", "payload": payload}
    return {"action_id": action_id, "proposed": payload}


@router.get("/{id}")
def get_approval(id: str) -> Dict[str, Any]:
    data = APPROVALS.get(id)
    if not data:
        raise HTTPException(status_code=404, detail="not found")
    return data


@router.post("/{id}/decision")
def decide(id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    decision = payload.get("decision")
    if decision not in {"approve", "decline", "modify"}:
        raise HTTPException(status_code=400, detail="invalid decision")
    data = APPROVALS.get(id)
    if not data:
        raise HTTPException(status_code=404, detail="not found")
    data = {**data, "status": decision, "reason": payload.get("reason")}
    APPROVALS[id] = data
    return data

