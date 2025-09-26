from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import JSONResponse

from ...deps import get_db_session
from ....db import check_database_health

router = APIRouter(tags=["ops"])


@router.get("/health")
def health(_: Request, session: Session = Depends(get_db_session)) -> JSONResponse:
    # Touch the session to ensure ORM roundtrip is functional
    try:
        session.execute(text("SELECT 1"))
        orm_ok = True
    except Exception as exc:  # noqa: BLE001
        orm_ok = False
        orm_details = str(exc)
    else:
        orm_details = "ok"

    db = check_database_health()
    overall_ok = db["ok"] and orm_ok
    status_code = 200 if overall_ok else 503
    return JSONResponse(
        {
            "status": "ok" if overall_ok else "degraded",
            "db": db,
            "orm": {"ok": orm_ok, "details": orm_details},
        },
        status_code=status_code,
    )
