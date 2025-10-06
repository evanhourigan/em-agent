from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

import psycopg
from fastapi import FastAPI, HTTPException

try:
    from opentelemetry import trace  # type: ignore
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )  # type: ignore
    from opentelemetry.instrumentation.fastapi import (
        FastAPIInstrumentor,
    )  # type: ignore
    from opentelemetry.sdk.resources import Resource  # type: ignore
    from opentelemetry.sdk.trace import TracerProvider  # type: ignore
    from opentelemetry.sdk.trace.export import (  # type: ignore
        BatchSpanProcessor,
        ConsoleSpanExporter,
        SimpleSpanProcessor,
    )

    _HAS_OTEL = True
except Exception:  # pragma: no cover - optional
    _HAS_OTEL = False
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

try:
    from sentence_transformers import SentenceTransformer  # type: ignore

    _HAS_ST = True
except Exception:  # pragma: no cover - optional dependency
    _HAS_ST = False


def create_app() -> FastAPI:
    app = FastAPI(title="rag", version="0.4.0")

    # Optional tracing
    if _HAS_OTEL and os.getenv("OTEL_ENABLED", "false").lower() == "true":
        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        resource = Resource.create({"service.name": "rag"})
        provider = TracerProvider(resource=resource)
        if endpoint:
            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
            )
        else:
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)

    # Backend selection: tfidf (default) or st (Sentence-Transformers)
    app.state.backend: str = os.getenv("EMBEDDINGS_BACKEND", "tfidf").lower()

    # In-memory index of chunks: each doc is { id, content, parent_id, meta }
    app.state.docs: List[Dict[str, Any]] = []

    # Optional pgvector persistence
    app.state.pg_dsn = os.getenv(
        "RAG_PG_DSN",
        "postgresql+psycopg://postgres:postgres@db:5432/postgres",
    )
    app.state.pg_enabled = os.getenv("RAG_PG_ENABLED", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    app.state.use_vector = os.getenv("RAG_USE_VECTOR", "false").lower() in {"1", "true", "yes"}

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
        if app.state.pg_enabled:
            try:
                with psycopg.connect(app.state.pg_dsn.replace("+psycopg", "")) as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            create table if not exists rag_docs (
                                id text primary key,
                                parent_id text,
                                content text,
                                meta jsonb,
                                embedding vector(384)
                            )
                            """
                        )
                        if app.state.backend == "st" and app.state.use_vector and app.state.st_model is not None:
                            emb = app.state.st_model.encode([content], normalize_embeddings=True)[0]
                            vec = "[" + ",".join(f"{float(x):.6f}" for x in emb) + "]"
                            cur.execute(
                                "insert into rag_docs(id,parent_id,content,meta,embedding) values (%s,%s,%s,%s,%s::vector) on conflict (id) do update set content=excluded.content, meta=excluded.meta, embedding=excluded.embedding",
                                (
                                    doc_id,
                                    doc_id,
                                    content,
                                    psycopg.adapters.Json(meta) if meta else None,
                                    vec,
                                ),
                            )
                        else:
                            # Simple TF-IDF has no embedding; store null for now
                            cur.execute(
                                "insert into rag_docs(id,parent_id,content,meta) values (%s,%s,%s,%s) on conflict (id) do update set content=excluded.content, meta=excluded.meta",
                                (
                                    doc_id,
                                    doc_id,
                                    content,
                                    psycopg.adapters.Json(meta) if meta else None,
                                ),
                            )
                        conn.commit()
            except Exception:
                pass
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
        if app.state.pg_enabled:
            try:
                with psycopg.connect(app.state.pg_dsn.replace("+psycopg", "")) as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            create table if not exists rag_docs (
                                id text primary key,
                                parent_id text,
                                content text,
                                meta jsonb,
                                embedding vector(384)
                            )
                            """
                        )
                        for d in app.state.docs[-added:]:
                            if app.state.backend == "st" and app.state.use_vector and app.state.st_model is not None:
                                emb = app.state.st_model.encode([d["content"]], normalize_embeddings=True)[0]
                                vec = "[" + ",".join(f"{float(x):.6f}" for x in emb) + "]"
                                cur.execute(
                                    "insert into rag_docs(id,parent_id,content,meta,embedding) values (%s,%s,%s,%s,%s::vector) on conflict (id) do update set content=excluded.content, meta=excluded.meta, embedding=excluded.embedding",
                                    (
                                        d["id"],
                                        d.get("parent_id"),
                                        d["content"],
                                        (
                                            psycopg.adapters.Json(d.get("meta"))
                                            if d.get("meta")
                                            else None
                                        ),
                                        vec,
                                    ),
                                )
                            else:
                                cur.execute(
                                    "insert into rag_docs(id,parent_id,content,meta) values (%s,%s,%s,%s) on conflict (id) do update set content=excluded.content, meta=excluded.meta",
                                    (
                                        d["id"],
                                        d.get("parent_id"),
                                        d["content"],
                                        (
                                            psycopg.adapters.Json(d.get("meta"))
                                            if d.get("meta")
                                            else None
                                        ),
                                    ),
                                )
                        conn.commit()
            except Exception:
                pass
        return {"indexed": added}

    @app.post("/search")
    def search(payload: Dict[str, Any]) -> Dict[str, Any]:
        query = payload.get("q", "").lower()
        top_k = int(payload.get("top_k", 5))
        if not query:
            raise HTTPException(status_code=400, detail="q required")
        if not app.state.docs:
            return {"results": []}
        # Vector path (pgvector cosine) if enabled and embeddings exist
        if app.state.pg_enabled and app.state.use_vector and app.state.backend == "st" and app.state.st_model is not None:
            try:
                q_vec = app.state.st_model.encode([query], normalize_embeddings=True)[0]
                vec = "[" + ",".join(f"{float(x):.6f}" for x in q_vec) + "]"
                with psycopg.connect(app.state.pg_dsn.replace("+psycopg", "")) as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            select id, parent_id, content, meta, (1.0 - (embedding <=> %s::vector)) as score
                            from rag_docs
                            where embedding is not null
                            order by embedding <=> %s::vector asc
                            limit %s
                            """,
                            (vec, vec, top_k),
                        )
                        rows = cur.fetchall()
                        out = []
                        for rid, parent_id, content, meta, score in rows:
                            out.append(
                                {
                                    "id": rid,
                                    "parent_id": parent_id,
                                    "score": float(score),
                                    "snippet": content[:200],
                                    "meta": meta,
                                }
                            )
                        return {"results": out}
            except Exception:
                # fall through to in-memory methods
                pass
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
