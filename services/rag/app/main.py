from __future__ import annotations

from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException


def create_app() -> FastAPI:
    app = FastAPI(title="rag", version="0.1.0")

    # simple in-memory index for demo
    app.state.docs: List[Dict[str, Any]] = []

    @app.get("/")
    def root() -> Dict[str, Any]:
        return {"service": "rag", "status": "ok"}

    @app.get("/health")
    def health() -> Dict[str, Any]:
        return {"status": "ok"}

    @app.post("/index")
    def index(payload: Dict[str, Any]) -> Dict[str, Any]:
        doc_id = payload.get("id")
        content = payload.get("content")
        if not doc_id or not content:
            raise HTTPException(status_code=400, detail="id and content required")
        app.state.docs.append({"id": doc_id, "content": content})
        return {"indexed": doc_id}

    @app.post("/search")
    def search(payload: Dict[str, Any]) -> Dict[str, Any]:
        query = payload.get("q", "").lower()
        if not query:
            raise HTTPException(status_code=400, detail="q required")
        results = [d for d in app.state.docs if query in d["content"].lower()]
        return {"results": results[:20]}

    return app


app = create_app()


