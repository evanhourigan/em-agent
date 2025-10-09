from __future__ import annotations

from typing import Any, Dict, List

import httpx
from fastapi import APIRouter, HTTPException

from ....core.config import get_settings

router = APIRouter(prefix="/v1/agent", tags=["agent"])


@router.post("/run")
def run_agent(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Very minimal agent loop: plan -> call tools -> synthesize.
    payload: { query: str }
    """
    query = (payload.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query required")

    gw = get_settings()
    mcp_url = gw.rag_url.replace("rag", "mcp")  # heuristic for compose

    plan: List[Dict[str, Any]] = []
    calls: List[Dict[str, Any]] = []

    # naive router
    try:
        with httpx.Client(timeout=20) as client:
            if "sprint" in query and "health" in query:
                plan.append({"tool": "reports.sprint_health"})
                resp = client.post(mcp_url.rstrip("/") + "/tools/reports.sprint_health", json={})
                calls.append({"tool": "reports.sprint_health", "ok": resp.status_code < 300})
                data = resp.json()
                # Optional propose nudges if query asks
                if "nudge" in query or "dm" in query:
                    # Use signals rule to find PRs without review
                    rules = [{"kind": "pr_without_review", "older_than_hours": 12}]
                    plan.append({"tool": "signals.evaluate", "rules": rules})
                    sig = client.post("http://localhost:8000/v1/signals/evaluate", json={"rules": rules})
                    sig.raise_for_status()
                    sig_data = sig.json()
                    no_review = (sig_data.get("results") or {}).get("pr_without_review") or []
                    targets = [str(r.get("delivery_id") or r) for r in no_review[:20]]
                    approval = {
                        "subject": "pr:nudge_no_review",
                        "action": "nudge",
                        "reason": "Agent proposal to DM PR owners without review",
                        "payload": {"kind": "pr_without_review", "targets": targets},
                    }
                    plan.append({"tool": "approvals.propose", "payload": approval})
                    prop = client.post("http://localhost:8000/v1/approvals/propose", json=approval)
                    prop.raise_for_status()
                    return {"plan": plan, "report": data, "proposed": prop.json(), "candidates": len(targets)}
                return {"plan": plan, "report": data}
            if "stale" in query or "triage" in query:
                plan.append({"tool": "signals.evaluate", "rules": [{"kind": "stale_pr", "older_than_hours": 48}]})
                resp = client.post(mcp_url.rstrip("/") + "/tools/signals.evaluate", json={"rules": [{"kind": "stale_pr", "older_than_hours": 48}]})
                calls.append({"tool": "signals.evaluate", "ok": resp.status_code < 300})
                return {"plan": plan, "result": resp.json()}
            if ("label" in query and ("no ticket" in query or "missing ticket" in query)) or ("no_ticket" in query and "label" in query):
                # 1) find candidates via signals: no_ticket_link
                rules = [{"kind": "no_ticket_link", "ticket_pattern": "[A-Z]+-[0-9]+"}]
                plan.append({"tool": "signals.evaluate", "rules": rules})
                sig = client.post("http://localhost:8000/v1/signals/evaluate", json={"rules": rules})
                sig.raise_for_status()
                sig_data = sig.json()
                results = (sig_data.get("results") or {}).get("no_ticket_link") or []
                targets = [str(r.get("delivery_id") or r) for r in results[:20]]
                # 2) propose approval to add label
                approval = {
                    "subject": "pr:missing_ticket",
                    "action": "label",
                    "reason": "Agent proposal to mark PRs without ticket link",
                    "payload": {"label": "needs-ticket", "targets": targets},
                }
                plan.append({"tool": "approvals.propose", "payload": approval})
                prop = client.post("http://localhost:8000/v1/approvals/propose", json=approval)
                prop.raise_for_status()
                return {"plan": plan, "proposed": prop.json(), "candidates": len(targets)}
            # default: RAG
            plan.append({"tool": "rag.search", "q": query})
            resp = client.post(mcp_url.rstrip("/") + "/tools/rag.search", json={"q": query, "top_k": 5})
            calls.append({"tool": "rag.search", "ok": resp.status_code < 300})
            return {"plan": plan, "result": resp.json()}
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
