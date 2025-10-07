# EM Agent (Engineering Manager Agent)

An AI-assisted “Chief of Staff” for engineering. Plugs into your stack, surfaces risks, automates toil, and produces trustworthy operating metrics—while keeping humans in control.

See `ARCHITECTURE.md` for the vision, reference architecture, phases, and execution tracker.

## Releases

- See `docs/releases/README.md` for the index of releases.
- Latest: `docs/releases/v1.md` — Engineering Manager Agent v1 release notes and diagrams.

## Status

- Phase 0 complete (gateway, Postgres, logging/metrics)
- Phase 1 in progress (ingestion + normalization)

## Quickstart (Docker)

Prereqs

- Docker Desktop running
- Homebrew with docker-compose: `brew install docker-compose`

Run (gateway + db)

```bash
make up
```

Check status

```bash
make ps
```

Follow logs

```bash
make logs
```

Stop and clean

```bash
make down
```

## Health and Metrics

Health check

````bash
make health
# or
curl -sS http://localhost:8000/health
curl -sS http://localhost:8000/ready

Tracing (optional)

```bash
# enable OTLP exporter (e.g., Tempo/Jaeger OTLP endpoint)
OTEL_ENABLED=true OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 docker compose up -d --build gateway rag

# verify spans (if no endpoint set, console exporter logs spans)
docker compose logs -f gateway | grep -i span || true
````

````

Prometheus metrics

```bash
make metrics
# or
curl -sS http://localhost:8000/metrics | head -50
````

Safety limits (optional)

```bash
# Requests per minute per-process and max payload size
RATE_LIMIT_PER_MIN=120 MAX_PAYLOAD_BYTES=$((1024*1024)) docker compose up -d --build gateway
```

## Database & Migrations

Alembic migrations are bundled into the gateway image.

Apply latest migrations

```bash
make mig.up
```

Create a new revision (interactive message prompt)

```bash
make mig.revision
```

Show migration history

```bash
make mig.history
```

## Demo Data (optional)

Populate `events_raw` with synthetic events and rebuild metrics:

```bash
# apply latest migrations (if not already)
make mig.up

# reset demo data (safe for local dev)
make seed.reset

# seed synthetic events and build dbt models
make seed.events
make dbt.run
```

## API (alpha)

## Periodic Evaluator (Phase 3)

Enable the background evaluator that reads rules from YAML (default bundled file) and writes to `action_log`:

```bash
# turn on (builds gateway and waits for health)
make eval.on

# turn off
make eval.off

# apply/override rules and start
make rules.apply

# environment flags (alternative). Add UVICORN_ACCESS_LOG=true to re-enable access logs
EVALUATOR_ENABLED=true EVALUATOR_INTERVAL_SEC=60 RULES_PATH=/app/app/config/rules.yml \
  docker-compose up -d --build gateway

# policy from YAML
POLICY_PATH=/app/app/config/policy.yml docker-compose up -d --build gateway
```

Base URL: `http://localhost:8000`

- `GET /` → service info
- `GET /health` → app + DB health
- `GET /metrics` → Prometheus exposition format

### Metrics API (DORA)

JSON endpoints backed by dbt views (for UI/Grafana or quick checks):

```bash
curl -sS http://localhost:8000/v1/metrics/dora/lead-time | jq | head
curl -sS http://localhost:8000/v1/metrics/dora/deployment-frequency | jq | head
curl -sS http://localhost:8000/v1/metrics/dora/change-fail-rate | jq | head
curl -sS http://localhost:8000/v1/metrics/dora/mttr | jq | head
```

Projects CRUD

```bash
# create
curl -sS -X POST localhost:8000/v1/projects \
  -H 'content-type: application/json' \
  -d '{"key":"core","name":"Core Platform"}'

# list
curl -sS localhost:8000/v1/projects | jq

# update
curl -sS -X PATCH localhost:8000/v1/projects/1 \
  -H 'content-type: application/json' \
  -d '{"name":"Core Platform Team"}'

# delete
curl -sS -X DELETE -o /dev/null -w '%{http_code}\n' localhost:8000/v1/projects/1
```

### Signals & Policy (Phase 3)

Evaluate signals with JSON rules or a YAML string:

```bash
curl -sS -X POST http://localhost:8000/v1/signals/evaluate \
  -H 'content-type: application/json' \
  -d '{"yaml":"- { name: stale48h, kind: stale_pr, older_than_hours: 48 }\n- { name: wip_limit, kind: wip_limit_exceeded, limit: 5 }\n- { name: missing_ticket_link, kind: no_ticket_link, ticket_pattern: [A-Z]+-[0-9]+ }"}' | jq
```

Evaluate policy stub:

```bash
curl -sS -X POST http://localhost:8000/v1/policy/evaluate \
  -H 'content-type: application/json' \
  -d '{"kind":"stale_pr"}' | jq
```

### Reports (Phase 5)

Endpoints for daily and sprint summaries. These return JSON and can also post to Slack using Block Kit when Slack env is configured (`SLACK_WEBHOOK_URL` or bot token + `SLACK_DEFAULT_CHANNEL`).

```bash
# JSON only
curl -sS -X POST http://localhost:8000/v1/reports/standup -H 'content-type: application/json' -d '{"older_than_hours":48}' | jq
curl -sS -X POST http://localhost:8000/v1/reports/sprint-health -H 'content-type: application/json' -d '{"days":14}' | jq

# Post to Slack (optional channel override)
curl -sS -X POST http://localhost:8000/v1/reports/standup/post -H 'content-type: application/json' -d '{"older_than_hours":48, "channel":"#eng"}' | jq
curl -sS -X POST http://localhost:8000/v1/reports/sprint-health/post -H 'content-type: application/json' -d '{"days":14, "channel":"#eng"}' | jq
```

### Workflows & Approvals (Phase 3)

Queue a workflow job (policy-gated; defaults to action from policy):

```bash
curl -sS -X POST http://localhost:8000/v1/workflows/run \
  -H 'content-type: application/json' \
  -d '{"rule_kind":"stale_pr","subject":"pr:123"}' | jq
```

Trigger an approval (explicit block) then approve and verify job enqueue:

```bash
# propose blocked action (returns { action_id, status: "awaiting_approval" })
APPROVAL_ID=$(curl -sS -X POST http://localhost:8000/v1/workflows/run \
  -H 'content-type: application/json' \
  -d '{"rule_kind":"stale_pr","subject":"pr:456","action":"block"}' | jq -r '.action_id')

# approve it
curl -sS -X POST http://localhost:8000/v1/approvals/$APPROVAL_ID/decision \
  -H 'content-type: application/json' \
  -d '{"decision":"approve","reason":"ok"}' | jq

# list jobs (processed by background runner)
curl -sS http://localhost:8000/v1/workflows/jobs | jq
```

List approvals and get by ID:

```bash
curl -sS http://localhost:8000/v1/approvals | jq
curl -sS http://localhost:8000/v1/approvals/1 | jq
```

### RAG Service (Phase 4)

Start and health-check:

```bash
make rag.up
```

Index and search:

```bash
curl -sS -X POST http://localhost:8001/index \
  -H 'content-type: application/json' \
  -d '{"id":"doc-1","content":"Design doc: gateway architecture"}' | jq

curl -sS -X POST http://localhost:8001/search \
  -H 'content-type: application/json' \
  -d '{"q":"architecture"}' | jq
```

Embeddings backend toggle:

```bash
# default TF-IDF
docker-compose up -d --build rag

# sentence-transformers (small, CPU-friendly). First start may take longer to warm up
EMBEDDINGS_BACKEND=st docker-compose up -d --build rag
curl -sS http://localhost:8001/health | jq
```

Gateway proxy to RAG:

```bash
# search via gateway
curl -sS -X POST http://localhost:8000/v1/rag/search \
  -H 'content-type: application/json' \
  -d '{"q":"architecture","top_k":3}' | jq
```

Bulk indexing with chunking and citations:

```bash
curl -sS -X POST http://localhost:8001/index/bulk \
  -H 'content-type: application/json' \
  -d '{"chunk_size":800,"overlap":100,"docs":[{"id":"adr-1","content":"...long text...","meta":{"url":"https://example/adr-1"}}]}' | jq

curl -sS -X POST http://localhost:8000/v1/rag/search \
  -H 'content-type: application/json' \
  -d '{"q":"architecture decision record","top_k":3}' | jq
# results include id, parent_id, meta, snippet, score for citations
```

### Slack Commands (Phase 5)

Slack signing verification is supported. Set `SLACK_SIGNING_SECRET` and `SLACK_SIGNING_REQUIRED=true` to enforce signatures. For local JSON testing without Slack, omit signing and set `SLACK_SIGNING_REQUIRED=false`.

````bash
# list signals or pending approvals
curl -sS -X POST http://localhost:8000/v1/slack/commands \
  -H 'content-type: application/json' \
  -d '{"text":"signals"}' | jq

curl -sS -X POST http://localhost:8000/v1/slack/commands \
  -H 'content-type: application/json' \
  -d '{"text":"approvals"}' | jq

# approve interaction (queues a job)
curl -sS -X POST http://localhost:8000/v1/slack/interactions \
  -H 'content-type: application/json' \
  -d '{"action":"approve-job","job_id":1}' | jq

# standup quick text and post
curl -sS -X POST http://localhost:8000/v1/slack/commands -H 'content-type: application/json' -d '{"text":"standup 48"}' | jq
curl -sS -X POST http://localhost:8000/v1/slack/commands -H 'content-type: application/json' -d '{"text":"standup post #eng 48"}' | jq

# sprint health quick text and post
curl -sS -X POST http://localhost:8000/v1/slack/commands -H 'content-type: application/json' -d '{"text":"sprint 14"}' | jq
curl -sS -X POST http://localhost:8000/v1/slack/commands -H 'content-type: application/json' -d '{"text":"sprint post #eng 14"}' | jq

# approvals list and post with buttons
curl -sS -X POST http://localhost:8000/v1/slack/commands -H 'content-type: application/json' -d '{"text":"approvals"}' | jq
curl -sS -X POST http://localhost:8000/v1/slack/commands -H 'content-type: application/json' -d '{"text":"approvals post #eng"}' | jq

# ask RAG and optionally post
curl -sS -X POST http://localhost:8000/v1/slack/commands -H 'content-type: application/json' -d '{"text":"ask how do I run migrations?"}' | jq
curl -sS -X POST http://localhost:8000/v1/slack/commands -H 'content-type: application/json' -d '{"text":"ask post #eng how do I run migrations?"}' | jq

# triage summary and post
curl -sS -X POST http://localhost:8000/v1/slack/commands -H 'content-type: application/json' -d '{"text":"triage"}' | jq
curl -sS -X POST http://localhost:8000/v1/slack/commands -H 'content-type: application/json' -d '{"text":"triage post #eng"}' | jq

# agent planner (experimental)
curl -sS -X POST http://localhost:8000/v1/agent/run -H 'content-type: application/json' -d '{"query":"sprint health and stale PRs"}' | jq

Enable LLM summary (optional):

```bash
export AGENT_LLM_ENABLED=true
export OPENAI_API_KEY=sk-...            # or compatible key
export OPENAI_BASE_URL=https://api.openai.com/v1   # optional
export OPENAI_MODEL=gpt-4o-mini         # default

docker compose up -d --build gateway

curl -sS -X POST http://localhost:8000/v1/agent/run \
  -H 'content-type: application/json' \
  -d '{"query":"sprint health and stale PRs"}' | jq
````

````

Next steps:

- Add Slack signing verification and secrets management.
- Add interactive message payload schemas and richer responses.
- Map commands to actual signal queries and approvals UX.

Webhooks (intake stubs)

```bash
# GitHub (no secret)
curl -sS -X POST http://localhost:8000/webhooks/github \
  -H 'X-GitHub-Event: push' \
  -H 'X-GitHub-Delivery: demo-1' \
  -H 'content-type: application/json' \
  -d '{"zen":"Keep it logically awesome."}'

# Jira
curl -sS -X POST http://localhost:8000/webhooks/jira \
  -H 'X-Atlassian-Webhook-Identifier: demo-1' \
  -H 'content-type: application/json' \
  -d '{"event":"issue_updated"}'
````

### MCP Tools (Phase 4)

An HTTP MCP tools service is scaffolded at `services/mcp` exposing minimal tools that proxy to the gateway:

- `POST /tools/signals.evaluate` → forwards to `/v1/signals/evaluate`
- `POST /tools/reports.standup` → forwards to `/v1/reports/standup`
- `POST /tools/rag.search` → forwards to `/v1/rag/search`
- `POST /tools/reports.sprint_health` → forwards to `/v1/reports/sprint-health`
- `POST /tools/approvals.propose` → forwards to `/v1/approvals/propose`
- `POST /tools/approvals.decide` → forwards to `/v1/approvals/{id}/decision`
- `POST /tools/slack.post_text` and `/tools/slack.post_blocks` (env Slack creds)

Run it:

```bash
docker compose up -d --build mcp
curl -sS http://localhost:8002/ | jq
curl -sS -X POST http://localhost:8002/tools/reports.standup -H 'content-type: application/json' -d '{}' | jq
```

OPA policy (optional)

```bash
# run a local OPA with the example policy
docker run -d --name opa -p 8181:8181 -v $(pwd)/services/opa/policies:/policies openpolicyagent/opa:latest run --server --addr=0.0.0.0:8181 -b /policies

# point gateway at OPA (Rego package em_agent with rule data.em_agent.decision)
OPA_URL=http://localhost:8181 docker compose up -d --build gateway

# evaluate via gateway (falls back to YAML policy if OPA unreachable)
curl -sS -X POST http://localhost:8000/v1/policy/evaluate \
  -H 'content-type: application/json' \
  -d '{"kind":"stale_pr"}' | jq
```

## Secrets hardening (Phase 6)

- Prefer runtime-injected secrets over .env files in production.
- Options: HashiCorp Vault, AWS Secrets Manager, GCP Secret Manager.
- For Git-managed configs, use SOPS (age/GPG) to encrypt files and decrypt at deploy.
- Minimum local hygiene:
  - Never commit real secrets.
  - Use `.env.example` for structure.
  - In CI, set secrets in the provider and pass as env vars.

## Development Notes

- Service: `services/gateway`