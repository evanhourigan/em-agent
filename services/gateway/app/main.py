from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .core.config import get_settings
from .core.logging import configure_structlog, get_logger
from .core.observability import add_prometheus
from .db import check_database_health, get_engine


def create_app() -> FastAPI:
    settings = get_settings()

    configure_structlog()
    logger = get_logger(__name__)

    app = FastAPI(title=settings.app_name, version=settings.app_version)

    # CORS (dev-friendly by default)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Metrics
    add_prometheus(app, app_name="gateway")

    @app.on_event("startup")
    def on_startup() -> None:  # noqa: D401
        # Initialize connection pool early so first requests are fast
        logger.info("startup.init_db_pool")
        get_engine()

    @app.get("/health", tags=["ops"])  # Liveness/readiness probe
    def health(_: Request) -> JSONResponse:
        db = check_database_health()
        status_code = 200 if db["ok"] else 503
        return JSONResponse(
            {"status": "ok" if db["ok"] else "degraded", "db": db},
            status_code=status_code,
        )

    @app.get("/")
    def root() -> dict:
        return {"service": "gateway", "status": "ok"}

    return app


app = create_app()
