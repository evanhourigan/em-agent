from typing import Any, List, Dict

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.responses import PlainTextResponse

from ...deps import get_db_session
from ....core.metrics import metrics as global_metrics
from ....core.config import get_settings

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
def metrics_placeholder() -> PlainTextResponse:
    # Prometheus metrics are served by starlette_exporter middleware at /metrics.
    return PlainTextResponse("metrics available at /metrics", status_code=200)


@router.get("/v1/metrics/quotas")
def quotas_info() -> Dict[str, Any]:
    m = global_metrics
    out: Dict[str, Any] = {"ok": True}
    try:
        settings = get_settings()
        if m:
            def _val(k):
                c = m.get(k)
                try:
                    return c._value.get() if c else None  # type: ignore[attr-defined]
                except Exception:
                    return None
            out["quota"] = {
                "slack_posts": _val("quota_slack_posts_total"),
                "rag_searches": _val("quota_rag_searches_total"),
                "limits": {
                    "max_daily_slack_posts": settings.max_daily_slack_posts,
                    "max_daily_rag_searches": settings.max_daily_rag_searches,
                },
            }
    except Exception:
        pass
    return out


def _query_list(session: Session, sql: str) -> List[dict[str, Any]]:
    rows = session.execute(text(sql)).mappings().all()
    return [dict(r) for r in rows]


@router.get("/v1/metrics/dora/lead-time")
def dora_lead_time(session: Session = Depends(get_db_session)) -> List[dict[str, Any]]:
    return _query_list(
        session,
        "select delivery_id, lead_time_hours from public.dora_lead_time order by lead_time_hours desc limit 200",
    )


@router.get("/v1/metrics/dora/deployment-frequency")
def deployment_frequency(
    session: Session = Depends(get_db_session),
) -> List[dict[str, Any]]:
    return _query_list(
        session,
        "select day, deployments from public.deployment_frequency order by day desc limit 60",
    )


@router.get("/v1/metrics/dora/change-fail-rate")
def change_fail_rate(
    session: Session = Depends(get_db_session),
) -> List[dict[str, Any]]:
    return _query_list(
        session,
        "select day, change_fail_rate from public.change_fail_rate order by day desc limit 60",
    )


@router.get("/v1/metrics/dora/mttr")
def mttr(session: Session = Depends(get_db_session)) -> List[dict[str, Any]]:
    return _query_list(
        session,
        "select delivery_id, mttr_hours from public.mttr order by mttr_hours desc limit 200",
    )
