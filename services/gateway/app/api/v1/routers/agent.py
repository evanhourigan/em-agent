from __future__ import annotations

from typing import Any, Dict

import httpx
from fastapi import APIRouter, HTTPException

from ....core.config import get_settings

router = APIRouter(prefix="/v1/agent", tags=["agent"])


@router.post("/run")
def run_agent(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Heuristic agent loop: calls MCP tools and summarizes results.

    payload: { "query": str, "days": optional int }
    """
    q = (payload.get("query") or "").strip().lower()
    if not q:
        raise HTTPException(status_code=400, detail="query required")

    mcp_url = "http://mcp:8000"
    days = int(payload.get("days", 14))
    out: Dict[str, Any] = {"query": q, "steps": []}

    def call_tool(path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        try:
            with httpx.Client(timeout=20) as client:
                resp = client.post(f"{mcp_url}{path}", json=body)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"tool error {path}: {exc}")

    # Very simple planning: keywords route to tools
    if any(k in q for k in ["sprint", "health", "summary"]):
        r = call_tool("/tools/reports.sprint_health", {"days": days})
        out["steps"].append({"tool": "reports.sprint_health", "result": r})
    if any(k in q for k in ["stale", "triage", "review"]):
        r = call_tool("/tools/signals.evaluate", {"kinds": ["stale_pr", "pr_without_review"]})
        out["steps"].append({"tool": "signals.evaluate", "result": r})
    if any(k in q for k in ["docs", "why", "how", "explain"]):
        r = call_tool("/tools/rag.search", {"q": q, "top_k": 3})
        out["steps"].append({"tool": "rag.search", "result": r})

    # Suggest an approval if keyword indicates action
    if any(k in q for k in ["post", "notify", "share"]):
        msg = f"Agent report for '{q}'"
        # Propose posting to Slack via approval
        a = call_tool(
            "/tools/approvals.propose",
            {"action": "post.slack", "subject": "agent", "payload": {"text": msg}},
        )
        out["proposed_approval"] = a

    return out


