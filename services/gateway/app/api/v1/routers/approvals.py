from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

router = APIRouter(prefix="/v1/approvals", tags=["approvals"])
from ....app import main as app_module  # type: ignore
from ....core.config import get_settings
from ....core.logging import get_logger
from ....core.observability import add_prometheus
from ....db import get_sessionmaker
from ....models.approvals import Approval
from ....models.workflow_jobs import WorkflowJob
from ....services.slack_client import SlackClient

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
    if "action" not in payload:
        raise HTTPException(status_code=400, detail="missing action")
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        a = Approval(
            subject=payload.get("subject", "n/a"),
            action=payload["action"],
            status="pending",
            reason=payload.get("reason"),
            payload=str(payload.get("payload")),
        )
        session.add(a)
        session.commit()
        return {"action_id": a.id, "proposed": payload}


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
        session.commit()
        # Metrics: decision counter and latency (if available)
        try:
            metrics = app_module.app.state.metrics  # type: ignore[attr-defined]
            if metrics:
                metrics["approvals_decisions_total"].labels(status=decision).inc()
                if a.created_at and a.decided_at:
                    latency = (a.decided_at - a.created_at).total_seconds()
                    metrics["approvals_latency_seconds"].observe(latency)
        except Exception:
            pass
        resp = {"id": a.id, "status": a.status, "reason": a.reason}
        if job_id is not None:
            resp["job_id"] = job_id
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
        try:
            metrics = app_module.app.state.metrics  # type: ignore[attr-defined]
            if metrics:
                ok = bool(res.get("ok")) or bool(res.get("dry_run"))
                metrics["slack_posts_total"].labels(kind="approval", ok=str(ok).lower()).inc()
        except Exception:
            pass
        return {"ok": bool(res.get("ok")) or bool(res.get("dry_run")), "posted": res}
