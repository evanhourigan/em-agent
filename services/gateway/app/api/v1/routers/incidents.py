from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

from ....db import get_sessionmaker
from ....models.incidents import Incident, IncidentTimeline


router = APIRouter(prefix="/v1/incidents", tags=["incidents"])


@router.post("")
def start_incident(payload: Dict[str, Any]) -> Dict[str, Any]:
    title = (payload.get("title") or "").strip() or "Untitled Incident"
    severity = (payload.get("severity") or None)
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        inc = Incident(title=title, severity=severity, status="open")
        session.add(inc)
        session.commit()
        return {"id": inc.id, "status": inc.status, "title": inc.title}


@router.post("/{id}/note")
def add_note(id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text required")
    author = (payload.get("author") or None)
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        inc = session.get(Incident, id)
        if not inc:
            raise HTTPException(status_code=404, detail="incident not found")
        tl = IncidentTimeline(incident_id=inc.id, text=text, author=author, kind="note")
        session.add(tl)
        session.commit()
        return {"ok": True, "timeline_id": tl.id}


@router.get("")
def list_incidents() -> List[Dict[str, Any]]:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        rows = session.query(Incident).order_by(Incident.id.desc()).limit(50).all()
        return [
            {"id": i.id, "title": i.title, "status": i.status, "severity": i.severity}
            for i in rows
        ]


@router.post("/{id}/close")
def close_incident(id: int) -> Dict[str, Any]:
    from datetime import datetime

    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        inc = session.get(Incident, id)
        if not inc:
            raise HTTPException(status_code=404, detail="incident not found")
        if inc.status != "closed":
            inc.status = "closed"
            inc.closed_at = datetime.utcnow()
            session.add(inc)
            session.add(IncidentTimeline(incident_id=inc.id, kind="system", text="Incident closed"))
            session.commit()
        return {"id": inc.id, "status": inc.status}


@router.post("/{id}/severity")
def set_severity(id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    sev = (payload.get("severity") or "").strip()
    if not sev:
        raise HTTPException(status_code=400, detail="severity required")
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        inc = session.get(Incident, id)
        if not inc:
            raise HTTPException(status_code=404, detail="incident not found")
        inc.severity = sev
        session.add(inc)
        session.add(IncidentTimeline(incident_id=inc.id, kind="system", text=f"Severity set to {sev}"))
        session.commit()
        return {"id": inc.id, "severity": inc.severity}


