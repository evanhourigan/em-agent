# Metrics Service — Changelog

All notable changes to the `metrics` service (dbt project and related assets) are documented here. This log was bootstrapped from git history for the v1 release.

## v1 (2025-10-07)

- 2025-09-30 fef788c reports: add sprint health endpoint + Slack post, fix date intervals; Slack: add 'sprint post [channel] [days]'; CI: add sprint-health daily workflow
- 2025-09-27 eefdd97 feat: retention purge script + targets; metrics API endpoints for DORA views
- 2025-09-27 38d28d8 feat(metrics): add change_fail_rate & mttr models; update dashboard, seed script; docs + tracker
- 2025-09-27 c2b6483 chore(metrics): add seed.events Make target and backfill_events.py
- 2025-09-27 3070ec9 ci: add dbt parse/compile workflow; feat(metrics): add pr_idle_time model
- 2025-09-27 ddeaf51 feat(metrics): add DORA lead time model and docs; make targets for dbt
- 2025-09-27 6dfbaad feat(metrics): scaffold dbt project and placeholder Grafana dashboard
