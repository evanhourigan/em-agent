from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

try:
    from sentence_transformers import SentenceTransformer  # type: ignore

    _HAS_ST = True
except Exception:  # pragma: no cover - optional dependency
    _HAS_ST = False


def create_app() -> FastAPI:
    app = FastAPI(title="rag", version="0.3.0")

    # Backend selection: tfidf (default) or st (Sentence-Transformers)
    app.state.backend: str = os.getenv("EMBEDDINGS_BACKEND", "tfidf").lower()

    # In-memory index of chunks: each doc is { id, content, parent_id, meta }
    app.state.docs: List[Dict[str, Any]] = []

    # TF-IDF state
    app.state.vectorizer: Optional[TfidfVectorizer] = None
    app.state.doc_vectors = None  # sparse matrix

    # Sentence-Transformers state
    app.state.st_model = None
    app.state.st_doc_vectors = None  # dense numpy array

    @app.get("/")
    def root() -> Dict[str, Any]:
        return {"service": "rag", "status": "ok"}

    @app.get("/health")
    def health() -> Dict[str, Any]:
        return {
            "status": "ok",
            "backend": app.state.backend,
            "doc_count": len(app.state.docs),
        }

    def _chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
        if chunk_size <= 0:
            return [text]
        chunks: List[str] = []
        n = len(text)
        start = 0
        step = max(1, chunk_size - max(0, overlap))
        while start < n:
            end = min(n, start + chunk_size)
            chunks.append(text[start:end])
            if end >= n:
                break
            start += step
        return chunks

    def _rebuild_embeddings() -> None:
        texts = [d["content"] for d in app.state.docs]
        if app.state.backend == "st":
            if not _HAS_ST:
                raise HTTPException(
                    status_code=500, detail="sentence-transformers not available"
                )
            if app.state.st_model is None:
                app.state.st_model = SentenceTransformer(
                    "sentence-transformers/all-MiniLM-L6-v2"
                )
            app.state.st_doc_vectors = app.state.st_model.encode(
                texts, normalize_embeddings=True
            )
            return
        if app.state.vectorizer is None:
            app.state.vectorizer = TfidfVectorizer(stop_words="english")
            app.state.doc_vectors = app.state.vectorizer.fit_transform(texts)
        else:
            app.state.doc_vectors = app.state.vectorizer.fit_transform(texts)

    @app.post("/reset")
    def reset() -> Dict[str, Any]:
        app.state.docs = []
        app.state.vectorizer = None
        app.state.doc_vectors = None
        app.state.st_model = app.state.st_model  # keep model cached if present
        app.state.st_doc_vectors = None
        return {"reset": True}

    @app.post("/index")
    def index(payload: Dict[str, Any]) -> Dict[str, Any]:
        doc_id = payload.get("id")
        content = payload.get("content")
        meta = payload.get("meta")
        if not doc_id or not content:
            raise HTTPException(status_code=400, detail="id and content required")
        app.state.docs.append(
            {"id": doc_id, "content": content, "parent_id": doc_id, "meta": meta}
        )
        _rebuild_embeddings()
        return {"indexed": doc_id}

    @app.post("/index/bulk")
    def index_bulk(payload: Dict[str, Any]) -> Dict[str, Any]:
        docs = payload.get("docs") or []
        if not isinstance(docs, list) or not docs:
            raise HTTPException(status_code=400, detail="docs required")
        chunk_size = int(payload.get("chunk_size", 800))
        overlap = int(payload.get("overlap", 100))
        added = 0
        for d in docs:
            doc_id = d.get("id")
            content = d.get("content")
            meta = d.get("meta")
            if not doc_id or not content:
                continue
            chunks = _chunk_text(content, chunk_size, overlap)
            if len(chunks) == 1:
                app.state.docs.append(
                    {
                        "id": doc_id,
                        "content": chunks[0],
                        "parent_id": doc_id,
                        "meta": meta,
                    }
                )
                added += 1
            else:
                for idx, ch in enumerate(chunks):
                    chunk_id = f"{doc_id}#c{idx}"
                    app.state.docs.append(
                        {
                            "id": chunk_id,
                            "content": ch,
                            "parent_id": doc_id,
                            "meta": meta,
                        }
                    )
                    added += 1
        _rebuild_embeddings()
        return {"indexed": added}

    @app.post("/search")
    def search(payload: Dict[str, Any]) -> Dict[str, Any]:
        query = payload.get("q", "").lower()
        top_k = int(payload.get("top_k", 5))
        if not query:
            raise HTTPException(status_code=400, detail="q required")
        if not app.state.docs:
            return {"results": []}
        # Sentence-Transformers path
        if app.state.backend == "st":
            if app.state.st_model is None or app.state.st_doc_vectors is None:
                # fall back to substring search when not ready
                results = [d for d in app.state.docs if query in d["content"].lower()]
                out = [
                    {
                        "id": d["id"],
                        "parent_id": d.get("parent_id"),
                        "score": None,
                        "snippet": d["content"][:200],
                        "meta": d.get("meta"),
                    }
                    for d in results[:top_k]
                ]
                return {"results": out}
            q_vec = app.state.st_model.encode([query], normalize_embeddings=True)
            # cosine similarity = dot product on normalized vectors
            import numpy as np  # local import to avoid global dependency when unused

            sims = (q_vec @ app.state.st_doc_vectors.T)[0]
            ranked: List[Tuple[Dict[str, Any], float]] = sorted(
                zip(app.state.docs, sims.tolist()), key=lambda x: x[1], reverse=True
            )
            out = [
                {
                    "id": doc["id"],
                    "parent_id": doc.get("parent_id"),
                    "score": float(score),
                    "snippet": doc["content"][:200],
                    "meta": doc.get("meta"),
                }
                for doc, score in ranked[:top_k]
            ]
            return {"results": out}

        # TF-IDF path (default)
        if app.state.vectorizer is None or app.state.doc_vectors is None:
            results = [d for d in app.state.docs if query in d["content"].lower()]
            out = [
                {
                    "id": d["id"],
                    "parent_id": d.get("parent_id"),
                    "score": None,
                    "snippet": d["content"][:200],
                    "meta": d.get("meta"),
                }
                for d in results[:top_k]
            ]
            return {"results": out}
        q_vec = app.state.vectorizer.transform([query])
        sims = cosine_similarity(q_vec, app.state.doc_vectors)[0]
        ranked = sorted(zip(app.state.docs, sims), key=lambda x: x[1], reverse=True)
        out = [
            {
                "id": doc["id"],
                "parent_id": doc.get("parent_id"),
                "score": float(score),
                "snippet": doc["content"][:200],
                "meta": doc.get("meta"),
            }
            for doc, score in ranked[:top_k]
        ]
        return {"results": out}

    return app


app = create_app()
