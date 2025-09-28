from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/v1/policy", tags=["policy"])


@dataclass
class PolicyDecision:
    allow: bool
    reason: str


DEFAULT_POLICY = {
    "stale_pr": {"action": "nudge", "threshold_hours": 48},
    "wip_limit_exceeded": {"action": "escalate", "limit": 5},
    "no_ticket_link": {"action": "nudge"},
}


@router.post("/evaluate")
def evaluate_policy(payload: Dict[str, Any]) -> Dict[str, Any]:
    rule_kind = payload.get("kind")
    if not rule_kind:
        raise HTTPException(status_code=400, detail="missing kind")
    policy = DEFAULT_POLICY.get(rule_kind)
    if not policy:
        return {"allow": True, "reason": "no policy; allow by default"}
    action = policy.get("action", "nudge")
    return {"allow": action != "block", "action": action, "policy": policy}


