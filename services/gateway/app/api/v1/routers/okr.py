from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import IntegrityError, OperationalError

from ....core.logging import get_logger
from ....db import get_sessionmaker
from ....models.okr import KeyResult, Objective
from ....schemas.okr import (
    KeyResultCreateRequest,
    KeyResultCreateResponse,
    KeyResultProgressRequest,
    KeyResultProgressResponse,
    ObjectiveCreateRequest,
    ObjectiveCreateResponse,
    ObjectiveResponse,
)

router = APIRouter(prefix="/v1/okr", tags=["okr"])
logger = get_logger(__name__)


@router.post("/objectives", response_model=ObjectiveCreateResponse)
def create_objective(payload: ObjectiveCreateRequest) -> ObjectiveCreateResponse:
    """
    Create a new objective.

    An objective represents a high-level goal to be achieved within a time period.
    """
    try:
        SessionLocal = get_sessionmaker()
        with SessionLocal() as session:
            obj = Objective(
                title=payload.title, owner=payload.owner, period=payload.period
            )
            session.add(obj)
            session.commit()
            session.refresh(obj)

            logger.info(
                "okr.objective_created",
                objective_id=obj.id,
                title=payload.title,
                owner=payload.owner,
            )
            return ObjectiveCreateResponse(id=obj.id, title=obj.title)

    except IntegrityError as e:
        logger.error(
            "okr.create_objective.integrity_error", error=str(e), exc_info=True
        )
        raise HTTPException(status_code=409, detail="Objective conflict")
    except OperationalError as e:
        logger.error("okr.create_objective.db_error", error=str(e), exc_info=True)
        raise HTTPException(status_code=503, detail="Database unavailable")
    except Exception as e:
        logger.error(
            "okr.create_objective.unexpected_error", error=str(e), exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/objectives/{id}/krs", response_model=KeyResultCreateResponse)
def add_key_result(id: int, payload: KeyResultCreateRequest) -> KeyResultCreateResponse:
    """
    Add a key result to an objective.

    A key result is a measurable outcome that contributes to achieving an objective.
    """
    try:
        SessionLocal = get_sessionmaker()
        with SessionLocal() as session:
            obj = session.get(Objective, id)
            if not obj:
                logger.warning("okr.add_kr.objective_not_found", objective_id=id)
                raise HTTPException(status_code=404, detail="Objective not found")

            kr = KeyResult(
                objective_id=obj.id,
                title=payload.title,
                target=payload.target,
                unit=payload.unit,
            )
            session.add(kr)
            session.commit()
            session.refresh(kr)

            logger.info(
                "okr.key_result_added",
                objective_id=id,
                kr_id=kr.id,
                title=payload.title,
            )
            return KeyResultCreateResponse(id=kr.id)

    except HTTPException:
        raise  # Re-raise 404
    except IntegrityError as e:
        logger.error(
            "okr.add_kr.integrity_error", error=str(e), objective_id=id, exc_info=True
        )
        raise HTTPException(status_code=409, detail="Key result conflict")
    except OperationalError as e:
        logger.error(
            "okr.add_kr.db_error", error=str(e), objective_id=id, exc_info=True
        )
        raise HTTPException(status_code=503, detail="Database unavailable")
    except Exception as e:
        logger.error(
            "okr.add_kr.unexpected_error", error=str(e), objective_id=id, exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/krs/{id}/progress", response_model=KeyResultProgressResponse)
def update_progress(
    id: int, payload: KeyResultProgressRequest
) -> KeyResultProgressResponse:
    """
    Update the current progress value for a key result.

    This tracks how close the key result is to its target value.
    """
    try:
        SessionLocal = get_sessionmaker()
        with SessionLocal() as session:
            kr = session.get(KeyResult, id)
            if not kr:
                logger.warning("okr.update_progress.kr_not_found", kr_id=id)
                raise HTTPException(status_code=404, detail="Key result not found")

            kr.current = payload.current
            session.add(kr)
            session.commit()

            logger.info(
                "okr.progress_updated",
                kr_id=id,
                current=payload.current,
                target=kr.target,
            )
            return KeyResultProgressResponse(ok=True)

    except HTTPException:
        raise  # Re-raise 404
    except IntegrityError as e:
        logger.error(
            "okr.update_progress.integrity_error", error=str(e), kr_id=id, exc_info=True
        )
        raise HTTPException(status_code=409, detail="Progress update conflict")
    except OperationalError as e:
        logger.error(
            "okr.update_progress.db_error", error=str(e), kr_id=id, exc_info=True
        )
        raise HTTPException(status_code=503, detail="Database unavailable")
    except Exception as e:
        logger.error(
            "okr.update_progress.unexpected_error",
            error=str(e),
            kr_id=id,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/objectives", response_model=list[ObjectiveResponse])
def list_objectives() -> list[ObjectiveResponse]:
    """
    List objectives (most recent first, limited to 50).
    """
    try:
        SessionLocal = get_sessionmaker()
        with SessionLocal() as session:
            rows = (
                session.query(Objective).order_by(Objective.id.desc()).limit(50).all()
            )
            logger.info("okr.list_objectives", count=len(rows))
            return [ObjectiveResponse.model_validate(o) for o in rows]

    except OperationalError as e:
        logger.error("okr.list_objectives.db_error", error=str(e), exc_info=True)
        raise HTTPException(status_code=503, detail="Database unavailable")
    except Exception as e:
        logger.error(
            "okr.list_objectives.unexpected_error", error=str(e), exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error")
