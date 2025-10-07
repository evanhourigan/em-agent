# RAG Service — Changelog

All notable changes to the `rag` service are documented here. This log was bootstrapped from git history for the v1 release.

## v1 (2025-10-07)

- 2025-10-06 eb02859 policy: add optional OPA evaluation (OPA_URL) and use in workflows; docs updated
- 2025-10-06 423f2a1 rag: add vector writes for ST backend and pgvector similarity search; env RAG_USE_VECTOR
- 2025-10-06 83e761b rag: switch db to pgvector image; add optional pg persistence for indexed docs (schema + inserts)
- 2025-09-30 e6028eb metrics: add Prometheus counters/histograms for approvals and Slack posts
- 2025-09-30 4737a5d observability: add optional OpenTelemetry tracing (gateway+rag), OTLP endpoint/env; docs updated
- 2025-09-30 fef788c reports: add sprint health endpoint + Slack post, fix date intervals; Slack: add 'sprint post [channel] [days]'; CI: add sprint-health daily workflow
- 2025-09-29 397baad feat(rag): bulk/chunk indexing and citations; docs+CI updated
- 2025-09-29 4b691d1 feat(rag): add TF-IDF embeddings and cosine-sim search; update deps
- 2025-09-29 6ad45ae feat(rag): scaffold RAG service; wire compose/Make; add CI smoke; docs
