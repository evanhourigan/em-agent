# Changelog (rag)

All notable changes to the rag service will be documented in this file.

## [Unreleased]

- Expose Prometheus metrics endpoint via starlette-exporter
- Optional OpenTelemetry tracing; spans around request handling
- Pgvector persistence path for Sentence-Transformers embeddings

## [0.4.0] - 2025-10-07

- RAG service scaffold: /health, /index, /index/bulk, /search
- TF-IDF and Sentence-Transformers backends
