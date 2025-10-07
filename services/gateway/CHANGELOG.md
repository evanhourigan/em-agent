# Gateway Service — Changelog

All notable changes to the `gateway` service are documented here. This log was bootstrapped from git history for the v1 release.

## v1 (2025-10-07)

- 2025-10-06 68a06c6 policy: add sample OPA Rego policy and README instructions
- 2025-10-06 eb02859 policy: add optional OPA evaluation (OPA_URL) and use in workflows; docs updated
- 2025-10-06 491f50f otel: add spans for approvals propose/decide and workflow job processing
- 2025-10-06 85ba39d reliability: per-process rate limiting and payload size guard; docs updated
- 2025-10-01 babbf0f slack: include agent LLM summary in 'agent <query>' response when enabled
- 2025-10-01 b08fd38 agent: optional LLM summary via OpenAI-compatible API; config/env and docs
- 2025-10-01 9d2c142 fix(reports): use interval concat for :days in sprint health queries
- 2025-10-01 0dec785 fix: clean SlackClient metrics code; rebuild gateway
- 2025-10-01 d64410a fix: remove circular import by using global metrics registry; restart gateway
- 2025-10-01 13dd2f7 agent: add /v1/agent/run heuristic planner + Slack command 'agent <query>'; docs updated
- 2025-09-30 e6028eb metrics: add Prometheus counters/histograms for approvals and Slack posts
- 2025-09-30 4737a5d observability: add optional OpenTelemetry tracing (gateway+rag), OTLP endpoint/env; docs updated
- 2025-09-30 14c8f28 reliability: compose healthcheck -> /ready; Slack client retries with simple backoff
- 2025-09-30 a3b3292 phase6: add /ready endpoint; add retries to RAG proxy; docs updated
- 2025-09-30 ea5b90e slack: add 'triage' and 'triage post [channel]' using signals; docs updated
- 2025-09-30 4bb4167 slack: add 'ask' and 'ask post [channel] <query>' backed by RAG proxy; docs updated
- 2025-09-30 d4ad881 slack: add 'approvals post [channel]' with Block Kit approve/decline buttons; docs: usage examples
- 2025-09-30 8083f03 docs: README/ARCHITECTURE updates for sprint health + Slack commands; add examples
- 2025-09-30 fef788c reports: add sprint health endpoint + Slack post, fix date intervals; Slack: add 'sprint post [channel] [days]'; CI: add sprint-health daily workflow
- 2025-09-30 1d8dc2d feat(slack): parse json and form-encoded payloads; validate signature on raw body
- 2025-09-30 9107cb9 feat(reports): add /v1/reports/standup; feat(slack): standup command bound to report
- 2025-09-29 97b4252 feat(ui): minimal RAG search card; feat(slack): stub commands/interactions; wire router
- 2025-09-29 80647a4 feat(gateway): /v1/rag/search proxy via httpx; wire RAG_URL; docs
- 2025-09-29 8acc654 feat(policy): load policy from YAML (POLICY_PATH) and wire evaluator/workflows; add sample policy.yml and docs
- 2025-09-29 48c4059 feat(workflows): add /v1/workflows/jobs list and get endpoints
- 2025-09-29 389eea6 feat(approvals): enqueue workflow_job on approve and return job_id
- 2025-09-29 3ecc2f9 feat(approvals): persist approvals in Postgres; list/get/decision endpoints
- 2025-09-28 5360efc fix(migration): drop stray workflow_jobs_id_seq before creating table
- 2025-09-28 afd8286 feat(workflows): add workflow_jobs table + background runner; enqueue jobs from evaluator and /v1/workflows/run; start runner on app startup
- 2025-09-28 b76a8e6 feat(workflows): gate by policy; auto-propose approval when blocked; in-memory approvals store
- 2025-09-28 54e3baf chore(logging): silence uvicorn access logs by default; health interval=60s; workflows gated by policy
- 2025-09-28 99d80c9 feat(rules): load evaluator rules from YAML (RULES_PATH), add make rules.apply, docs
- 2025-09-28 23ee206 feat(evaluator): env-configurable periodic evaluator; make eval.on/off; doc phase 3 progress
- 2025-09-28 5c28db7 chore(gateway): run alembic upgrade on startup via entrypoint; add make up.migrate
- 2025-09-28 95e1e59 fix(workflows): correct relative import to app.models.action_log
- 2025-09-28 4a255df fix(evaluator): use sessionmaker from db instead of get_db_connection import
- 2025-09-28 dde44a3 feat(workflows/approvals): add background evaluator toggle, /v1/approvals stubs, wire startup hook
- 2025-09-28 57bc326 feat(workflows): add action_log table and /v1/workflows/run endpoint as skeleton; wire router
- 2025-09-28 29ea762 feat(signals): add pr_without_review rule; expand DSL support
- 2025-09-28 c10f55f feat(signals/policy): add no_ticket_link rule; add /v1/policy/evaluate stub and wire router
- 2025-09-28 afa21d1 feat(signals): add initial Signals DSL evaluator and /v1/signals/evaluate API; add PyYAML dependency
- 2025-09-27 eefdd97 feat: retention purge script + targets; metrics API endpoints for DORA views
- 2025-09-27 38d28d8 feat(metrics): add change_fail_rate & mttr models; update dashboard, seed script; docs + tracker
- 2025-09-26 635ef0c feat(identities): add model + router + migration (#12)
- 2025-09-26 71c900c feat(webhooks): add events_raw model + migration; GitHub/Jira webhook endpoints with idempotency; wire routes (Refs #4) (#11)
- 2025-09-26 712d453 feat(projects crud) (#10)
- 2025-09-26 4537fea db: add SQLAlchemy sessionmaker and FastAPI dependency; health check uses session roundtrip (Fixes #2) (#9)
- 2025-09-26 501b93a db:migrations: add Alembic scaffolding, initial migration, Make targets; copy alembic files in image
- 2025-09-25 80e21ed chore(devex): phase-0 polish (.env.example, healthcheck, CI, formatter)
- 2025-09-25 096f014 refactor(api): split health and metrics into v1 routers and add deps scaffold
- 2025-09-25 a099f1c feat(core): add config, structured logging, and observability wiring
- 2025-09-24 a62316b feat(gateway): initial FastAPI service with health/metrics and Postgres
