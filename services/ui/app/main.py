from __future__ import annotations

import os
from typing import Any, Dict

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse


def create_app() -> FastAPI:
    app = FastAPI(title="ui", version="0.1.0")

    gateway_url = os.getenv("GATEWAY_URL", "http://gateway:8000").rstrip("/")

    @app.get("/")
    def index() -> HTMLResponse:
        with open("/app/static/index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(f.read(), status_code=200)

    @app.post("/search")
    def search(payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(f"{gateway_url}/v1/rag/search", json=payload)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    return app


app = create_app()
