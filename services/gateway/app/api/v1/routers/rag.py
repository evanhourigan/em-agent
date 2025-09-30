from __future__ import annotations

from typing import Any, Dict

import httpx
from fastapi import APIRouter, HTTPException

from ....core.config import get_settings

router = APIRouter(prefix="/v1/rag", tags=["rag"])


@router.post("/search")
def proxy_search(payload: Dict[str, Any]) -> Dict[str, Any]:
    rag_url = get_settings().rag_url.rstrip("/")
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(f"{rag_url}/search", json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"rag proxy error: {exc}")
