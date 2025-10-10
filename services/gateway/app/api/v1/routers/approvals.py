from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

router = APIRouter(prefix="/v1/approvals", tags=["approvals"])
from ....core.config import get_settings
from ....core.logging import get_logger
from ....core.metrics import metrics as global_metrics
from ....core.observability import add_prometheus
from ....db import get_sessionmaker
from ....models.approvals import Approval
from ....models.workflow_jobs import WorkflowJob
from ....models.action_log import ActionLog
from ....services.slack_client import SlackClient
from ....core.logging import get_logger
from ....services.temporal_client import get_temporal

logger = get_logger(__name__)


@router.get("")
def list_approvals() -> List[Dict[str, Any]]:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        rows = session.query(Approval).order_by(Approval.id.desc()).limit(100).all()
        return [
            {
                "id": a.id,
                "subject": a.subject,
                "action": a.action,
                "status": a.status,
                "reason": a.reason,
                "created_at": a.created_at.isoformat(),
                "decided_at": a.decided_at.isoformat() if a.decided_at else None,
            }
            for a in rows
        ]


@router.post("/propose")
def propose_action(payload: Dict[str, Any]) -> Dict[str, Any]:
    # Start span if OTel is enabled
    try:
        from opentelemetry import trace  # type: ignore

        span = trace.get_tracer(__name__).start_span("approvals.propose")
        span.set_attribute("action", payload.get("action", ""))
    except Exception:
        span = None
    if "action" not in payload:
        raise HTTPException(status_code=400, detail="missing action")
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        a = Approval(
            subject=payload.get("subject", "n/a"),
            action=payload["action"],
            status="pending",
            reason=payload.get("reason"),
            payload=__import__("json").dumps(payload.get("payload")),
        )
        session.add(a)
        session.commit()
        # Audit: record proposal
        try:
            session.add(
                ActionLog(
                    rule_name="approval.propose",
                    subject=a.subject,
                    action=a.action,
                    payload=a.payload,
                )
            )
            session.commit()
        except Exception:
            session.rollback()
        result = {"action_id": a.id, "proposed": payload}
        if span:
            try:
                span.end()
            except Exception:
                pass
        return result


@router.get("/{id}")
def get_approval(id: int) -> Dict[str, Any]:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        a = session.get(Approval, id)
        if not a:
            raise HTTPException(status_code=404, detail="not found")
        return {
            "id": a.id,
            "subject": a.subject,
            "action": a.action,
            "status": a.status,
            "reason": a.reason,
            "created_at": a.created_at.isoformat(),
            "decided_at": a.decided_at.isoformat() if a.decided_at else None,
        }


@router.post("/{id}/decision")
def decide(id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from opentelemetry import trace  # type: ignore

        span = trace.get_tracer(__name__).start_span("approvals.decide")
        span.set_attribute("approval.id", id)
        span.set_attribute("decision", payload.get("decision", ""))
    except Exception:
        span = None
    decision = payload.get("decision")
    if decision not in {"approve", "decline", "modify"}:
        raise HTTPException(status_code=400, detail="invalid decision")
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        a = session.get(Approval, id)
        if not a:
            raise HTTPException(status_code=404, detail="not found")
        a.status = decision
        a.reason = payload.get("reason")
        from datetime import datetime

        a.decided_at = datetime.utcnow()
        session.add(a)
        job_id = None
        # Determine prior policy suggested action (for override detection)
        suggested = None
        if decision == "approve":
            job = WorkflowJob(
                status="queued",
                rule_kind=a.action,
                subject=a.subject,
                payload=a.payload,
            )
            session.add(job)
            session.flush()  # populate job.id
            job_id = job.id
            # enqueue celery
            try:
                import redis

                r = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
                # naive enqueue via Celery's default redis queues
                r.lpush("celery", '{"id": "process_workflow_job", "args": [' + str(job_id) + '], "kwargs": {}, "retries": 0}')
            except Exception:
                pass
            # start Temporal workflow if available (best-effort)
            try:
                import asyncio
                from temporalio.client import Workflow

                async def _start():
                    client = await get_temporal().ensure()
                    if client:
                        await client.start_workflow(
                            "app.workers_temporal.app.worker.ProcessJobWorkflow",
                            job_id,
                            id=f"wf-job-{job_id}",
                            task_queue="workflow-jobs",
                        )
                asyncio.create_task(_start())
            except Exception:
                pass
        session.commit()
        # Audit: record decision and potential job enqueue
        try:
            session.add(
                ActionLog(
                    rule_name="approval.decision",
                    subject=a.subject,
                    action=decision,
                    payload=a.payload,
                )
            )
            session.commit()
        except Exception:
            session.rollback()
        # Metrics: decision counter and latency (if available)
        m = global_metrics
        if m:
            try:
                m["approvals_decisions_total"].labels(status=decision).inc()
                if a.created_at and a.decided_at:
                    latency = (a.decided_at - a.created_at).total_seconds()
                    m["approvals_latency_seconds"].observe(latency)
                # Override detection: if policy would not auto-approve and user approved, or vice versa
                # simple heuristic: if decision != "approve" then it's override of auto; if approve after block
                if decision != "approve":
                    m["approvals_override_total"].labels(**{"from": "auto", "to": decision}).inc()
                else:
                    m["approvals_override_total"].labels(**{"from": "block", "to": "approve"}).inc()
            except Exception:
                pass
        resp = {"id": a.id, "status": a.status, "reason": a.reason}
        if job_id is not None:
            resp["job_id"] = job_id
        if span:
            try:
                span.end()
            except Exception:
                pass
        return resp


@router.post("/{id}/notify")
def notify(id: int, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    channel = (payload or {}).get("channel")
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        a = session.get(Approval, id)
        if not a:
            raise HTTPException(status_code=404, detail="not found")
        text = f"Approval needed: {a.action} {a.subject}"
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": text}},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Approve"},
                        "style": "primary",
                        "value": f"approve:{a.id}",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Decline"},
                        "style": "danger",
                        "value": f"decline:{a.id}",
                    },
                ],
            },
        ]
        res = SlackClient().post_blocks(text=text, blocks=blocks, channel=channel)
        m = global_metrics
        if m:
            try:
                ok = bool(res.get("ok")) or bool(res.get("dry_run"))
                m["slack_posts_total"].labels(kind="approval", ok=str(ok).lower()).inc()
            except Exception:
                pass
        return {"ok": bool(res.get("ok")) or bool(res.get("dry_run")), "posted": res}
