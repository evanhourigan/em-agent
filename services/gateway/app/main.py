from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .api.v1.routers.approvals import router as approvals_router
from .api.v1.routers.health import router as health_router
from .api.v1.routers.identities import router as identities_router
from .api.v1.routers.metrics import router as metrics_router
from .api.v1.routers.policy import router as policy_router
from .api.v1.routers.projects import router as projects_router
from .api.v1.routers.signals import router as signals_router
from .api.v1.routers.webhooks import router as webhooks_router
from .api.v1.routers.workflows import router as workflows_router
from .core.config import get_settings
from .core.logging import configure_structlog, get_logger
from .core.observability import add_prometheus
from .db import get_engine, get_sessionmaker
from .services.signal_runner import maybe_start_evaluator
from .services.workflow_runner import maybe_start_workflow_runner


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
        maybe_start_evaluator(app, lambda: get_sessionmaker()())
        maybe_start_workflow_runner(app, lambda: get_sessionmaker()())

    # Routers
    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(projects_router)
    app.include_router(webhooks_router)
    app.include_router(identities_router)
    app.include_router(signals_router)
    app.include_router(workflows_router)
    app.include_router(approvals_router)
    app.include_router(policy_router)

    @app.get("/")
    def root() -> dict:
        return {"service": "gateway", "status": "ok"}

    return app


app = create_app()
