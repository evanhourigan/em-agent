from fastapi import APIRouter
from starlette.responses import PlainTextResponse

router = APIRouter(tags=["ops"])


@router.get("/metrics")
def metrics_placeholder() -> PlainTextResponse:
    # Metrics are served by starlette_exporter middleware at /metrics.
    # This placeholder keeps path discoverable in the OpenAPI schema.
    return PlainTextResponse("metrics available at /metrics", status_code=200)
