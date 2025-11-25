# Changelog (gateway)

All notable changes to the gateway service will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### To Be Released in v0.5.0
- GitHub Actions workflow_run event tracking
- Updated dbt metrics for accurate deployment frequency
- Bi-directional Slack notifications

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
