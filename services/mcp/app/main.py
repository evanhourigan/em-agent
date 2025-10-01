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
                resp = client.post(
                    f"{gateway_url}/v1/reports/standup", json=payload or {}
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @app.post("/tools/reports.sprint_health")
    def reports_sprint_health(payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.post(
                    f"{gateway_url}/v1/reports/sprint-health", json=payload or {}
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @app.post("/tools/approvals.propose")
    def approvals_propose(payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.post(f"{gateway_url}/v1/approvals/propose", json=payload)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @app.post("/tools/approvals.decide")
    def approvals_decide(payload: Dict[str, Any]) -> Dict[str, Any]:
        approval_id = payload.get("id")
        if not approval_id:
            raise HTTPException(status_code=400, detail="id required")
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.post(
                    f"{gateway_url}/v1/approvals/{approval_id}/decision",
                    json={
                        "decision": payload.get("decision"),
                        "reason": payload.get("reason"),
                    },
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    # Slack posting (direct, optional) – mirrors gateway Slack client behavior
    @app.post("/tools/slack.post_text")
    def slack_post_text(payload: Dict[str, Any]) -> Dict[str, Any]:
        text = payload.get("text") or ""
        if not text:
            raise HTTPException(status_code=400, detail="text required")
        webhook = os.getenv("SLACK_WEBHOOK_URL")
        bot_token = os.getenv("SLACK_BOT_TOKEN")
        default_channel = os.getenv("SLACK_DEFAULT_CHANNEL")
        if not webhook and not bot_token:
            # dry-run
            return {"ok": False, "dry_run": True, "text": text}
        if webhook:
            with httpx.Client(timeout=10) as client:
                resp = client.post(webhook, json={"text": text})
                return {"ok": resp.status_code < 300}
        headers = {"Authorization": f"Bearer {bot_token}"}
        channel = payload.get("channel") or default_channel
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                "https://slack.com/api/chat.postMessage",
                headers=headers,
                json={"channel": channel, "text": text},
            )
            data = resp.json()
            return {"ok": bool(data.get("ok")), "response": data}

    @app.post("/tools/slack.post_blocks")
    def slack_post_blocks(payload: Dict[str, Any]) -> Dict[str, Any]:
        blocks = payload.get("blocks") or []
        if not isinstance(blocks, list) or not blocks:
            raise HTTPException(status_code=400, detail="blocks required")
        text = payload.get("text") or "Message"
        webhook = os.getenv("SLACK_WEBHOOK_URL")
        bot_token = os.getenv("SLACK_BOT_TOKEN")
        default_channel = os.getenv("SLACK_DEFAULT_CHANNEL")
        if not webhook and not bot_token:
            return {"ok": False, "dry_run": True, "blocks": blocks}
        if webhook:
            with httpx.Client(timeout=10) as client:
                resp = client.post(webhook, json={"text": text, "blocks": blocks})
                return {"ok": resp.status_code < 300}
        headers = {"Authorization": f"Bearer {bot_token}"}
        channel = payload.get("channel") or default_channel
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                "https://slack.com/api/chat.postMessage",
                headers=headers,
                json={"channel": channel, "text": text, "blocks": blocks},
            )
            data = resp.json()
            return {"ok": bool(data.get("ok")), "response": data}

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
