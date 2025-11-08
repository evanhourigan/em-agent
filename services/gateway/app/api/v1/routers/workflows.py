from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from ....api.v1.routers.approvals import propose_action
from ....api.v1.routers.policy import _load_policy
from ....core.config import get_settings
from ....core.logging import get_logger
from ....core.metrics import metrics as global_metrics
from ....models.action_log import ActionLog
from ....models.workflow_jobs import WorkflowJob
from ....schemas.approvals import ApprovalProposalRequest
from ....schemas.workflows import (
    WorkflowJobResponse,
    WorkflowRunRequest,
    WorkflowRunResponse,
)
from ...deps import get_db_session

router = APIRouter(prefix="/v1/workflows", tags=["workflows"])
logger = get_logger(__name__)


@router.post("/run", response_model=WorkflowRunResponse)
def run_workflow(
    payload: WorkflowRunRequest, session: Session = Depends(get_db_session)
) -> WorkflowRunResponse:
    """
    Run a workflow with policy-gated execution.

    Determines the action based on:
    1. Explicit action in request
    2. OPA policy decision (if configured)
    3. Local policy file
    4. Default to 'nudge'

    If action is 'block', creates an approval request instead.
    """
    try:
        # Policy-gated execution: determine default action for a rule kind
        rule = payload.rule or payload.kind or "manual"
        subject = payload.subject or "n/a"
        action = payload.action

        if not action:
            kind = payload.kind or rule
            settings = get_settings()

            # Prefer OPA if configured
            if settings.opa_url:
                try:
                    logger.info("workflow.opa_query", kind=kind, subject=subject)
                    with httpx.Client(timeout=5) as client:
                        resp = client.post(
                            settings.opa_url.rstrip("/") + "/v1/data/em_agent/decision",
                            json={"input": {"kind": kind, **payload.model_dump()}},
                        )
                        resp.raise_for_status()
                        data = resp.json().get("result") or {}
                        action = data.get("action") or (
                            "allow" if data.get("allow", True) else "block"
                        )
                        logger.info("workflow.opa_decision", action=action, kind=kind)
                except httpx.HTTPStatusError as e:
                    logger.warning(
                        "workflow.opa_http_error",
                        error=str(e),
                        status_code=e.response.status_code,
                    )
                    action = None
                except httpx.RequestError as e:
                    logger.warning("workflow.opa_request_error", error=str(e))
                    action = None

            if not action:
                policy = _load_policy().get(kind)
                action = (policy or {}).get("action", "nudge")
                logger.info("workflow.policy_decision", action=action, kind=kind)

        if action == "block":
            # Instead of hard-failing, propose an approval for human decision
            logger.info("workflow.blocked", rule=rule, subject=subject)
            proposal = ApprovalProposalRequest(
                subject=subject,
                action=rule,
                payload=payload.payload,
                reason="blocked by policy",
            )
            res = propose_action(proposal)

            # Count HITL path
            if global_metrics:
                try:
                    global_metrics["workflows_auto_vs_hitl_total"].labels(
                        mode="hitl"
                    ).inc()
                except KeyError as e:
                    logger.warning("workflow.metrics_error", error=str(e))

            return WorkflowRunResponse(
                status="awaiting_approval", action_id=res.action_id, action=action
            )

        # Create workflow job
        log = ActionLog(
            rule_name=rule,
            subject=subject,
            action=action,
            payload=str(payload.payload) if payload.payload else "{}",
        )
        job = WorkflowJob(
            status="queued",
            rule_kind=payload.kind or rule,
            subject=subject,
            payload=str(payload.payload) if payload.payload else "{}",
        )

        session.add(log)
        session.add(job)
        session.commit()
        session.refresh(log)

        logger.info(
            "workflow.queued", id=log.id, rule=rule, subject=subject, action=action
        )

        # Count AUTO path
        if global_metrics:
            try:
                global_metrics["workflows_auto_vs_hitl_total"].labels(mode="auto").inc()
            except KeyError as e:
                logger.warning("workflow.metrics_error", error=str(e))

        return WorkflowRunResponse(status="queued", id=log.id, action=action)

    except HTTPException:
        raise  # Re-raise HTTP exceptions from propose_action
    except IntegrityError as e:
        logger.error("workflow.run.integrity_error", error=str(e), exc_info=True)
        session.rollback()
        raise HTTPException(status_code=409, detail="Workflow conflict")
    except OperationalError as e:
        logger.error("workflow.run.db_error", error=str(e), exc_info=True)
        session.rollback()
        raise HTTPException(status_code=503, detail="Database unavailable")
    except Exception as e:
        logger.error("workflow.run.unexpected_error", error=str(e), exc_info=True)
        session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/jobs", response_model=list[WorkflowJobResponse])
def list_jobs(session: Session = Depends(get_db_session)) -> list[WorkflowJobResponse]:
    """
    List workflow jobs (most recent first, limited to 100).
    """
    try:
        rows = (
            session.query(WorkflowJob).order_by(WorkflowJob.id.desc()).limit(100).all()
        )
        logger.info("workflow.list_jobs", count=len(rows))
        return [WorkflowJobResponse.model_validate(j) for j in rows]
    except OperationalError as e:
        logger.error("workflow.list_jobs.db_error", error=str(e), exc_info=True)
        raise HTTPException(status_code=503, detail="Database unavailable")
    except Exception as e:
        logger.error("workflow.list_jobs.unexpected_error", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/jobs/{id}", response_model=WorkflowJobResponse)
def get_job(id: int, session: Session = Depends(get_db_session)) -> WorkflowJobResponse:
    """
    Get a specific workflow job by ID.
    """
    try:
        j = session.get(WorkflowJob, id)
        if not j:
            logger.warning("workflow.get_job.not_found", job_id=id)
            raise HTTPException(status_code=404, detail="Workflow job not found")

        logger.info("workflow.get_job", job_id=id, status=j.status)
        return WorkflowJobResponse.model_validate(j)
    except HTTPException:
        raise  # Re-raise 404
    except OperationalError as e:
        logger.error(
            "workflow.get_job.db_error", error=str(e), job_id=id, exc_info=True
        )
        raise HTTPException(status_code=503, detail="Database unavailable")
    except Exception as e:
        logger.error(
            "workflow.get_job.unexpected_error", error=str(e), job_id=id, exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error")
