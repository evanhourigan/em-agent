## Summary

Add webhook ingestion: `events_raw` table and `/webhooks/github` + `/webhooks/jira` endpoints with idempotency and optional HMAC validation.

## Related Issues

Closes #4

## Context / Decision Links

- ARCHITECTURE.md → Phase 1 — 1.4 Webhook intake stubs

## Changes

- [x] Code
- [ ] Tests
- [x] Docs (ARCHITECTURE tracker already updated)
- [x] Migrations (`0003_events_raw`)

## Screenshots / Logs (optional)

N/A

## Validation

- Build and migrate:
  - `make up` then `make mig.up`
- GitHub webhook (no secret):

```bash
curl -sS -X POST http://localhost:8000/webhooks/github \
  -H 'X-GitHub-Event: push' \
  -H 'X-GitHub-Delivery: demo-1' \
  -H 'content-type: application/json' \
  -d '{"zen":"Keep it logically awesome."}'
```

- Jira webhook:

```bash
curl -sS -X POST http://localhost:8000/webhooks/jira \
  -H 'X-Atlassian-Webhook-Identifier: demo-1' \
  -H 'content-type: application/json' \
  -d '{"event":"issue_updated"}'
```

## Risk & Rollback

Low. Schema addition only; rollback via `alembic downgrade 0002_projects` if needed. No external side effects.
