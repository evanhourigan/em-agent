# Changelog (gateway)

All notable changes to the gateway service will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### To Be Released in v0.7.0
- CircleCI integration for CI/CD pipeline tracking
- Jenkins integration for build and deployment tracking
- GitLab CI integration for pipeline events

## [0.6.0] - 2025-11-25

### Added - Phase 2: Observability & Change Failure Rate
- Datadog webhook handler (POST /webhooks/datadog)
  - Monitor alerts (triggered, recovered, no data)
  - Events and custom webhooks
  - APM trace alert support
- Sentry webhook handler (POST /webhooks/sentry)
  - Issue lifecycle tracking (created, resolved, assigned, ignored)
  - Event alerts
  - Sentry-Hook-Resource header parsing

### Changed
- Updated change_fail_rate.sql with real incident correlation
  - Correlates deployments with incidents within 24-hour window
  - Aggregates from Sentry, Datadog, and PagerDuty
  - Weekly grouping with percentage calculation
- Updated mttr.sql to include all observability sources
  - PagerDuty: triggered → resolved
  - Sentry: issue.created → issue.resolved
  - Datadog: monitor trigger → recovery
  - Outputs MTTR in hours and minutes
- Enabled feature flags:
  - integrations_github_actions_enabled = True
  - integrations_datadog_enabled = True
  - integrations_sentry_enabled = True

### Fixed
- Added missing get_settings import to webhooks router

## [0.5.0] - 2025-11-24

### Added - Phase 1: Core DORA Metrics
- GitHub Actions workflow_run event tracking via existing webhook
- Automatic Slack notifications for deployment workflows
  - Filters workflows containing "deploy" or "production"
  - Rich formatting with emojis, duration, workflow URL
  - Async delivery via SlackClient.post_deployment_notification()
- START_HERE_AFTER_COMPACTION.md quick reference guide

### Changed
- Updated deployment_frequency.sql to use workflow_run events instead of releases
- Updated dora_lead_time.sql to calculate PR merge → deployment time
- Fixed JSON operators in SQL queries (-> vs ->>)

### Fixed
- SQL query type casting for JSON comparisons in dbt models

## [0.4.1] - 2025-11-19

### Added
- Slack Events API webhook handler (POST /webhooks/slack)
- Comprehensive Slack integration documentation (600+ lines)
- 6 Slack webhook tests (URL verification, messages, reactions, mentions, etc.)
- Integration feature flags system (15 flags for gradual rollout)
- Centralized VERSION file for version management
- Automated release workflow (GitHub Actions)
- MIGRATION_GUIDE.md for version upgrades
- ROLLBACK.md for emergency procedures
- RELEASE_CHECKLIST.md for release process

### Changed
- app_version updated from 0.1.0 to 0.5.0
- Demo script updated to include all 7 integrations

### Fixed
- Version inconsistency between config.py and CHANGELOG

## [0.4.0] - 2025-10-07

- Phase 5 Slack commands: approvals post, ask/triage commands, sprint health post
- Agent endpoint with optional LLM summarization
- `/ready` endpoint with DB roundtrip; metrics and tracing setup
- RAG proxy with simple retries
