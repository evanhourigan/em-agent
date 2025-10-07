from __future__ import annotations

import os
import threading
import time

from sqlalchemy.orm import Session

from ..core.logging import get_logger
from ..models.workflow_jobs import WorkflowJob


class WorkflowRunner(threading.Thread):
    def __init__(self, session_factory, interval_sec: int = 10) -> None:
        super().__init__(daemon=True)
        self._session_factory = session_factory
        self._interval = interval_sec
        self._stop = threading.Event()
        self._logger = get_logger(__name__)

    def run(self) -> None:  # pragma: no cover
        while not self._stop.is_set():
            try:
                with self._session_factory() as session:
                    self._process_batch(session)
            except Exception as exc:
                self._logger.warning("workflow_runner.error", error=str(exc))
            self._stop.wait(self._interval)

    def stop(self) -> None:
        self._stop.set()

    def _process_batch(self, session: Session) -> None:
        jobs = (
            session.query(WorkflowJob)
            .filter(WorkflowJob.status == "queued")
            .order_by(WorkflowJob.id.asc())
            .limit(25)
            .all()
        )
        processed = 0
        for job in jobs:
            # Start a span per job if tracing enabled
            try:
                from opentelemetry import trace  # type: ignore

                span = trace.get_tracer(__name__).start_span("workflow.process")
                span.set_attribute("workflow.job_id", job.id)
                span.set_attribute("workflow.rule_kind", job.rule_kind or "")
            except Exception:
                span = None

            job.status = "done"
            processed += 1
            if span:
                try:
                    span.end()
                except Exception:
                    pass
        if processed:
            session.commit()
            self._logger.info("workflow_runner.processed", count=processed)


def maybe_start_workflow_runner(app, session_factory) -> WorkflowRunner | None:
    enabled = os.getenv("WORKFLOW_RUNNER_ENABLED", "true").lower() in {"1", "true", "yes"}
    if not enabled:
        return None
    interval = int(os.getenv("WORKFLOW_RUNNER_INTERVAL_SEC", "10"))
    t = WorkflowRunner(session_factory, interval)
    t.start()
    app.state.workflow_runner_thread = t
    get_logger(__name__).info("workflow_runner.started", interval_sec=interval)
    return t


def maybe_stop_workflow_runner(app) -> None:
    t = getattr(app.state, "workflow_runner_thread", None)
    if t is not None:
        try:
            t.stop()
        except Exception:
            pass
