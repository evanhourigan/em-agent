# EM Agent (Engineering Manager Agent)

An AI-assisted “Chief of Staff” for engineering. Plugs into your stack, surfaces risks, automates toil, and produces trustworthy operating metrics—while keeping humans in control.

See `ARCHITECTURE.md` for the vision, reference architecture, phases, and execution tracker.

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
```bash
make health
# or
curl -sS http://localhost:8000/health
```

Prometheus metrics
```bash
make metrics
# or
curl -sS http://localhost:8000/metrics | head -50
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

## API (alpha)
Base URL: `http://localhost:8000`

- `GET /` → service info
- `GET /health` → app + DB health
- `GET /metrics` → Prometheus exposition format

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
```

## Development Notes
- Service: `services/gateway` (FastAPI + SQLAlchemy + Alembic)
- DB: Postgres (compose `db` service)
- Logging: `structlog` (JSON)
- Metrics: `starlette-exporter` Prometheus endpoint

## Contributing
- Issues: use the enhanced issue template (acceptance criteria, validation, risk)
- PRs: use the PR template; prefer squash merges for linear history
- Project board: `gh project view 1 --owner evanhourigan --web`

## License
See `LICENSE`.
