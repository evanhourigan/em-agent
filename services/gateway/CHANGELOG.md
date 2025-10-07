# Changelog (gateway)

All notable changes to the gateway service will be documented in this file.

## [Unreleased]

- Add Slack post error counter and expanded approvals metrics
- Add OpenTelemetry spans to SlackClient and approvals/workflow paths
- Add graceful shutdown to stop workflow runner thread
- Rate limit and payload size guard middleware
- OPA integration via compose (`OPA_URL`) and sample policy bundle

## [0.4.0] - 2025-10-07

- Phase 5 Slack commands: approvals post, ask/triage commands, sprint health post
- Agent endpoint with optional LLM summarization
- `/ready` endpoint with DB roundtrip; metrics and tracing setup
- RAG proxy with simple retries
