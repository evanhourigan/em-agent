from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/v1/approvals", tags=["approvals"])


@router.post("/propose")
def propose_action(payload: Dict[str, Any]) -> Dict[str, Any]:
    # Stub: echo back proposed action with a fake id
    if "action" not in payload:
        raise HTTPException(status_code=400, detail="missing action")
    return {"action_id": "appr-1", "proposed": payload}


@router.get("/{id}")
def get_approval(id: str) -> Dict[str, Any]:
    return {"id": id, "status": "pending"}


@router.post("/{id}/decision")
def decide(id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    decision = payload.get("decision")
    if decision not in {"approve", "decline", "modify"}:
        raise HTTPException(status_code=400, detail="invalid decision")
    return {"id": id, "status": decision}


