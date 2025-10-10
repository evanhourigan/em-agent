from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from ....db import get_sessionmaker
from ....models.onboarding import OnboardingPlan, OnboardingTask


router = APIRouter(prefix="/v1/onboarding", tags=["onboarding"])


@router.post("/plans")
def create_plan(payload: Dict[str, Any]) -> Dict[str, Any]:
    title = (payload.get("title") or "").strip() or "New Hire Plan"
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        plan = OnboardingPlan(title=title)
        session.add(plan)
        session.commit()
        return {"id": plan.id, "title": plan.title, "status": plan.status}


@router.post("/plans/{id}/tasks")
def add_task(id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    title = (payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title required")
    assignee = payload.get("assignee")
    due_date = payload.get("due_date")
    due = None
    if due_date:
        try:
            due = datetime.fromisoformat(due_date).date()
        except Exception:
            pass
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        plan = session.get(OnboardingPlan, id)
        if not plan:
            raise HTTPException(status_code=404, detail="plan not found")
        task = OnboardingTask(plan_id=plan.id, title=title, assignee=assignee, due_date=due)
        session.add(task)
        session.commit()
        return {"id": task.id}


@router.post("/tasks/{id}/done")
def mark_done(id: int) -> Dict[str, Any]:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        task = session.get(OnboardingTask, id)
        if not task:
            raise HTTPException(status_code=404, detail="task not found")
        task.status = "done"
        task.completed_at = datetime.utcnow()
        session.add(task)
        session.commit()
        return {"ok": True}


@router.get("/plans")
def list_plans() -> List[Dict[str, Any]]:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        rows = session.query(OnboardingPlan).order_by(OnboardingPlan.id.desc()).limit(50).all()
        return [{"id": p.id, "title": p.title, "status": p.status} for p in rows]


