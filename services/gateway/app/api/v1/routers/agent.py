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
            if "assign" in query and "review" in query:
                # 1) candidates with no review
                rules = [{"kind": "pr_without_review", "older_than_hours": 12}]
                plan.append({"tool": "signals.evaluate", "rules": rules})
                sig = client.post("http://localhost:8000/v1/signals/evaluate", json={"rules": rules})
                sig.raise_for_status()
                sig_data = sig.json()
                no_review = (sig_data.get("results") or {}).get("pr_without_review") or []
                targets = [str(r.get("delivery_id") or r) for r in no_review[:20]]
                # Reviewer selection heuristic (placeholder)
                reviewer = payload.get("reviewer") or None
                team_reviewers: List[str] = []
                # Optional: suggest from CODEOWNERS if not provided
                try:
                    if ("codeowners" in query or not reviewer) and targets:
                        first = targets[0]
                        if "#" in first and "/" in first:
                            repo_part, num = first.split("#", 1)
                            owner, repo = repo_part.split("/", 1)
                            # fetch CODEOWNERS
                            gh = httpx.Client(timeout=10)
                            gh_token = os.getenv("GH_TOKEN") if hasattr(os, "getenv") else None
                            headers = {"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github+json"} if gh_token else {}
                            # try common paths
                            paths = [".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"]
                            codeowners_text = None
                            for p in paths:
                                rco = gh.get(f"https://api.github.com/repos/{owner}/{repo}/contents/{p}", headers=headers)
                                if rco.status_code == 200:
                                    co = rco.json()
                                    import base64
                                    codeowners_text = base64.b64decode(co.get("content") or b"").decode(errors="ignore")
                                    break
                            # get changed files
                            files = []
                            rf = gh.get(f"https://api.github.com/repos/{owner}/{repo}/pulls/{num}/files", headers=headers)
                            if rf.status_code == 200:
                                files = [f.get("filename") for f in rf.json()]
                            if codeowners_text and files:
                                # naive parse: pattern owners...; pick first matching owner
                                chosen_user = None
                                chosen_team = None
                                lines = [ln.strip() for ln in codeowners_text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
                                for fpath in files:
                                    for ln in lines:
                                        parts = ln.split()
                                        if len(parts) < 2:
                                            continue
                                        pattern, owners = parts[0], parts[1:]
                                        pat = pattern.replace("*", "")
                                        if pat and fpath.startswith(pat):
                                            for o in owners:
                                                if o.startswith("@"):
                                                    if "/" in o and not chosen_team:
                                                        chosen_team = o.split("/", 1)[1]
                                                    elif not chosen_user:
                                                        chosen_user = o[1:]
                                            if chosen_user or chosen_team:
                                                break
                                    if chosen_user or chosen_team:
                                        break
                                if not reviewer and chosen_user:
                                    reviewer = chosen_user
                                if chosen_team:
                                    team_reviewers = [chosen_team]
                except Exception:
                    pass
                approval = {
                    "subject": "pr:assign_reviewer",
                    "action": "assign_reviewer",
                    "reason": "Agent proposal to assign reviewer to PRs without review",
                    "payload": {"reviewer": reviewer or "", "team_reviewers": team_reviewers, "targets": targets},
                }
                plan.append({"tool": "approvals.propose", "payload": approval})
                prop = client.post("http://localhost:8000/v1/approvals/propose", json=approval)
                prop.raise_for_status()
                return {"plan": plan, "proposed": prop.json(), "candidates": len(targets)}
            if ("create" in query and "missing" in query and "ticket" in query) or ("create issues" in query and "ticket" in query):
                # Create GitHub issues for PRs missing ticket link
                rules = [{"kind": "no_ticket_link", "ticket_pattern": "[A-Z]+-[0-9]+"}]
                plan.append({"tool": "signals.evaluate", "rules": rules})
                sig = client.post("http://localhost:8000/v1/signals/evaluate", json={"rules": rules})
                sig.raise_for_status()
                sig_data = sig.json()
                results = (sig_data.get("results") or {}).get("no_ticket_link") or []
                targets = [str(r.get("delivery_id") or r) for r in results[:20]]
                approval = {
                    "subject": "pr:create_missing_ticket_issue",
                    "action": "issue_create",
                    "reason": "Agent proposal to create issues for PRs missing ticket link",
                    "payload": {"targets": targets},
                }
                plan.append({"tool": "approvals.propose", "payload": approval})
                prop = client.post("http://localhost:8000/v1/approvals/propose", json=approval)
                prop.raise_for_status()
                return {"plan": plan, "proposed": prop.json(), "candidates": len(targets)}
            if ("summarize" in query or "summary" in query) and ("pr" in query or "pull" in query):
                # Expect target pattern owner/repo#123 in query payload (optional param)
                target = payload.get("target") or ""
                # naive extract owner/repo#num from query
                import re
                m = re.search(r"([\w.-]+/[\w.-]+)#(\d+)", query)
                if m:
                    target = f"{m.group(1)}#{m.group(2)}"
                if not target:
                    raise HTTPException(status_code=400, detail="target like owner/repo#123 required")
                # Draft summary text (placeholder)
                draft = f"Draft summary for {target}: scope, changes, risks, next steps."
                approval = {
                    "subject": "pr:comment_summary",
                    "action": "comment_summary",
                    "reason": "Agent proposal to post PR summary comment",
                    "payload": {"target": target, "text": draft},
                }
                plan.append({"tool": "approvals.propose", "payload": approval})
                prop = client.post("http://localhost:8000/v1/approvals/propose", json=approval)
                prop.raise_for_status()
                return {"plan": plan, "proposed": prop.json(), "target": target}
            # default: RAG
            plan.append({"tool": "rag.search", "q": query})
            resp = client.post(mcp_url.rstrip("/") + "/tools/rag.search", json={"q": query, "top_k": 5})
            calls.append({"tool": "rag.search", "ok": resp.status_code < 300})
            return {"plan": plan, "result": resp.json()}
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
