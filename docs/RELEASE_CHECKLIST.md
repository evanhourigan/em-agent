# Release Checklist

## Pre-Release (1 day before)

### Code Preparation
- [ ] All planned features merged to main
- [ ] Update VERSION file (e.g., `0.5.0`)
- [ ] Update `app_version` in config.py to match VERSION
- [ ] All tests passing: `pytest tests/`
- [ ] Coverage acceptable: `pytest --cov`
- [ ] Linting clean: `ruff check .`

### Documentation
- [ ] Update CHANGELOG.md with new version section
- [ ] Update MIGRATION_GUIDE.md if breaking changes
- [ ] Update relevant integration docs
- [ ] Update README.md status section
- [ ] Review API documentation

### Database
- [ ] Create database migration if schema changes
- [ ] Test migration locally: `alembic upgrade head`
- [ ] Test rollback: `alembic downgrade -1`
- [ ] Document migration in MIGRATION_GUIDE.md

### Testing
- [ ] Run E2E tests: `python tests/e2e_integration_test.py`
- [ ] Test all webhook endpoints manually
- [ ] Test new feature flags (enable/disable)
- [ ] Test rollback procedure
- [ ] Load test if major changes

---

## Release Day

### 1. Create Git Tag (triggers release workflow)
```bash
# Verify VERSION file
cat VERSION  # Should show new version

# Create annotated tag
git tag -a v0.5.0 -m "Phase 1: GitHub Actions + dbt metrics"

# Push tag (triggers GitHub Actions release workflow)
git push origin v0.5.0
```

### 2. Monitor Release Build
- [ ] Watch GitHub Actions workflow
- [ ] Verify Docker images built successfully
- [ ] Check images pushed to ghcr.io
- [ ] Verify GitHub Release created

### 3. Deploy to Production
```bash
# Backup database
docker compose exec db pg_dump -U postgres > backup_v0.5.0_pre.sql

# Pull new version
docker compose pull

# Run migrations
docker compose exec gateway alembic upgrade head

# Restart services
docker compose up -d

# Wait for health
sleep 10
curl http://localhost:8000/health
```

### 4. Post-Deployment Verification
- [ ] Health endpoints responding
- [ ] All services running: `docker compose ps`
- [ ] Version correct: `curl localhost:8000/ | jq`
- [ ] Database migrations applied: `alembic current`
- [ ] Webhooks accepting events
- [ ] No error spikes in logs

### 5. Gradual Feature Rollout
```bash
# Enable new features one at a time
export INTEGRATIONS_GITHUB_ACTIONS_ENABLED=true
docker compose restart gateway

# Monitor for 1 hour
docker compose logs gateway -f

# If issues, disable immediately
export INTEGRATIONS_GITHUB_ACTIONS_ENABLED=false
docker compose restart gateway
```

---

## Post-Release (24 hours)

### Monitoring
- [ ] Check error rates (baseline vs current)
- [ ] Monitor webhook success rates
- [ ] Check database performance
- [ ] Review logs for warnings
- [ ] Verify new metrics in dbt

### Communication
- [ ] Announce release in Slack/email
- [ ] Update project board
- [ ] Share release notes with team
- [ ] Document any issues found

### Cleanup
- [ ] Archive old Docker images (keep last 3)
- [ ] Update documentation if gaps found
- [ ] Plan next release (v0.6.0)

---

## Emergency Rollback

If critical issues found:
1. See [ROLLBACK.md](ROLLBACK.md)
2. Disable feature flag first (fastest)
3. Rollback Docker images if needed
4. Rollback database migrations if needed
5. Document incident for post-mortem

---

## Release Approval

**Required sign-offs before release:**
- [ ] Engineering lead reviewed code
- [ ] Tests passing in CI
- [ ] Documentation updated
- [ ] Migration tested
- [ ] Rollback procedure verified

**Release manager:** _______________
**Date:** _______________
**Version:** _______________
