from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import IntegrityError, OperationalError

from ....core.logging import get_logger
from ....db import get_sessionmaker
from ....models.incidents import Incident, IncidentTimeline
from ....schemas.incidents import (
    IncidentAddNoteRequest,
    IncidentCloseResponse,
    IncidentNoteResponse,
    IncidentResponse,
    IncidentSetSeverityRequest,
    IncidentSeverityResponse,
    IncidentStartRequest,
    IncidentStartResponse,
)

router = APIRouter(prefix="/v1/incidents", tags=["incidents"])
logger = get_logger(__name__)


@router.post("", response_model=IncidentStartResponse)
def start_incident(payload: IncidentStartRequest) -> IncidentStartResponse:
    """
    Start a new incident.

    Creates an incident with the specified title and severity.
    Default title is 'Untitled Incident' if not provided.
    """
    try:
        title = payload.title or "Untitled Incident"
        severity = payload.severity

        SessionLocal = get_sessionmaker()
        with SessionLocal() as session:
            inc = Incident(title=title, severity=severity, status="open")
            session.add(inc)
            session.commit()
            session.refresh(inc)

            logger.info(
                "incident.started", incident_id=inc.id, title=title, severity=severity
            )
            return IncidentStartResponse(id=inc.id, status=inc.status, title=inc.title)

    except IntegrityError as e:
        logger.error("incident.start.integrity_error", error=str(e), exc_info=True)
        raise HTTPException(status_code=409, detail="Incident conflict")
    except OperationalError as e:
        logger.error("incident.start.db_error", error=str(e), exc_info=True)
        raise HTTPException(status_code=503, detail="Database unavailable")
    except Exception as e:
        logger.error("incident.start.unexpected_error", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{id}/note", response_model=IncidentNoteResponse)
def add_note(id: int, payload: IncidentAddNoteRequest) -> IncidentNoteResponse:
    """
    Add a note to an incident.

    Creates a timeline entry with the specified note text and optional author.
    """
    try:
        SessionLocal = get_sessionmaker()
        with SessionLocal() as session:
            inc = session.get(Incident, id)
            if not inc:
                logger.warning("incident.add_note.not_found", incident_id=id)
                raise HTTPException(status_code=404, detail="Incident not found")

            tl = IncidentTimeline(
                incident_id=inc.id,
                text=payload.text,
                author=payload.author,
                kind="note",
            )
            session.add(tl)
            session.commit()
            session.refresh(tl)

            logger.info(
                "incident.note_added",
                incident_id=id,
                timeline_id=tl.id,
                author=payload.author,
            )
            return IncidentNoteResponse(ok=True, timeline_id=tl.id)

    except HTTPException:
        raise  # Re-raise 404
    except IntegrityError as e:
        logger.error(
            "incident.add_note.integrity_error",
            error=str(e),
            incident_id=id,
            exc_info=True,
        )
        raise HTTPException(status_code=409, detail="Note conflict")
    except OperationalError as e:
        logger.error(
            "incident.add_note.db_error", error=str(e), incident_id=id, exc_info=True
        )
        raise HTTPException(status_code=503, detail="Database unavailable")
    except Exception as e:
        logger.error(
            "incident.add_note.unexpected_error",
            error=str(e),
            incident_id=id,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("", response_model=list[IncidentResponse])
def list_incidents() -> list[IncidentResponse]:
    """
    List incidents (most recent first, limited to 50).
    """
    try:
        SessionLocal = get_sessionmaker()
        with SessionLocal() as session:
            rows = session.query(Incident).order_by(Incident.id.desc()).limit(50).all()
            logger.info("incident.list", count=len(rows))
            return [IncidentResponse.model_validate(i) for i in rows]

    except OperationalError as e:
        logger.error("incident.list.db_error", error=str(e), exc_info=True)
        raise HTTPException(status_code=503, detail="Database unavailable")
    except Exception as e:
        logger.error("incident.list.unexpected_error", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{id}/close", response_model=IncidentCloseResponse)
def close_incident(id: int) -> IncidentCloseResponse:
    """
    Close an incident.

    Sets the status to 'closed' and records the close time.
    Creates a timeline entry to track the closure.
    """
    try:
        SessionLocal = get_sessionmaker()
        with SessionLocal() as session:
            inc = session.get(Incident, id)
            if not inc:
                logger.warning("incident.close.not_found", incident_id=id)
                raise HTTPException(status_code=404, detail="Incident not found")

            if inc.status != "closed":
                inc.status = "closed"
                inc.closed_at = datetime.now(UTC)
                session.add(inc)
                session.add(
                    IncidentTimeline(
                        incident_id=inc.id, kind="system", text="Incident closed"
                    )
                )
                session.commit()
                logger.info("incident.closed", incident_id=id)
            else:
                logger.info("incident.already_closed", incident_id=id)

            return IncidentCloseResponse(id=inc.id, status=inc.status)

    except HTTPException:
        raise  # Re-raise 404
    except IntegrityError as e:
        logger.error(
            "incident.close.integrity_error",
            error=str(e),
            incident_id=id,
            exc_info=True,
        )
        raise HTTPException(status_code=409, detail="Incident conflict")
    except OperationalError as e:
        logger.error(
            "incident.close.db_error", error=str(e), incident_id=id, exc_info=True
        )
        raise HTTPException(status_code=503, detail="Database unavailable")
    except Exception as e:
        logger.error(
            "incident.close.unexpected_error",
            error=str(e),
            incident_id=id,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{id}/severity", response_model=IncidentSeverityResponse)
def set_severity(
    id: int, payload: IncidentSetSeverityRequest
) -> IncidentSeverityResponse:
    """
    Set incident severity.

    Updates the severity level and creates a timeline entry to track the change.
    """
    try:
        SessionLocal = get_sessionmaker()
        with SessionLocal() as session:
            inc = session.get(Incident, id)
            if not inc:
                logger.warning("incident.set_severity.not_found", incident_id=id)
                raise HTTPException(status_code=404, detail="Incident not found")

            inc.severity = payload.severity
            session.add(inc)
            session.add(
                IncidentTimeline(
                    incident_id=inc.id,
                    kind="system",
                    text=f"Severity set to {payload.severity}",
                )
            )
            session.commit()

            logger.info(
                "incident.severity_set", incident_id=id, severity=payload.severity
            )
            return IncidentSeverityResponse(id=inc.id, severity=inc.severity)

    except HTTPException:
        raise  # Re-raise 404
    except IntegrityError as e:
        logger.error(
            "incident.set_severity.integrity_error",
            error=str(e),
            incident_id=id,
            exc_info=True,
        )
        raise HTTPException(status_code=409, detail="Incident conflict")
    except OperationalError as e:
        logger.error(
            "incident.set_severity.db_error",
            error=str(e),
            incident_id=id,
            exc_info=True,
        )
        raise HTTPException(status_code=503, detail="Database unavailable")
    except Exception as e:
        logger.error(
            "incident.set_severity.unexpected_error",
            error=str(e),
            incident_id=id,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error")
