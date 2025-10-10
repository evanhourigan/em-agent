from __future__ import annotations

import time
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

from ....db import get_sessionmaker
from ....core.metrics import metrics as global_metrics
from .signals import _evaluate_rule


router = APIRouter(prefix="/v1/evals", tags=["evals"])


@router.post("/run")
def run_evals(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run a set of signal rules and return timing and counts.
    payload: { rules: [ {kind:..., ...}, ... ] }
    """
    rules: List[Dict[str, Any]] = payload.get("rules") or []
    if not isinstance(rules, list) or not rules:
        raise HTTPException(status_code=400, detail="rules required")
    SessionLocal = get_sessionmaker()
    results: Dict[str, Any] = {"ok": True, "evaluations": []}
    with SessionLocal() as session:
        for rule in rules:
            started = time.perf_counter()
            try:
                rows = _evaluate_rule(session, rule)
                elapsed = time.perf_counter() - started
                results["evaluations"].append(
                    {
                        "rule": rule,
                        "count": len(rows),
                        "elapsed_ms": int(elapsed * 1000),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                results["evaluations"].append(
                    {"rule": rule, "error": str(exc), "elapsed_ms": int((time.perf_counter() - started) * 1000)}
                )
    # Optionally emit metrics here later
    return results


