from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from ....core.config import get_settings
from ....core.metrics import metrics as global_metrics

router = APIRouter(prefix="/v1/rag", tags=["rag"])


@router.post("/search")
def proxy_search(payload: dict[str, Any]) -> dict[str, Any]:
    rag_url = get_settings().rag_url.rstrip("/")
    last_exc: Exception | None = None
    for _ in range(3):
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.post(f"{rag_url}/search", json=payload)
                resp.raise_for_status()
                data = resp.json()
                m = global_metrics
                if m:
                    try:
                        m.get("quota_rag_searches_total", None) and m[
                            "quota_rag_searches_total"
                        ].inc()
                    except Exception:
                        pass
                return data
        except httpx.HTTPError as exc:  # noqa: BLE001
            last_exc = exc
    raise HTTPException(status_code=502, detail=f"rag proxy error: {last_exc}")


@router.post("/index")
def proxy_index(payload: dict[str, Any]) -> dict[str, Any]:
    rag_url = get_settings().rag_url.rstrip("/")
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(f"{rag_url}/index", json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"rag index error: {exc}")


@router.post("/index/bulk")
def proxy_index_bulk(payload: dict[str, Any]) -> dict[str, Any]:
    rag_url = get_settings().rag_url.rstrip("/")
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(f"{rag_url}/index/bulk", json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"rag index bulk error: {exc}")
