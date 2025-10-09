from __future__ import annotations

import os

import structlog
from celery import Celery
from sqlalchemy import create_engine, text
import json
import httpx


logger = structlog.get_logger(__name__)
redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")

app = Celery("em_workers", broker=redis_url, backend=redis_url)


def _get_engine():
    url = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@db:5432/postgres")
    return create_engine(url, pool_pre_ping=True)


@app.task(name="process_workflow_job")
def process_workflow_job(job_id: int) -> dict[str, str]:
    engine = _get_engine()
    with engine.begin() as conn:
        # Mark in-progress
        conn.execute(text("update workflow_jobs set status='running' where id=:id"), {"id": job_id})
        # Fetch payload to discover action
        row = conn.execute(text("select rule_kind, subject, payload from workflow_jobs where id=:id"), {"id": job_id}).mappings().first()
        action = (row or {}).get("rule_kind") or ""
        payload = (row or {}).get("payload") or "{}"
        try:
            data = json.loads(payload)
        except Exception:
            data = {}
        # Implement GitHub label action (best-effort)
        if action == "label":
            gh_token = os.getenv("GH_TOKEN")
            label = data.get("label")
            targets = data.get("targets") or []
            headers = {"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github+json"} if gh_token else {}
            for tgt in targets:
                # Expect target like owner/repo#123 or a delivery id mapping (simplified)
                if "#" in tgt and "/" in tgt:
                    repo_part, num = tgt.split("#", 1)
                    owner, repo = repo_part.split("/", 1)
                    try:
                        with httpx.Client(timeout=10, headers=headers) as client:
                            # apply label
                            client.post(f"https://api.github.com/repos/{owner}/{repo}/issues/{num}/labels", json={"labels": [label]})
                    except httpx.HTTPError:
                        continue
        # Implement Slack DM nudge action (best-effort)
        if action == "nudge":
            slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
            slack_token = os.getenv("SLACK_BOT_TOKEN")
            default_channel = os.getenv("SLACK_DEFAULT_CHANNEL")
            targets = data.get("targets") or []
            text = data.get("text") or "Gentle nudge: please take a look"
            if slack_webhook:
                for tgt in targets:
                    try:
                        with httpx.Client(timeout=10) as client:
                            client.post(slack_webhook, json={"text": f"{text}: {tgt}"})
                    except httpx.HTTPError:
                        continue
            elif slack_token and default_channel:
                headers = {"Authorization": f"Bearer {slack_token}"}
                for tgt in targets:
                    try:
                        with httpx.Client(timeout=10) as client:
                            client.post(
                                "https://slack.com/api/chat.postMessage",
                                headers=headers,
                                json={"channel": default_channel, "text": f"{text}: {tgt}"},
                            )
                    except httpx.HTTPError:
                        continue
        # Implement GitHub assign reviewer action
        if action == "assign_reviewer":
            gh_token = os.getenv("GH_TOKEN")
            reviewer = data.get("reviewer") or None
            team_reviewers = data.get("team_reviewers") or []
            targets = data.get("targets") or []
            headers = {"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github+json"} if gh_token else {}
            for tgt in targets:
                # Expect owner/repo#PR
                if "#" in tgt and "/" in tgt:
                    repo_part, num = tgt.split("#", 1)
                    owner, repo = repo_part.split("/", 1)
                    try:
                        with httpx.Client(timeout=10, headers=headers) as client:
                            payload = {}
                            if reviewer:
                                payload["reviewers"] = [reviewer]
                            if team_reviewers:
                                payload["team_reviewers"] = team_reviewers
                            if payload:
                                client.post(
                                    f"https://api.github.com/repos/{owner}/{repo}/pulls/{num}/requested_reviewers",
                                    json=payload,
                                )
                    except httpx.HTTPError:
                        continue
        if action == "issue_create":
            gh_token = os.getenv("GH_TOKEN")
            headers = {"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github+json"} if gh_token else {}
            targets = data.get("targets") or []
            for tgt in targets:
                if "#" in tgt and "/" in tgt:
                    repo_part, num = tgt.split("#", 1)
                    owner, repo = repo_part.split("/", 1)
                    title = f"Missing ticket link in PR #{num}"
                    body = "This PR appears to be missing a ticket reference. Please add one (e.g., ABC-123)."
                    try:
                        with httpx.Client(timeout=10, headers=headers) as client:
                            client.post(
                                f"https://api.github.com/repos/{owner}/{repo}/issues",
                                json={"title": title, "body": body},
                            )
                    except httpx.HTTPError:
                        continue
        # Implement PR summary comment
        if action == "comment_summary":
            gh_token = os.getenv("GH_TOKEN")
            headers = {"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github+json"} if gh_token else {}
            target = data.get("target") or ""
            text = data.get("text") or "PR summary"
            if "#" in target and "/" in target:
                repo_part, num = target.split("#", 1)
                owner, repo = repo_part.split("/", 1)
                try:
                    with httpx.Client(timeout=10, headers=headers) as client:
                        client.post(
                            f"https://api.github.com/repos/{owner}/{repo}/issues/{num}/comments",
                            json={"body": text},
                        )
                except httpx.HTTPError:
                    pass
        # Mark done
        conn.execute(text("update workflow_jobs set status='done' where id=:id"), {"id": job_id})
    logger.info("workflow.job.processed", id=job_id)
    return {"status": "done"}


