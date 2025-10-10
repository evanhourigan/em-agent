# EM Agent – Comprehensive Feature Guide and Test Instructions

This is the exhaustive reference for everything implemented in this repository and how to validate it locally. For a concise overview and installation, see README.md.

## Index
- Services overview
- Configuration & secrets
- Database migrations
- Observability (metrics, tracing, redaction)
- API surface (with test commands)
  - Health/Ready
  - Projects CRUD
  - Signals evaluator
  - Policy (YAML/OPA)
  - Workflows & Approvals (HITL)
  - Reports (standup, sprint)
  - Slack commands & interactions
  - RAG proxy & service
  - Incidents (Phase 7)
  - Onboarding (Phase 7)
  - OKR mapping (Phase 7)
- Connectors (Confluence & GitHub)
- Workers (Celery) & Temporal
- Quotas & cost caps
- Evals harness
- Grafana dashboards
- End‑to‑end recipes

---

## Services overview
- gateway (FastAPI): APIs, Slack, policy/approvals, signals, reports, incidents, onboarding, OKR, RAG proxy
- rag (FastAPI): indexing/search (TF‑IDF or pgvector + sentence‑transformers)
- connectors (FastAPI): Confluence & GitHub crawlers → RAG via gateway
- workers (Celery): background actions (nudge, assign_reviewer, comment_summary, issue_create, label)
- workers_temporal: optional Temporal execution
- metrics: dbt models + Grafana dashboards

---

## Configuration & secrets (gateway)
- DATABASE_URL, RAG_URL
- SLACK_SIGNING_SECRET, SLACK_SIGNING_REQUIRED
- SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN (+ SLACK_DEFAULT_CHANNEL)
- OTEL_ENABLED, OTEL_EXPORTER_OTLP_ENDPOINT
- OPA_URL (optional)
- RATE_LIMIT_PER_MIN, MAX_PAYLOAD_BYTES
- MAX_DAILY_SLACK_POSTS, MAX_DAILY_RAG_SEARCHES
- EVALUATOR_ENABLED, EVALUATOR_INTERVAL_SEC, RULES_PATH
- RETENTION_DAYS, RETENTION_INTERVAL_SEC

Guidance: use .env only for local dev; do not commit real secrets. In production, prefer Vault/AWS/GCP secret managers. Slack signing must use the exact same secret as the container.

---

## Database migrations
Recent migrations:
- 0009_incidents (incidents, incident_timeline)
- 0010_onboarding (onboarding_plans, onboarding_tasks)
- 0011_okr (objectives, key_results)

Run all:
```bash
make mig.up
```

---

## Observability
- Prometheus metrics (`/metrics`): approvals_decisions_total, approvals_latency_seconds, approvals_override_total, workflows_auto_vs_hitl_total, slack_posts_total, slack_post_errors_total, quota_slack_posts_total, quota_rag_searches_total
- Tracing: enable OTEL and set OTLP endpoint
- Redaction: Authorization/Bearer and Slack/OpenAI tokens masked in logs

Redaction check:
```bash
docker compose logs -f gateway | grep -i authorization || true
```

---

## API surface (test commands)
Base URL: `http://localhost:8000`

Health/Ready:
```bash
curl -sS http://localhost:8000/health | jq
curl -sS http://localhost:8000/ready | jq
```

Projects CRUD:
```bash
curl -sS -X POST localhost:8000/v1/projects -H 'content-type: application/json' -d '{"key":"core","name":"Core Platform"}' | jq
curl -sS localhost:8000/v1/projects | jq
```

Signals evaluator:
```bash
curl -sS -X POST http://localhost:8000/v1/signals/evaluate -H 'content-type: application/json' -d '{"rules":[{"kind":"stale_pr","older_than_hours":48}]}' | jq
```

Policy (YAML/OPA):
```bash
curl -sS -X POST http://localhost:8000/v1/policy/evaluate -H 'content-type: application/json' -d '{"kind":"stale_pr"}' | jq
```

Approvals (HITL):
```bash
curl -sS -X POST http://localhost:8000/v1/approvals/propose -H 'content-type: application/json' -d '{"subject":"deploy:service-x","action":"deploy","payload":{}}' | jq
curl -sS -X POST http://localhost:8000/v1/approvals/1/decision -H 'content-type: application/json' -d '{"decision":"approve"}' | jq
```

Reports:
```bash
curl -sS -X POST http://localhost:8000/v1/reports/standup -H 'content-type: application/json' -d '{"older_than_hours":48}' | jq
curl -sS -X POST http://localhost:8000/v1/reports/sprint-health -H 'content-type: application/json' -d '{"days":14}' | jq
```

Slack commands (unsigned local test):
```bash
curl -sS -X POST http://localhost:8000/v1/slack/commands -H 'content-type: application/json' -d '{"text":"triage"}' | jq
```
Signed request template:
```bash
TS=$(date +%s); BODY='text=triage'; SIG_BASE="v0:${TS}:${BODY}"; \
SECRET=$(grep -E '^SLACK_SIGNING_SECRET=' .env | cut -d= -f2-); \
SIG="v0=$(printf '%s' "${SIG_BASE}" | openssl dgst -sha256 -hmac "${SECRET}" | sed 's/^.* //')"; \
curl -sS -X POST http://localhost:8000/v1/slack/commands \
  -H "x-slack-request-timestamp: ${TS}" -H "x-slack-signature: ${SIG}" \
  -H 'content-type: application/x-www-form-urlencoded' --data-raw "${BODY}" | jq
```

RAG search:
```bash
curl -sS -X POST http://localhost:8000/v1/rag/search -H 'content-type: application/json' -d '{"q":"architecture","top_k":3}' | jq
```

Incidents:
```bash
curl -sS -X POST http://localhost:8000/v1/incidents -H 'content-type: application/json' -d '{"title":"API outage"}' | jq
curl -sS -X POST http://localhost:8000/v1/incidents/1/note -H 'content-type: application/json' -d '{"text":"Mitigation in progress"}' | jq
curl -sS -X POST http://localhost:8000/v1/incidents/1/close | jq
```

Onboarding:
```bash
curl -sS -X POST http://localhost:8000/v1/onboarding/plans -H 'content-type: application/json' -d '{"title":"New hire kit"}' | jq
curl -sS -X POST http://localhost:8000/v1/onboarding/plans/1/tasks -H 'content-type: application/json' -d '{"title":"Set up dev env"}' | jq
```

OKR mapping:
```bash
curl -sS -X POST http://localhost:8000/v1/okr/objectives -H 'content-type: application/json' -d '{"title":"Reduce MTTR"}' | jq
curl -sS -X POST http://localhost:8000/v1/okr/objectives/1/krs -H 'content-type: application/json' -d '{"title":"MTTR < 4h","target":4,"unit":"h"}' | jq
```

---

## Connectors (Confluence & GitHub)
Confluence (retry/backoff, If‑Modified‑Since):
```bash
curl -sS -X POST http://localhost:8003/crawl/confluence -H 'content-type: application/json' -d '{"base_url":"https://your-domain.atlassian.net","page_ids":["12345"],"chunk_size":800,"overlap":100}' | jq
```
GitHub (retry/backoff, ETag):
```bash
curl -sS -X POST http://localhost:8003/crawl/github -H 'content-type: application/json' -d '{"owner":"your-org","repo":"your-repo","ref":"main","include_paths":["docs/","README.md"],"exts":[".md",".txt"],"chunk_size":800,"overlap":100}' | jq
```
Scheduler: set `CRAWLER_INTERVAL_SEC` and `CRAWL_GH_OWNER/CRAWL_GH_REPO`.

---

## Workers (Celery) & Temporal
Bring up workers:
```bash
docker compose up -d --build redis workers
```
Actions: nudge, assign_reviewer, comment_summary, issue_create, label.

---

## Quotas & cost caps
Quotas endpoint:
```bash
curl -sS http://localhost:8000/v1/metrics/quotas | jq
```
Slack client enforces daily cap based on env; RAG searches counted via quota counter.

---

## Evals harness
```bash
curl -sS -X POST http://localhost:8000/v1/evals/run -H 'content-type: application/json' -d '{"rules":[{"kind":"stale_pr","older_than_hours":48},{"kind":"pr_without_review","older_than_hours":12}]}' | jq
```

---

## Grafana dashboards
Import from `services/metrics/grafana/dashboards/` (approvals_hitl.json, delivery.json) and point Grafana at Prometheus.

---

## End‑to‑end recipes
```bash
make up && make health
make rag.up && curl -sS -X POST http://localhost:8000/v1/rag/search -H 'content-type: application/json' -d '{"q":"architecture"}' | jq
curl -sS -X POST http://localhost:8000/v1/slack/commands -H 'content-type: application/json' -d '{"text":"triage"}' | jq
```
