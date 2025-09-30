## Summary

Add identity mapping skeleton: `identities` table, mapper utilities (GitHub/Slack), and minimal `/v1/identities` list/create endpoints.

## Related Issues

Closes #5

## Context / Decision Links

- ARCHITECTURE.md → Phase 1 — 1.5 Identity mapping

## Changes

- [x] Code
- [ ] Tests
- [x] Docs (ARCHITECTURE tracker updated)
- [x] Migrations (`0004_identities`)
- [ ] Observability (n/a)
- [ ] Security/Privacy (n/a)

## Validation

Local steps:

```bash
make up && make mig.up

# create identity
curl -sS -X POST localhost:8000/v1/identities \
  -H 'content-type: application/json' \
  -d '{"external_type":"github","external_id":"octocat","display_name":"The Octocat"}'

# list
curl -sS localhost:8000/v1/identities | jq
```

## Risk & Rollback

- Risk: low (additive schema + minimal endpoints)
- Rollback: `alembic downgrade 0003_events_raw`
