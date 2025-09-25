from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import JSONResponse

from ....db import check_database_health


router = APIRouter(tags=["ops"])


@router.get("/health")
def health(_: Request) -> JSONResponse:
    db = check_database_health()
    status_code = 200 if db["ok"] else 503
    return JSONResponse(
        {"status": "ok" if db["ok"] else "degraded", "db": db},
        status_code=status_code,
    )
