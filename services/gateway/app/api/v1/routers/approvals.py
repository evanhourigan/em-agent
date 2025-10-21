"""
Approvals router with proper error handling and input validation.

This module handles the Human-in-the-Loop (HITL) approval workflow:
- Proposing actions for approval
- Making decisions on approvals
- Notifying stakeholders via Slack
"""
from __future__ import annotations

import json
import os
from typing import List
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import IntegrityError, OperationalError

from ....core.config import get_settings
from ....core.logging import get_logger
from ....core.metrics import metrics as global_metrics
from ....db import get_sessionmaker
from ....models.approvals import Approval
from ....models.workflow_jobs import WorkflowJob
from ....models.action_log import ActionLog
from ....services.slack_client import SlackClient
from ....services.temporal_client import get_temporal
from ....schemas.approvals import (
    ApprovalProposalRequest,
    ApprovalProposalResponse,
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ApprovalNotifyRequest,
    ApprovalNotifyResponse,
    ApprovalResponse,
)

router = APIRouter(prefix="/v1/approvals", tags=["approvals"])
logger = get_logger(__name__)


@router.get("", response_model=List[ApprovalResponse])
def list_approvals() -> List[ApprovalResponse]:
    """
    List recent approvals, ordered by most recent first.

    Returns up to 100 most recent approvals.
    """
    try:
        SessionLocal = get_sessionmaker()
        with SessionLocal() as session:
            rows = session.query(Approval).order_by(Approval.id.desc()).limit(100).all()
            return [ApprovalResponse.model_validate(a) for a in rows]
    except OperationalError as e:
        logger.error("approval.list.db_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable"
        )
    except Exception as e:
        logger.error("approval.list.unexpected_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post("/propose", response_model=ApprovalProposalResponse)
def propose_action(payload: ApprovalProposalRequest) -> ApprovalProposalResponse:
    """
    Propose an action for approval.

    Creates a new approval request that will be in 'pending' status
    until a decision is made.
    """
    # Start span if OTel is enabled
    span = None
    try:
        from opentelemetry import trace  # type: ignore
        tracer = trace.get_tracer(__name__)
        span = tracer.start_span("approvals.propose")
        span.set_attribute("action", payload.action)
        span.set_attribute("subject", payload.subject)
    except Exception as e:
        logger.debug("approval.propose.tracing_unavailable", error=str(e))

    try:
        SessionLocal = get_sessionmaker()
        with SessionLocal() as session:
            # Create approval record
            a = Approval(
                subject=payload.subject,
                action=payload.action,
                status="pending",
                reason=payload.reason,
                payload=json.dumps(payload.payload) if payload.payload else None,
            )
            session.add(a)
            session.commit()
            session.refresh(a)  # Get the ID

            logger.info(
                "approval.proposed",
                approval_id=a.id,
                action=a.action,
                subject=a.subject
            )

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
            except Exception as e:
                logger.warning(
                    "approval.propose.audit_failed",
                    error=str(e),
                    approval_id=a.id
                )
                # Don't fail the whole request if audit logging fails
                session.rollback()

            result = ApprovalProposalResponse(
                action_id=a.id,
                proposed=payload
            )

            if span:
                try:
                    span.end()
                except Exception:
                    pass

            return result

    except IntegrityError as e:
        logger.error("approval.propose.integrity_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate approval request or constraint violation"
        )
    except OperationalError as e:
        logger.error("approval.propose.db_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable"
        )
    except Exception as e:
        logger.error("approval.propose.unexpected_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get("/{id}", response_model=ApprovalResponse)
def get_approval(id: int) -> ApprovalResponse:
    """
    Get a specific approval by ID.

    Args:
        id: The approval ID

    Returns:
        The approval details

    Raises:
        404: If approval not found
    """
    try:
        SessionLocal = get_sessionmaker()
        with SessionLocal() as session:
            a = session.get(Approval, id)
            if not a:
                logger.warning("approval.get.not_found", approval_id=id)
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Approval {id} not found"
                )
            return ApprovalResponse.model_validate(a)
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except OperationalError as e:
        logger.error("approval.get.db_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable"
        )
    except Exception as e:
        logger.error("approval.get.unexpected_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post("/{id}/decision", response_model=ApprovalDecisionResponse)
def decide(id: int, payload: ApprovalDecisionRequest) -> ApprovalDecisionResponse:
    """
    Make a decision on an approval.

    Args:
        id: The approval ID
        payload: The decision (approve/decline/modify) and optional reason

    Returns:
        The updated approval status and job ID if created

    Raises:
        404: If approval not found
    """
    # Start span if OTel is enabled
    span = None
    try:
        from opentelemetry import trace  # type: ignore
        tracer = trace.get_tracer(__name__)
        span = tracer.start_span("approvals.decide")
        span.set_attribute("approval.id", id)
        span.set_attribute("decision", payload.decision)
    except Exception as e:
        logger.debug("approval.decide.tracing_unavailable", error=str(e))

    try:
        SessionLocal = get_sessionmaker()
        with SessionLocal() as session:
            a = session.get(Approval, id)
            if not a:
                logger.warning("approval.decide.not_found", approval_id=id)
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Approval {id} not found"
                )

            # Update approval
            a.status = payload.decision
            a.reason = payload.reason
            a.decided_at = datetime.utcnow()
            session.add(a)

            job_id = None

            # If approved, create workflow job
            if payload.decision == "approve":
                job = WorkflowJob(
                    status="queued",
                    rule_kind=a.action,
                    subject=a.subject,
                    payload=a.payload,
                )
                session.add(job)
                session.flush()  # Populate job.id
                job_id = job.id

                logger.info(
                    "approval.workflow_job_created",
                    approval_id=a.id,
                    job_id=job_id,
                    action=a.action
                )

                # Enqueue to Celery (best-effort)
                try:
                    import redis
                    r = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
                    celery_task = {
                        "id": "process_workflow_job",
                        "args": [job_id],
                        "kwargs": {},
                        "retries": 0
                    }
                    r.lpush("celery", json.dumps(celery_task))
                    logger.info("approval.celery_enqueued", job_id=job_id)
                except Exception as e:
                    logger.warning("approval.celery_enqueue_failed", error=str(e), job_id=job_id)

                # Start Temporal workflow (best-effort)
                try:
                    import asyncio

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
                    logger.info("approval.temporal_started", job_id=job_id)
                except Exception as e:
                    logger.warning("approval.temporal_start_failed", error=str(e), job_id=job_id)

            session.commit()

            logger.info(
                "approval.decided",
                approval_id=a.id,
                decision=payload.decision,
                job_id=job_id
            )

            # Audit: record decision
            try:
                session.add(
                    ActionLog(
                        rule_name="approval.decision",
                        subject=a.subject,
                        action=payload.decision,
                        payload=a.payload,
                    )
                )
                session.commit()
            except Exception as e:
                logger.warning("approval.decide.audit_failed", error=str(e))
                session.rollback()

            # Metrics
            if global_metrics:
                try:
                    global_metrics["approvals_decisions_total"].labels(
                        status=payload.decision
                    ).inc()

                    if a.created_at and a.decided_at:
                        latency = (a.decided_at - a.created_at).total_seconds()
                        global_metrics["approvals_latency_seconds"].observe(latency)

                    # HITL metrics
                    mode = "hitl" if payload.decision in {"approve", "decline", "modify"} else "auto"
                    global_metrics["workflows_auto_vs_hitl_total"].labels(mode=mode).inc()
                except Exception as e:
                    logger.warning("approval.decide.metrics_failed", error=str(e))

            resp = ApprovalDecisionResponse(
                id=a.id,
                status=a.status,
                reason=a.reason,
                job_id=job_id
            )

            if span:
                try:
                    span.end()
                except Exception:
                    pass

            return resp

    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except IntegrityError as e:
        logger.error("approval.decide.integrity_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Database constraint violation"
        )
    except OperationalError as e:
        logger.error("approval.decide.db_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable"
        )
    except Exception as e:
        logger.error("approval.decide.unexpected_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post("/{id}/notify", response_model=ApprovalNotifyResponse)
def notify(id: int, payload: ApprovalNotifyRequest | None = None) -> ApprovalNotifyResponse:
    """
    Send a Slack notification about an approval.

    Args:
        id: The approval ID
        payload: Optional channel to notify

    Returns:
        Slack notification status

    Raises:
        404: If approval not found
    """
    channel = payload.channel if payload else None

    try:
        SessionLocal = get_sessionmaker()
        with SessionLocal() as session:
            a = session.get(Approval, id)
            if not a:
                logger.warning("approval.notify.not_found", approval_id=id)
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Approval {id} not found"
                )

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

            logger.info(
                "approval.notified",
                approval_id=a.id,
                channel=channel,
                ok=res.get("ok", False)
            )

            # Metrics
            if global_metrics:
                try:
                    ok = bool(res.get("ok")) or bool(res.get("dry_run"))
                    global_metrics["slack_posts_total"].labels(
                        kind="approval",
                        ok=str(ok).lower()
                    ).inc()
                except Exception as e:
                    logger.warning("approval.notify.metrics_failed", error=str(e))

            return ApprovalNotifyResponse(
                ok=bool(res.get("ok")) or bool(res.get("dry_run")),
                posted=res
            )

    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except OperationalError as e:
        logger.error("approval.notify.db_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable"
        )
    except Exception as e:
        logger.error("approval.notify.unexpected_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )
