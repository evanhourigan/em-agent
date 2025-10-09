from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

import os
import httpx
from fastapi import FastAPI, HTTPException
import base64
import re


def create_app() -> FastAPI:
    app = FastAPI(title="connectors", version="0.1.0")

    gateway_url = os.getenv("GATEWAY_URL", "http://gateway:8000").rstrip("/")

    @app.get("/health")
    def health() -> Dict[str, Any]:
        return {"status": "ok"}

    @app.post("/ingest/docs")
    def ingest_docs(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Accepts { docs: [{id, content, meta}], chunk_size?, overlap? } and forwards to RAG bulk index via gateway.
        """
        docs: List[Dict[str, Any]] = payload.get("docs") or []
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
    def ingest_doc(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Accepts single { id, content, meta } and forwards to RAG index via gateway.
        """
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
    def crawl_confluence(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Crawl Confluence pages by IDs and forward as docs.

        payload: { base_url: str, page_ids: ["123","456"], chunk_size?, overlap? }
        Auth via env: CONFLUENCE_EMAIL, CONFLUENCE_TOKEN
        """
        base_url = (payload.get("base_url") or "").rstrip("/")
        page_ids: List[str] = payload.get("page_ids") or []
        if not base_url or not page_ids:
            raise HTTPException(status_code=400, detail="base_url and page_ids required")
        email = os.getenv("CONFLUENCE_EMAIL")
        token = os.getenv("CONFLUENCE_TOKEN")
        if not email or not token:
            raise HTTPException(status_code=400, detail="CONFLUENCE_EMAIL/CONFLUENCE_TOKEN not set")
        docs: List[Dict[str, Any]] = []
        auth = (email, token)
        with httpx.Client(timeout=20) as client:
            for pid in page_ids:
                try:
                    resp = client.get(
                        f"{base_url}/wiki/api/v2/pages/{pid}?body-format=storage",
                        auth=auth,
                    )
                    if resp.status_code == 404:
                        # fallback to older API
                        resp = client.get(
                            f"{base_url}/rest/api/content/{pid}?expand=body.storage",
                            auth=auth,
                        )
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
                    url = data.get("_links", {}).get("webui") or data.get("_links", {}).get("self")
                    if url and url.startswith("/"):
                        url = base_url + url
                    doc_id = f"confluence:{pid}"
                    docs.append({
                        "id": doc_id,
                        "content": f"{title}\n\n{content}",
                        "meta": {"source": "confluence", "url": url, "title": title},
                    })
                except httpx.HTTPError as exc:
                    # skip problematic page
                    continue
        if not docs:
            return {"indexed": 0}
        chunk_size = int(payload.get("chunk_size", 800))
        overlap = int(payload.get("overlap", 100))
        return ingest_docs({"docs": docs, "chunk_size": chunk_size, "overlap": overlap})

    @app.post("/crawl/github")
    def crawl_github(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Crawl GitHub repo files and forward as docs.

        payload: { owner, repo, ref?, include_paths?: ["docs/","README.md"], exts?: [".md", ".txt"], chunk_size?, overlap? }
        Auth via env: GH_TOKEN (optional for private/rate-limit)
        """
        owner = payload.get("owner")
        repo = payload.get("repo")
        if not owner or not repo:
            raise HTTPException(status_code=400, detail="owner and repo required")
        ref = payload.get("ref") or "main"
        include_paths: List[str] = payload.get("include_paths") or []
        exts: Set[str] = set(payload.get("exts") or [".md", ".txt", ".rst"])
        headers = {}
        if os.getenv("GH_TOKEN"):
            headers["Authorization"] = f"Bearer {os.getenv('GH_TOKEN')}"
        docs: List[Dict[str, Any]] = []
        with httpx.Client(timeout=30, headers=headers) as client:
            # Get tree
            r = client.get(
                f"https://api.github.com/repos/{owner}/{repo}/git/trees/{ref}?recursive=1"
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
                    c = client.get(
                        f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={ref}"
                    )
                    c.raise_for_status()
                    meta_json = c.json()
                    if meta_json.get("encoding") == "base64":
                        raw = base64.b64decode(meta_json.get("content", "")).decode(
                            "utf-8", errors="ignore"
                        )
                    else:
                        raw = meta_json.get("content", "")
                    docs.append(
                        {
                            "id": f"gh:{owner}/{repo}:{path}",
                            "content": raw,
                            "meta": {
                                "source": "github",
                                "url": meta_json.get("html_url"),
                                "path": path,
                                "ref": ref,
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

    return app


app = create_app()


