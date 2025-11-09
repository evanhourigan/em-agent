from __future__ import annotations

import base64
import os
import re
import time
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException


def create_app() -> FastAPI:
    app = FastAPI(title="connectors", version="0.1.0")

    gateway_url = os.getenv("GATEWAY_URL", "http://gateway:8000").rstrip("/")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok"}

    @app.post("/ingest/docs")
    def ingest_docs(payload: dict[str, Any]) -> dict[str, Any]:
        """Accepts { docs: [{id, content, meta}], chunk_size?, overlap? } and forwards to RAG bulk index via gateway."""
        docs: list[dict[str, Any]] = payload.get("docs") or []
        if not isinstance(docs, list) or not docs:
            raise HTTPException(status_code=400, detail="docs required")
        chunk_size = int(payload.get("chunk_size", 800))
        overlap = int(payload.get("overlap", 100))
        body = {"docs": docs, "chunk_size": chunk_size, "overlap": overlap}
        try:
            with httpx.Client(timeout=20) as client:
                resp = client.post(f"{gateway_url}/v1/rag/index/bulk", json=body)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @app.post("/ingest/doc")
    def ingest_doc(payload: dict[str, Any]) -> dict[str, Any]:
        """Accepts single { id, content, meta } and forwards to RAG index via gateway."""
        if not payload.get("id") or not payload.get("content"):
            raise HTTPException(status_code=400, detail="id and content required")
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(f"{gateway_url}/v1/rag/index", json=payload)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    # --- Helpers ---
    def _strip_markup(text: str) -> str:
        # very simple HTML-ish tag stripper
        return re.sub(r"<[^>]+>", " ", text)

    # --- Crawlers ---
    @app.post("/crawl/confluence")
    def crawl_confluence(payload: dict[str, Any]) -> dict[str, Any]:
        """Crawl Confluence pages by IDs and forward as docs.

        payload: { base_url: str, page_ids: ["123","456"], chunk_size?, overlap? }
        Auth via env: CONFLUENCE_EMAIL, CONFLUENCE_TOKEN
        """
        base_url = (payload.get("base_url") or "").rstrip("/")
        page_ids: list[str] = payload.get("page_ids") or []
        if not base_url or not page_ids:
            raise HTTPException(
                status_code=400, detail="base_url and page_ids required"
            )
        email = os.getenv("CONFLUENCE_EMAIL")
        token = os.getenv("CONFLUENCE_TOKEN")
        if not email or not token:
            raise HTTPException(
                status_code=400, detail="CONFLUENCE_EMAIL/CONFLUENCE_TOKEN not set"
            )
        docs: list[dict[str, Any]] = []
        auth = (email, token)

        # Basic retry/backoff
        def _get(client: httpx.Client, url: str, **kwargs):
            backoff = 0.5
            for _ in range(4):
                try:
                    r = client.get(url, **kwargs)
                    if r.status_code in (429, 500, 502, 503, 504):
                        time.sleep(backoff)
                        backoff *= 2
                        continue
                    return r
                except httpx.HTTPError:
                    time.sleep(backoff)
                    backoff *= 2
            raise HTTPException(
                status_code=502, detail=f"GET failed after retries: {url}"
            )

        since = payload.get("if_modified_since")  # RFC1123 string optional
        headers = {"If-Modified-Since": since} if since else {}
        with httpx.Client(timeout=20, headers=headers) as client:
            for pid in page_ids:
                try:
                    resp = _get(
                        client,
                        f"{base_url}/wiki/api/v2/pages/{pid}?body-format=storage",
                        auth=auth,
                    )
                    if resp.status_code == 404:
                        # fallback to older API
                        resp = _get(
                            client,
                            f"{base_url}/rest/api/content/{pid}?expand=body.storage",
                            auth=auth,
                        )
                    if resp.status_code == 304:
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    title = (
                        data.get("title")
                        or data.get("body", {}).get("title")
                        or f"page-{pid}"
                    )
                    storage = (
                        data.get("body", {}).get("storage", {}).get("value")
                        or data.get("body", {}).get("value")
                        or ""
                    )
                    content = _strip_markup(storage)
                    url = data.get("_links", {}).get("webui") or data.get(
                        "_links", {}
                    ).get("self")
                    if url and url.startswith("/"):
                        url = base_url + url
                    doc_id = f"confluence:{pid}"
                    docs.append(
                        {
                            "id": doc_id,
                            "content": f"{title}\n\n{content}",
                            "meta": {
                                "source": "confluence",
                                "url": url,
                                "title": title,
                            },
                        }
                    )
                except httpx.HTTPError:
                    # skip problematic page
                    continue
        if not docs:
            return {"indexed": 0}
        chunk_size = int(payload.get("chunk_size", 800))
        overlap = int(payload.get("overlap", 100))
        return ingest_docs({"docs": docs, "chunk_size": chunk_size, "overlap": overlap})

    @app.post("/crawl/github")
    def crawl_github(payload: dict[str, Any]) -> dict[str, Any]:
        """Crawl GitHub repo files and forward as docs.

        payload: { owner, repo, ref?, include_paths?: ["docs/","README.md"], exts?: [".md", ".txt"], chunk_size?, overlap? }
        Auth via env: GH_TOKEN (optional for private/rate-limit)
        """
        owner = payload.get("owner")
        repo = payload.get("repo")
        if not owner or not repo:
            raise HTTPException(status_code=400, detail="owner and repo required")
        ref = payload.get("ref") or "main"
        include_paths: list[str] = payload.get("include_paths") or []
        exts: set[str] = set(payload.get("exts") or [".md", ".txt", ".rst"])
        headers = {}
        if os.getenv("GH_TOKEN"):
            headers["Authorization"] = f"Bearer {os.getenv('GH_TOKEN')}"
        docs: list[dict[str, Any]] = []
        # Delta: If-Modified-Since / ETag support
        since = payload.get("if_modified_since")  # RFC1123
        etag = payload.get("etag")
        if since:
            headers["If-Modified-Since"] = since
        if etag:
            headers["If-None-Match"] = etag

        def _get(client: httpx.Client, url: str, **kwargs):
            backoff = 0.5
            for _ in range(4):
                try:
                    r = client.get(url, **kwargs)
                    if r.status_code in (429, 500, 502, 503, 504):
                        time.sleep(backoff)
                        backoff *= 2
                        continue
                    return r
                except httpx.HTTPError:
                    time.sleep(backoff)
                    backoff *= 2
            raise HTTPException(
                status_code=502, detail=f"GET failed after retries: {url}"
            )

        with httpx.Client(timeout=30, headers=headers) as client:
            # Get tree
            r = _get(
                client,
                f"https://api.github.com/repos/{owner}/{repo}/git/trees/{ref}?recursive=1",
            )
            r.raise_for_status()
            tree = r.json().get("tree", [])
            for node in tree:
                if node.get("type") != "blob":
                    continue
                path = node.get("path") or ""
                if include_paths and not any(path.startswith(p) for p in include_paths):
                    continue
                if exts and not any(path.lower().endswith(e) for e in exts):
                    continue
                try:
                    c = _get(
                        client,
                        f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={ref}",
                    )
                    if c.status_code == 304:
                        continue
                    c.raise_for_status()
                    meta_json = c.json()
                    if meta_json.get("encoding") == "base64":
                        raw = base64.b64decode(meta_json.get("content", "")).decode(
                            "utf-8", errors="ignore"
                        )
                    else:
                        raw = meta_json.get("content", "")
                    # Prefer text for markdown-like files; else skip binaries
                    if not raw:
                        continue
                    docs.append(
                        {
                            "id": f"gh:{owner}/{repo}:{path}",
                            "content": raw,
                            "meta": {
                                "source": "github",
                                "url": meta_json.get("html_url"),
                                "path": path,
                                "ref": ref,
                                "etag": c.headers.get("ETag"),
                            },
                        }
                    )
                except httpx.HTTPError:
                    continue
        if not docs:
            return {"indexed": 0}
        chunk_size = int(payload.get("chunk_size", 800))
        overlap = int(payload.get("overlap", 100))
        return ingest_docs({"docs": docs, "chunk_size": chunk_size, "overlap": overlap})

    @app.post("/crawl/shortcut")
    def crawl_shortcut(payload: dict[str, Any]) -> dict[str, Any]:
        """Crawl Shortcut stories and forward as docs for RAG indexing.

        payload: { workspace_slug?, state_ids?: ["500000001"], iteration_id?, chunk_size?, overlap? }
        Auth via env: SHORTCUT_API_TOKEN

        This crawls stories from Shortcut (formerly Clubhouse) for knowledge base indexing.
        Useful for searching past decisions, epics, requirements, etc.
        """
        api_token = os.getenv("SHORTCUT_API_TOKEN")
        if not api_token:
            raise HTTPException(status_code=400, detail="SHORTCUT_API_TOKEN not set")

        # Shortcut API v3
        base_url = "https://api.app.shortcut.com/api/v3"
        headers = {"Shortcut-Token": api_token, "Content-Type": "application/json"}

        # Filter options
        state_ids = payload.get("state_ids") or []  # Filter by workflow state
        iteration_id = payload.get("iteration_id")  # Filter by iteration/sprint

        docs: list[dict[str, Any]] = []

        def _get(client: httpx.Client, url: str, **kwargs):
            """Retry helper with exponential backoff"""
            backoff = 0.5
            for _ in range(4):
                try:
                    r = client.get(url, **kwargs)
                    if r.status_code in (429, 500, 502, 503, 504):
                        time.sleep(backoff)
                        backoff *= 2
                        continue
                    return r
                except httpx.HTTPError:
                    time.sleep(backoff)
                    backoff *= 2
            raise HTTPException(status_code=502, detail=f"GET failed: {url}")

        with httpx.Client(timeout=30, headers=headers) as client:
            # Search stories with filters
            search_payload: dict[str, Any] = {"page_size": 25}
            if state_ids:
                search_payload["workflow_state_ids"] = state_ids
            if iteration_id:
                search_payload["iteration_ids"] = [iteration_id]

            try:
                # Shortcut Search API
                resp = client.post(
                    f"{base_url}/search/stories", json=search_payload, headers=headers
                )
                resp.raise_for_status()
                data = resp.json()

                stories = data.get("data", [])
                for story in stories:
                    story_id = story.get("id")
                    name = story.get("name", "Untitled")
                    description = story.get("description", "")
                    story_type = story.get("story_type", "feature")
                    state = story.get("workflow_state_id")
                    url = story.get("app_url", "")

                    # Combine title and description for indexing
                    content = f"# {name}\n\n{description}"

                    # Add comments if available
                    comments = story.get("comments", [])
                    if comments:
                        content += "\n\n## Comments\n\n"
                        for comment in comments:
                            author = comment.get("author_id", "Unknown")
                            text = comment.get("text", "")
                            content += f"**{author}**: {text}\n\n"

                    doc_id = f"shortcut:story:{story_id}"
                    docs.append(
                        {
                            "id": doc_id,
                            "content": _strip_markup(content),
                            "meta": {
                                "source": "shortcut",
                                "url": url,
                                "title": name,
                                "story_type": story_type,
                                "state": str(state),
                            },
                        }
                    )

            except httpx.HTTPError as exc:
                raise HTTPException(
                    status_code=502, detail=f"Shortcut API error: {exc}"
                )

        if not docs:
            return {"indexed": 0}

        chunk_size = int(payload.get("chunk_size", 800))
        overlap = int(payload.get("overlap", 100))
        return ingest_docs({"docs": docs, "chunk_size": chunk_size, "overlap": overlap})

    @app.post("/crawl/linear")
    def crawl_linear(payload: dict[str, Any]) -> dict[str, Any]:
        """Crawl Linear issues and forward as docs for RAG indexing.

        payload: { team_id?, state_ids?: ["started","completed"], limit?: 50, chunk_size?, overlap? }
        Auth via env: LINEAR_API_KEY

        This crawls issues from Linear for knowledge base indexing.
        Useful for searching past decisions, requirements, discussions, etc.
        """
        api_key = os.getenv("LINEAR_API_KEY")
        if not api_key:
            raise HTTPException(status_code=400, detail="LINEAR_API_KEY not set")

        # Linear GraphQL API
        graphql_url = "https://api.linear.app/graphql"
        headers = {"Authorization": api_key, "Content-Type": "application/json"}

        # Filter options
        team_id = payload.get("team_id")  # Filter by team
        state_ids = payload.get("state_ids") or []  # Filter by state (started, completed, etc.)
        limit = int(payload.get("limit", 50))  # Max issues to fetch

        docs: list[dict[str, Any]] = []

        def _post(client: httpx.Client, url: str, **kwargs):
            """Retry helper with exponential backoff"""
            backoff = 0.5
            for _ in range(4):
                try:
                    r = client.post(url, **kwargs)
                    if r.status_code in (429, 500, 502, 503, 504):
                        time.sleep(backoff)
                        backoff *= 2
                        continue
                    return r
                except httpx.HTTPError:
                    time.sleep(backoff)
                    backoff *= 2
            raise HTTPException(status_code=502, detail=f"POST failed: {url}")

        with httpx.Client(timeout=30, headers=headers) as client:
            # Build GraphQL query with filters
            # Linear uses GraphQL for all queries
            filters = []
            if team_id:
                filters.append(f'team: {{ id: {{ eq: "{team_id}" }} }}')
            if state_ids:
                state_filter = ", ".join([f'"{s}"' for s in state_ids])
                filters.append(f"state: {{ name: {{ in: [{state_filter}] }} }}")

            filter_clause = ", ".join(filters) if filters else ""
            filter_arg = f"filter: {{ {filter_clause} }}" if filter_clause else ""

            query = f"""
            query {{
              issues({filter_arg}, first: {limit}) {{
                nodes {{
                  id
                  identifier
                  title
                  description
                  state {{
                    name
                  }}
                  priority
                  url
                  createdAt
                  updatedAt
                  team {{
                    name
                  }}
                  assignee {{
                    name
                  }}
                  comments {{
                    nodes {{
                      body
                      user {{
                        name
                      }}
                      createdAt
                    }}
                  }}
                }}
              }}
            }}
            """

            try:
                # Execute GraphQL query
                resp = _post(client, graphql_url, json={"query": query}, headers=headers)
                resp.raise_for_status()
                data = resp.json()

                # Check for GraphQL errors
                if "errors" in data:
                    error_msg = "; ".join([e.get("message", "") for e in data["errors"]])
                    raise HTTPException(
                        status_code=502, detail=f"Linear GraphQL error: {error_msg}"
                    )

                issues = data.get("data", {}).get("issues", {}).get("nodes", [])
                for issue in issues:
                    issue_id = issue.get("id", "")
                    identifier = issue.get("identifier", "")
                    title = issue.get("title", "Untitled")
                    description = issue.get("description", "")
                    state = issue.get("state", {}).get("name", "unknown")
                    priority = issue.get("priority", 0)
                    url = issue.get("url", "")
                    team = issue.get("team", {}).get("name", "")
                    assignee = issue.get("assignee", {}).get("name", "")

                    # Combine title and description for indexing
                    content = f"# {identifier}: {title}\n\n{description}"

                    # Add metadata
                    content += f"\n\n**Team:** {team}\n**State:** {state}\n**Priority:** {priority}"
                    if assignee:
                        content += f"\n**Assignee:** {assignee}"

                    # Add comments if available
                    comments = issue.get("comments", {}).get("nodes", [])
                    if comments:
                        content += "\n\n## Comments\n\n"
                        for comment in comments:
                            user = comment.get("user", {}).get("name", "Unknown")
                            body = comment.get("body", "")
                            content += f"**{user}**: {body}\n\n"

                    doc_id = f"linear:issue:{issue_id}"
                    docs.append(
                        {
                            "id": doc_id,
                            "content": _strip_markup(content),
                            "meta": {
                                "source": "linear",
                                "url": url,
                                "title": f"{identifier}: {title}",
                                "identifier": identifier,
                                "state": state,
                                "team": team,
                                "priority": str(priority),
                            },
                        }
                    )

            except httpx.HTTPError as exc:
                raise HTTPException(
                    status_code=502, detail=f"Linear API error: {exc}"
                )

        if not docs:
            return {"indexed": 0}

        chunk_size = int(payload.get("chunk_size", 800))
        overlap = int(payload.get("overlap", 100))
        return ingest_docs({"docs": docs, "chunk_size": chunk_size, "overlap": overlap})

    @app.post("/crawl/pagerduty")
    def crawl_pagerduty(payload: dict[str, Any]) -> dict[str, Any]:
        """Crawl PagerDuty incidents and forward as docs for RAG indexing.

        payload: { statuses?: ["triggered","acknowledged","resolved"], limit?: 100, chunk_size?, overlap? }
        Auth via env: PAGERDUTY_API_TOKEN

        This crawls incidents from PagerDuty for knowledge base indexing.
        Useful for searching past incidents, post-mortems, resolution patterns, etc.
        """
        api_token = os.getenv("PAGERDUTY_API_TOKEN")
        if not api_token:
            raise HTTPException(status_code=400, detail="PAGERDUTY_API_TOKEN not set")

        # PagerDuty REST API v2
        base_url = "https://api.pagerduty.com"
        headers = {
            "Authorization": f"Token token={api_token}",
            "Accept": "application/vnd.pagerduty+json;version=2",
            "Content-Type": "application/json",
        }

        # Filter options
        statuses = payload.get("statuses") or ["triggered", "acknowledged", "resolved"]
        limit = int(payload.get("limit", 100))  # Max incidents to fetch

        docs: list[dict[str, Any]] = []

        def _get(client: httpx.Client, url: str, **kwargs):
            """Retry helper with exponential backoff"""
            backoff = 0.5
            for _ in range(4):
                try:
                    r = client.get(url, **kwargs)
                    if r.status_code in (429, 500, 502, 503, 504):
                        time.sleep(backoff)
                        backoff *= 2
                        continue
                    return r
                except httpx.HTTPError:
                    time.sleep(backoff)
                    backoff *= 2
            raise HTTPException(status_code=502, detail=f"GET failed: {url}")

        with httpx.Client(timeout=30, headers=headers) as client:
            # Build query parameters
            params = {"statuses[]": statuses, "limit": min(limit, 100)}  # API max is 100

            try:
                # Fetch incidents
                resp = _get(client, f"{base_url}/incidents", params=params)
                resp.raise_for_status()
                data = resp.json()

                incidents = data.get("incidents", [])
                for incident in incidents:
                    incident_id = incident.get("id", "")
                    incident_number = incident.get("incident_number", 0)
                    title = incident.get("title", "Untitled incident")
                    description = incident.get("description", "")
                    status = incident.get("status", "unknown")
                    urgency = incident.get("urgency", "unknown")
                    created_at = incident.get("created_at", "")
                    html_url = incident.get("html_url", "")

                    # Get service info
                    service = incident.get("service", {})
                    service_name = service.get("summary", "Unknown service")

                    # Get assignment info
                    assignments = incident.get("assignments", [])
                    assignees = [a.get("assignee", {}).get("summary", "") for a in assignments]

                    # Combine title and description for indexing
                    content = f"# Incident #{incident_number}: {title}\n\n{description}"

                    # Add metadata
                    content += f"\n\n**Service:** {service_name}\n**Status:** {status}\n**Urgency:** {urgency}"
                    if assignees:
                        content += f"\n**Assigned to:** {', '.join(assignees)}"
                    content += f"\n**Created:** {created_at}"

                    # Fetch incident notes (for post-mortem content)
                    try:
                        notes_resp = _get(
                            client, f"{base_url}/incidents/{incident_id}/notes"
                        )
                        if notes_resp.status_code == 200:
                            notes_data = notes_resp.json()
                            notes = notes_data.get("notes", [])
                            if notes:
                                content += "\n\n## Notes\n\n"
                                for note in notes:
                                    note_content = note.get("content", "")
                                    note_user = note.get("user", {}).get("summary", "Unknown")
                                    content += f"**{note_user}**: {note_content}\n\n"
                    except Exception:
                        # Skip notes if they fail to fetch
                        pass

                    doc_id = f"pagerduty:incident:{incident_id}"
                    docs.append(
                        {
                            "id": doc_id,
                            "content": _strip_markup(content),
                            "meta": {
                                "source": "pagerduty",
                                "url": html_url,
                                "title": f"Incident #{incident_number}: {title}",
                                "incident_number": str(incident_number),
                                "status": status,
                                "urgency": urgency,
                                "service": service_name,
                            },
                        }
                    )

            except httpx.HTTPError as exc:
                raise HTTPException(
                    status_code=502, detail=f"PagerDuty API error: {exc}"
                )

        if not docs:
            return {"indexed": 0}

        chunk_size = int(payload.get("chunk_size", 800))
        overlap = int(payload.get("overlap", 100))
        return ingest_docs({"docs": docs, "chunk_size": chunk_size, "overlap": overlap})

    # Optional simple scheduler for periodic crawls
    import threading

    class Scheduler(threading.Thread):
        def __init__(self) -> None:
            super().__init__(daemon=True)
            self._stop = threading.Event()

        def run(self) -> None:  # pragma: no cover
            interval = int(os.getenv("CRAWLER_INTERVAL_SEC", "0") or 0)
            if interval <= 0:
                return
            while not self._stop.is_set():
                # Example: run GitHub crawl if env configured
                try:
                    owner = os.getenv("CRAWL_GH_OWNER")
                    repo = os.getenv("CRAWL_GH_REPO")
                    if owner and repo:
                        try:
                            crawl_github(
                                {
                                    "owner": owner,
                                    "repo": repo,
                                    "include_paths": ["docs/", "README.md"],
                                }
                            )
                        except Exception:
                            pass
                finally:
                    self._stop.wait(interval)

        def stop(self) -> None:
            self._stop.set()

    sched = Scheduler()
    sched.start()

    return app


app = create_app()
