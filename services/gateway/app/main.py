from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.cors import CORSMiddleware

from .api.v1.routers.agent import router as agent_router
from .api.v1.routers.approvals import router as approvals_router
from .api.v1.routers.auth import router as auth_router
from .api.v1.routers.health import router as health_router
from .api.v1.routers.identities import router as identities_router
from .api.v1.routers.metrics import router as metrics_router
from .api.v1.routers.policy import router as policy_router
from .api.v1.routers.projects import router as projects_router
from .api.v1.routers.rag import router as rag_router
from .api.v1.routers.reports import router as reports_router
from .api.v1.routers.evals import router as evals_router
from .api.v1.routers.incidents import router as incidents_router
from .api.v1.routers.onboarding import router as onboarding_router
from .api.v1.routers.okr import router as okr_router
from .api.v1.routers.signals import router as signals_router
from .api.v1.routers.slack import router as slack_router
from .api.v1.routers.webhooks import router as webhooks_router
from .api.v1.routers.workflows import router as workflows_router
from .core.config import get_settings, validate_settings
from .core.logging import configure_structlog, get_logger
from .core.observability import add_prometheus, add_tracing
from .db import get_engine, get_sessionmaker
from .middleware.logging import RequestLoggingMiddleware
from .services.signal_runner import maybe_start_evaluator
from .services.workflow_runner import (
    maybe_start_workflow_runner,
    maybe_stop_workflow_runner,
    maybe_start_retention,
    maybe_stop_retention,
)


def create_app() -> FastAPI:
    settings = get_settings()
    # Reliability: validate env/settings early
    try:
        validate_settings(settings)
    except Exception as exc:  # noqa: BLE001
        # Fail-fast with a clear error
        raise RuntimeError(f"Invalid configuration: {exc}")

    configure_structlog()
    logger = get_logger(__name__)

    app = FastAPI(title=settings.app_name, version=settings.app_version)

    # Rate limiting setup
    if settings.rate_limit_enabled:
        limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings.rate_limit_per_min}/minute"])
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        logger.info("rate_limiting.enabled", limit_per_min=settings.rate_limit_per_min)
    else:
        logger.info("rate_limiting.disabled")

    # Global exception handlers
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Handle Pydantic validation errors with detailed messages."""
        logger.warning(
            "request.validation_error",
            path=request.url.path,
            errors=exc.errors(),
            body=exc.body,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": "Validation error",
                "errors": exc.errors(),
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(
        request: Request, exc: SQLAlchemyError
    ) -> JSONResponse:
        """Handle database errors gracefully."""
        logger.error(
            "request.database_error",
            path=request.url.path,
            error=str(exc),
            exc_info=True,
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Database error occurred"},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle all unhandled exceptions."""
        logger.error(
            "request.unhandled_exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            error_type=type(exc).__name__,
            exc_info=True,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )

    # Middleware (order matters - later middleware wraps earlier ones)
    # Add request logging middleware first (outermost)
    app.add_middleware(RequestLoggingMiddleware)

    # CORS Configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
        max_age=settings.cors_max_age,
    )
    logger.info(
        "cors.configured",
        allow_origins=settings.cors_allow_origins,
        allow_credentials=settings.cors_allow_credentials,
    )

    # Metrics
    add_prometheus(app, app_name="gateway")

    # Tracing (optional)
    if settings.otel_enabled:
        add_tracing(app, app_name="gateway", endpoint=settings.otel_exporter_otlp_endpoint)

    @app.on_event("startup")
    def on_startup() -> None:  # noqa: D401
        # Initialize connection pool early so first requests are fast
        logger.info("startup.init_db_pool")
        get_engine()
        maybe_start_evaluator(app, lambda: get_sessionmaker()())
        maybe_start_workflow_runner(app, lambda: get_sessionmaker()())
        maybe_start_retention(app, lambda: get_sessionmaker()())

    @app.on_event("shutdown")
    def on_shutdown() -> None:  # noqa: D401
        maybe_stop_workflow_runner(app)
        maybe_stop_retention(app)

    # Routers
    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(auth_router)  # Authentication endpoints
    app.include_router(projects_router)
    app.include_router(webhooks_router)
    app.include_router(identities_router)
    app.include_router(signals_router)
    app.include_router(workflows_router)
    app.include_router(approvals_router)
    app.include_router(policy_router)
    app.include_router(rag_router)
    app.include_router(slack_router)
    app.include_router(reports_router)
    app.include_router(agent_router)
    app.include_router(evals_router)
    app.include_router(incidents_router)
    app.include_router(onboarding_router)
    app.include_router(okr_router)

    @app.get("/")
    def root() -> dict:
        return {"service": "gateway", "status": "ok"}

    return app


app = create_app()
