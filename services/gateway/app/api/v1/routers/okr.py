from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from ....db import get_sessionmaker
from ....models.okr import Objective, KeyResult


router = APIRouter(prefix="/v1/okr", tags=["okr"])


@router.post("/objectives")
def create_objective(payload: Dict[str, Any]) -> Dict[str, Any]:
    title = (payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title required")
    owner = payload.get("owner")
    period = payload.get("period")
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        obj = Objective(title=title, owner=owner, period=period)
        session.add(obj)
        session.commit()
        return {"id": obj.id, "title": obj.title}


@router.post("/objectives/{id}/krs")
def add_key_result(id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    title = (payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title required")
    target = payload.get("target")
    unit = payload.get("unit")
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        obj = session.get(Objective, id)
        if not obj:
            raise HTTPException(status_code=404, detail="objective not found")
        kr = KeyResult(objective_id=obj.id, title=title, target=target, unit=unit)
        session.add(kr)
        session.commit()
        return {"id": kr.id}


@router.post("/krs/{id}/progress")
def update_progress(id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    current = payload.get("current")
    if current is None:
        raise HTTPException(status_code=400, detail="current required")
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        kr = session.get(KeyResult, id)
        if not kr:
            raise HTTPException(status_code=404, detail="kr not found")
        kr.current = current
        session.add(kr)
        session.commit()
        return {"ok": True}


@router.get("/objectives")
def list_objectives() -> List[Dict[str, Any]]:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        rows = session.query(Objective).order_by(Objective.id.desc()).limit(50).all()
        return [
            {"id": o.id, "title": o.title, "owner": o.owner, "period": o.period}
            for o in rows
        ]


