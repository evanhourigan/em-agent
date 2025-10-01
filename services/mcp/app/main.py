from __future__ import annotations

import os
from typing import Any, Dict

import httpx
from fastapi import FastAPI, HTTPException


def create_app() -> FastAPI:
    app = FastAPI(title="mcp-tools", version="0.1.0")

    gateway_url = os.getenv("GATEWAY_URL", "http://gateway:8000").rstrip("/")

    @app.get("/")
    def root() -> Dict[str, Any]:
        return {"service": "mcp-tools", "gateway": gateway_url}

    # Minimal HTTP-based tools (MCP-ready): call gateway endpoints
    @app.post("/tools/signals.evaluate")
    def signals_evaluate(payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.post(f"{gateway_url}/v1/signals/evaluate", json=payload)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @app.post("/tools/reports.standup")
    def reports_standup(payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.post(f"{gateway_url}/v1/reports/standup", json=payload or {})
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @app.post("/tools/rag.search")
    def rag_search(payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.post(f"{gateway_url}/v1/rag/search", json=payload)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    return app


app = create_app()


