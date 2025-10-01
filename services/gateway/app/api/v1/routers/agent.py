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

    # Optional LLM summary
    settings = get_settings()
    if settings.agent_llm_enabled and settings.openai_api_key:
        try:
            base = settings.openai_base_url or "https://api.openai.com/v1"
            model = settings.openai_model
            # Build a compact summary prompt from steps
            context_lines: list[str] = []
            for s in out.get("steps", [])[:5]:
                tool = s.get("tool")
                res = s.get("result")
                context_lines.append(f"{tool}: {str(res)[:800]}")
            prompt = (
                "You are an engineering manager assistant. Summarize the key metrics and risks, "
                "and suggest a next action in one short paragraph.\n" + "\n".join(context_lines)
            )
            headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
            with httpx.Client(timeout=30) as client:
                resp = client.post(
                    f"{base}/chat/completions",
                    headers=headers,
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": "You are concise and practical."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.2,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                summary = (
                    (data.get("choices") or [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
                out["summary"] = summary
        except Exception as exc:  # noqa: BLE001
            out["summary_error"] = str(exc)

    return out
