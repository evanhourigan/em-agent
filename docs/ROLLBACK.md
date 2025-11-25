# Rollback Procedures

## Quick Rollback (Production Emergency)

### 1. Rollback Application (2 minutes)
```bash
# Set VERSION to previous
export VERSION=0.4.0

# Redeploy previous Docker images
docker compose down
docker compose up -d

# Verify services
curl http://localhost:8000/health
```

### 2. Rollback Database (if needed)
```bash
# Check current migration
docker compose exec gateway alembic current

# Rollback one migration
docker compose exec gateway alembic downgrade -1

# Or rollback to specific version
docker compose exec gateway alembic downgrade <revision_id>

# Restart gateway
docker compose restart gateway
```

### 3. Disable Feature Flags (Instant rollback without redeployment)
```bash
# Disable problematic integration
export INTEGRATIONS_GITHUB_ACTIONS_ENABLED=false

# Restart gateway
docker compose restart gateway
```

---

## Rollback Scenarios

### Scenario A: New Integration Causing Issues

**Symptoms:** High error rates, webhook failures, database errors

**Solution:** Disable feature flag
```bash
# In .env file
INTEGRATIONS_<NAME>_ENABLED=false

# Restart
docker compose restart gateway

# Verify
curl http://localhost:8000/webhooks/<integration>
# Should return 503 "integration disabled"
```

### Scenario B: Database Migration Failed

**Symptoms:** Gateway won't start, alembic errors

**Solution:** Rollback migration
```bash
# Check migration status
docker compose exec gateway alembic current

# Rollback
docker compose exec gateway alembic downgrade -1

# Restart
docker compose restart gateway
```

### Scenario C: Complete Version Rollback

**Symptoms:** Multiple issues, need to go back to previous version

**Solution:** Full rollback
```bash
# 1. Stop services
docker compose down

# 2. Restore database backup
docker compose up -d db
cat backup_v0.4.0.sql | docker compose exec -T db psql -U postgres

# 3. Checkout previous version
git checkout v0.4.0

# 4. Rebuild and restart
docker compose build --no-cache
docker compose up -d

# 5. Verify
curl http://localhost:8000/health
```

---

## Recovery Checklist

- [ ] Stop affected service
- [ ] Check logs for root cause
- [ ] Disable feature flag OR rollback code
- [ ] Rollback database if needed
- [ ] Restart services
- [ ] Verify health endpoints
- [ ] Check error rates (Datadog/logs)
- [ ] Monitor for 1 hour
- [ ] Document incident
- [ ] Schedule post-mortem

---

## Prevention

- Always backup database before migration
- Test migrations in staging first
- Use feature flags for new integrations
- Monitor error rates for 24h after release
- Keep previous Docker images for 30 days
