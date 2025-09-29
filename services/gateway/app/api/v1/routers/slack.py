from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from ....models.workflow_jobs import WorkflowJob
from ....db import get_sessionmaker


router = APIRouter(prefix="/v1/slack", tags=["slack"])


@router.post("/commands")
def commands(payload: Dict[str, Any]) -> Dict[str, Any]:
    text = payload.get("text", "").strip()
    if text.startswith("signals"):
        return {"ok": True, "message": "Signals: stale_pr, wip_limit_exceeded, pr_without_review"}
    if text.startswith("approvals"):
        SessionLocal = get_sessionmaker()
        with SessionLocal() as session:
            pending = session.execute("select count(*) from approvals where status='pending'").scalar()  # noqa: S608
            return {"ok": True, "message": f"Pending approvals: {pending}"}
    raise HTTPException(status_code=400, detail="unsupported command")


@router.post("/interactions")
def interactions(payload: Dict[str, Any]) -> Dict[str, Any]:
    action = payload.get("action")
    if action == "approve-job":
        job_id = int(payload.get("job_id"))
        SessionLocal = get_sessionmaker()
        with SessionLocal() as session:
            job = session.get(WorkflowJob, job_id)
            if not job:
                raise HTTPException(status_code=404, detail="job not found")
            job.status = "queued"
            session.add(job)
            session.commit()
            return {"ok": True, "message": f"Job {job_id} queued"}
    raise HTTPException(status_code=400, detail="unsupported interaction")


