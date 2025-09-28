from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from ..api.v1.routers.policy import DEFAULT_POLICY
from ..api.v1.routers.signals import _evaluate_rule
from ..models.action_log import ActionLog
from ..core.logging import get_logger

DEFAULT_RULES: List[Dict[str, Any]] = [
    {"name": "stale48h", "kind": "stale_pr", "older_than_hours": 48},
    {"name": "wip_limit", "kind": "wip_limit_exceeded", "limit": 5},
    {"name": "pr_no_review", "kind": "pr_without_review", "older_than_hours": 12},
]


def evaluate_and_log(session: Session, rules: List[Dict[str, Any]] | None = None) -> int:
    rules = rules or DEFAULT_RULES
    inserted = 0
    for rule in rules:
        name = rule.get("name", rule.get("kind", "rule"))
        results = _evaluate_rule(session, rule)
        action = DEFAULT_POLICY.get(rule.get("kind"), {}).get("action", "nudge")
        for row in results:
            subject = str(row.get("delivery_id") or row)
            log = ActionLog(rule_name=name, subject=subject, action=action, payload=str(row))
            session.add(log)
            inserted += 1
    session.commit()
    return inserted


class EvaluatorThread(threading.Thread):
    def __init__(self, session_factory, interval_sec: int) -> None:
        super().__init__(daemon=True)
        self._session_factory = session_factory
        self._interval = interval_sec
        self._stop = threading.Event()
        self._logger = get_logger(__name__)

    def run(self) -> None:  # pragma: no cover - background loop
        while not self._stop.is_set():
            try:
                with self._session_factory() as session:
                    inserted = evaluate_and_log(session)
                    self._logger.info("evaluator.cycle_complete", inserted=inserted)
            except Exception as exc:
                # Keep loop alive; surface for observability
                self._logger.warning("evaluator.cycle_error", error=str(exc))
            self._stop.wait(self._interval)

    def stop(self) -> None:
        self._stop.set()


def maybe_start_evaluator(app, session_factory) -> EvaluatorThread | None:
    enabled = os.getenv("EVALUATOR_ENABLED", "false").lower() in {"1", "true", "yes"}
    if not enabled:
        return None
    interval = int(os.getenv("EVALUATOR_INTERVAL_SEC", "600"))
    t = EvaluatorThread(session_factory, interval)
    t.start()
    app.state.evaluator_thread = t
    get_logger(__name__).info("evaluator.started", interval_sec=interval)
    return t

