from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette_exporter import PrometheusMiddleware, handle_metrics

from .db import check_database_health, get_engine

app = FastAPI(title="EM Agent Gateway", version="0.1.0")

# Basic CORS defaults for local/dev; tighten in prod
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics
app.add_middleware(
    PrometheusMiddleware,
    app_name="gateway",
    prefix="gateway",
    group_paths=True,
)
app.add_route("/metrics", handle_metrics)


@app.on_event("startup")
def on_startup() -> None:
    # Initialize connection pool early so first requests are fast
    get_engine()


@app.get("/health", tags=["ops"])  # Liveness/readiness probe
def health(_: Request) -> JSONResponse:
    db = check_database_health()
    status_code = 200 if db["ok"] else 503
    return JSONResponse(
        {"status": "ok" if db["ok"] else "degraded", "db": db}, status_code=status_code
    )


@app.get("/")
def root() -> dict:
    return {"service": "gateway", "status": "ok"}
