from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict

import yaml
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


def _load_policy() -> Dict[str, Any]:
    path = os.getenv("POLICY_PATH", "/app/app/config/policy.yml")
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                if isinstance(data, dict):
                    return data
    except Exception:
        pass
    return DEFAULT_POLICY


@router.post("/evaluate")
def evaluate_policy(payload: Dict[str, Any]) -> Dict[str, Any]:
    rule_kind = payload.get("kind")
    if not rule_kind:
        raise HTTPException(status_code=400, detail="missing kind")
    policy_map = _load_policy()
    policy = policy_map.get(rule_kind)
    if not policy:
        return {"allow": True, "reason": "no policy; allow by default"}
    action = policy.get("action", "nudge")
    return {"allow": action != "block", "action": action, "policy": policy}
