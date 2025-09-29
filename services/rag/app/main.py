from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def create_app() -> FastAPI:
    app = FastAPI(title="rag", version="0.2.0")

    # simple in-memory index with TF-IDF embeddings
    app.state.docs: List[Dict[str, Any]] = []
    app.state.vectorizer: Optional[TfidfVectorizer] = None
    app.state.doc_vectors = None  # sparse matrix

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
        # fit or update TF-IDF model
        texts = [d["content"] for d in app.state.docs]
        if app.state.vectorizer is None:
            app.state.vectorizer = TfidfVectorizer(stop_words="english")
            app.state.doc_vectors = app.state.vectorizer.fit_transform(texts)
        else:
            # Refit on full corpus for simplicity (sufficient for demo)
            app.state.doc_vectors = app.state.vectorizer.fit_transform(texts)
        return {"indexed": doc_id}

    @app.post("/search")
    def search(payload: Dict[str, Any]) -> Dict[str, Any]:
        query = payload.get("q", "").lower()
        if not query:
            raise HTTPException(status_code=400, detail="q required")
        if not app.state.docs:
            return {"results": []}
        if app.state.vectorizer is None or app.state.doc_vectors is None:
            # fall back to substring search
            results = [d for d in app.state.docs if query in d["content"].lower()]
            return {"results": results[:20]}
        q_vec = app.state.vectorizer.transform([query])
        sims = cosine_similarity(q_vec, app.state.doc_vectors)[0]
        ranked = sorted(zip(app.state.docs, sims), key=lambda x: x[1], reverse=True)
        topk = [dict(doc, score=float(score)) for doc, score in ranked[:20]]
        return {"results": topk}

    return app


app = create_app()
