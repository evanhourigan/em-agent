# Migration Guide

This guide helps you migrate between EM Agent versions.

## Version History

- **v0.4.0** (2025-11-19): Phase 1 complete - 7 integrations (GitHub, Linear, PagerDuty, Jira, Shortcut, Slack)
- **v0.5.0** (Next): GitHub Actions + dbt metrics layer
- **v1.0.0** (Goal): DORA Complete

---

## Migrating to v0.5.0 (from v0.4.0)

### Breaking Changes
- None

### New Features
- GitHub Actions workflow tracking
- Updated dbt metrics models
- Bi-directional Slack notifications
- Integration feature flags

### Database Migrations
```bash
# Backup database first
docker compose exec db pg_dump -U postgres > backup_v0.4.0.sql

# Run migrations
cd services/gateway
alembic upgrade head
```

### Environment Variables (New)
```bash
# Optional: Enable/disable integrations
INTEGRATIONS_GITHUB_ACTIONS_ENABLED=true
SLACK_DEPLOYMENT_CHANNEL=#engineering
```

### Configuration Changes
- `app_version` updated from `0.1.0` to `0.5.0` in config.py
- Added 15 new integration feature flags (see config.py lines 58-82)

### Deployment Steps
1. Update VERSION file to 0.5.0
2. Pull latest code: `git pull origin main`
3. Rebuild services: `docker compose build --no-cache gateway`
4. Run database migrations: `alembic upgrade head`
5. Restart services: `docker compose up -d`
6. Verify health: `curl http://localhost:8000/health`
7. Check version: `curl http://localhost:8000/ | jq .version`

### Rollback Procedure
See [ROLLBACK.md](ROLLBACK.md)

---

## Future Migrations

### v0.6.0 (Datadog + Sentry)
- New webhook endpoints
- New dbt models for change failure rate
- Database migrations: 0014-0015

### v0.7.0 (Multi-CI/CD)
- CircleCI, Jenkins, GitLab webhooks
- Unified CI metrics

### v1.0.0 (DORA Complete)
- Complete DORA metrics
- Production dashboards
- Full observability
