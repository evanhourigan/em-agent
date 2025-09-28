# Engineering Manager Agent - Architecture & Implementation Plan

## Vision

An AI-assisted “Chief of Staff” for engineering that plugs into your stack, continuously reads the room (tickets, PRs, commits, docs, chats), surfaces risks, automates toil, and produces trustworthy operating metrics—while keeping humans in control.

---

## Core Capabilities

1. **Blocker detection & escalation**
2. **PR triage & review coordinator**
3. **DORA & flow metrics**
4. **Meeting automation**
5. **Knowledge routing & RAG**
6. **Goal alignment**
7. **Capacity & planning helper**
8. **Policy guardrails**
9. **Incident co-pilot**
10. **Onboarding autopilot**
11. **Risk register**
12. **Ethical & privacy posture**

---

## Reference Architecture

```
+-----------------------------+      +---------------------------+
|         Slack, Email        |      |     Jira/Confluence      |
|  GitHub/Bitbucket/GitLab    |      |  GitHub Projects, Linear  |
|  CI/CD (GitHub, Circle, etc)|      |  PagerDuty, Statuspage    |
+--------------+--------------+      +---------------+-----------+
               |                                   |
               v                                   v
        +-------------+   Events (webhooks)   +-------------+
        |  Ingestion  |---------------------->|  Event Bus  |
        |  (MCP tools)|  (HTTP -> signed)     | (NATS/Kafka)|
        +------+------+                       +------+------ +
               |                                    |
               v                                    v
        +-------------+                      +-------------+
        |  Orchestr.  | <--- tasks/sagas --->|  Workers    |
        | (Temporal)  |                      | (Celery/etc)|
        +------+------+                      +------+------ +
               |                                    |
               v                                    v
   +---------------------+                 +--------------------+
   |  Core Services      |                 |  Data Platform     |
   | - Signal Engine     |                 | - OLTP: Postgres   |
   | - Policy Engine     |                 | - Vector: pgvector |
   | - Metrics Service   |                 | - Lake/Warehouse   |
   | - RAG Service       |                 |   (DuckDB/BigQuery)|
   +-----+---------+-----+                 +---------+----------+
         |         |                                 |
         v         v                                 v
 +---------------+  +----------------+       +-------------------+
 | LLM Gateway   |  | Secrets/Config |       | Observability     |
 | (tool calling)|  | (Vault/SOPS)   |       | OTel/Prom/Grafana |
 +-------+-------+  +--------+-------+       +---------+---------+
         |                   |                         |
         v                   v                         v
   +-----------+     +-------------+             +-----------+
   |  API/Edge |<--->|  Admin UI   |<--Slack-->  |  Audit    |
   | (FastAPI) |     |  & Chat Ops |             |  Ledger   |
   +-----------+     +-------------+             +-----------+
```

---

## Data Model

- **Identity**: users, teams, roles, code owners, Slack IDs, Jira users.
- **Work Items**: issues, epics, sprints, PRs, builds, deployments, incidents.
- **Signals**: derived facts (stale PR, overdue story, flaky test cluster).
- **Events**: raw webhooks normalized.
- **Actions**: nudges, comments, ticket changes, channel messages (with result + trace).
- **Metrics**: DORA, velocity, WIP, aging, flow efficiency.
- **Artifacts**: embeddings of docs, READMEs, runbooks.

---

## MVP v0.1 Scope

1. **Daily Standup Synth**
2. **PR Triage Bot**
3. **Sprint Health Report**
4. **Doc-first Answers**

---

## Project Plan

### Phase 0 — Foundations

- Repo structure with `gateway`, `workers`, `connectors`, `metrics`, `ui`, `infra`.

### Phase 1 — Ingestion & Normalization

- Webhook receivers, identity mapper.

### Phase 2 — Metrics & Analytics

- dbt models, dashboards, backfill.

### Phase 3 — Signal Engine & Policy

- Rule DSL, OPA policies, Temporal workflows.

### Phase 4 — RAG & Knowledge

- Confluence/repo crawlers, embeddings, retrieval with citations.

### Phase 5 — Slack App & ChatOps

- Slash commands (`/standup`, `/sprint-health`, `/triage`, `/ask`).

### Phase 6 — Reliability & Safety

- Observability, redaction, evals, cost controls.

### Phase 7 — Extras

- Incident co-pilot, onboarding autopilot, OKR mapping.

---

## Definition of Done v1.0

- **README** with architecture diagram, quickstart, demo dataset.
- **Integration tests** against sandboxes.
- **Dashboards** (delivery, flow, quality).
- **Slack commands** stable with approvals.
- **Security doc** and **contribution guide**.

---

## Deployment & DevEx

- Docker + Helm, dev profile (Kind), cloud profile (GKE/EKS).
- Seed data + fake providers for local demos.
- One-click demo: sample Jira/GitHub, canned sprint.

---

## Human-in-the-Loop (HITL) & Approvals

Keep humans in control for risky actions; automate read-only analysis and low-risk nudges.

### Principles

- Modes: auto (read-only/low risk), ask (default), require_approval (high risk).
- Tiers: high (irreversible/prod-impact/security), medium (visible but reversible), low (private drafts/labels).

### Where HITL applies

- Required: PR merges/closures/backports; ticket transitions/reassignments; paging/escalations; Statuspage updates; policy/rule changes; actions above cost/PII thresholds.
- Configurable: PR triage (assign/label), sprint nudges, posting reports to public channels, creating low-priority tickets.
- Not required: ingestion/normalization, embeddings, metrics calc, private drafts/DM summaries, audit logging.

### Architecture placement

- Orchestrator (Temporal): workflows include a wait-for-approval step (external signal).
- Gateway (API/Edge): Approvals API to propose actions and record decisions.
- Admin UI & Slack: decision UX (modals/buttons), queue of pending approvals.
- Audit & Observability: every propose/decision/execution logged and traced.

### Policy (per-tenant)

```yaml
actions:
  pr.merge:             { risk: high,   mode: require_approval }
  pr.label:             { risk: low,    mode: auto }
  pr.comment.summary:   { risk: medium, mode: ask_if_channel_public: true }
  issue.create.low:     { risk: medium, mode: ask }
  incident.page:        { risk: high,   mode: require_approval }
limits:
  max_monthly_cost_usd: 200
  max_channel_size_auto_post: 10
  pii_redaction: strict
```

### API surface

- POST /v1/actions/propose → { action_id, risk, ttl }
- GET /v1/approvals/{id} → status/detail
- POST /v1/approvals/{id}/decision → { approve|decline|modify }
- Slack interactivity endpoint → forwards decisions with trace_id

### Data model

- approvals(id, action_type, target_ref, risk_level, proposed_payload, requester, ttl, status, decided_by, decided_at, decision, reason, model_version, trace_id)
- audit_events(id, subject, verb, payload, actor, outcome, ts, correlation_id)

### Observability & metrics

- Spans: propose → wait_for_approval → execute
- Metrics: approval_latency_ms, approval_override_rate, auto_vs_hitl_counts

### Delivery plan alignment

- Phase 3 (Signal/Policy): define policy and add workflow gating.
- Phase 5 (Slack & ChatOps): user-facing approvals UX and endpoints.
- Phase 6 (Reliability & Safety): audit, redaction, evals, cost caps, approval metrics.

---

## Execution Tracker (source of truth)

This section is the single place any agent/human should consult for status and next actions.

### Phase status

- [x] Phase 0 — Foundations (skeleton gateway, Postgres, logging, metrics)
- [x] Phase 1 — Ingestion & Normalization (complete)
- [ ] Phase 2 — Metrics & Analytics (in progress)
- [ ] Phase 3 — Signal Engine & Policy
- [ ] Phase 4 — RAG & Knowledge
- [ ] Phase 5 — Slack App & ChatOps
- [ ] Phase 6 — Reliability & Safety
- [ ] Phase 7 — Extras

### Done (Phase 0)

- **Gateway service**: FastAPI with `/`, `/health`, `/metrics`.
- **Observability**: `starlette-exporter` Prometheus endpoint; `structlog` JSON logs.
- **Database**: Postgres via Compose; SQLAlchemy 2.x engine with DSN normalization.
- **DevEx**: Dockerfile, Make targets, baseline lint/format config.

### Phase 1 — Work Breakdown (authoritative WBS)

Short-term objective: capture, normalize, and persist events; establish DB migrations and simple domain CRUD to verify stack.

- [x] 1.1 Add Alembic and migration workflow

  - [x] Add Alembic dependency and `alembic.ini`
  - [x] Create `migrations/` with env script wired to SQLAlchemy 2.0 engine
  - [x] First migration: `schema_version` stamp and base tables

- [x] 1.2 Database session scaffolding

  - [x] Session/Unit-of-work helpers (context-managed sessions)
  - [x] Healthcheck uses session roundtrip

- [x] 1.3 "Projects" vertical to exercise stack

  - [x] Model: `projects` table (id, key, name, created_at, updated_at)
  - [x] Pydantic schemas: create/update/read
  - [x] Repo/service: basic CRUD with uniqueness on `key`
  - [x] Router: `POST /v1/projects`, `GET /v1/projects`, `GET /v1/projects/{id}`, `PUT/PATCH`, `DELETE`
  - [x] Migration for `projects`

- [x] 1.4 Webhook intake (stubs, signed)

  - [x] `POST /webhooks/github` (HMAC stub, idempotency key)
  - [x] `POST /webhooks/jira` (JWT or shared-secret stub)
  - [x] Persist raw payloads to `events_raw` with headers/signature and dedupe

- [x] 1.5 Identity mapping (skeleton)
  - [x] `identities` table (external_type, external_id, user_id, metadata)
  - [x] Mapper utilities (GitHub login → user, Slack user → user)
  - [x] Minimal `/v1/identities` list/create for verification

### Phase 2 — Work Breakdown

- [x] 2.1 dbt project scaffold (profiles, seed data)
- [ ] 2.2 DORA models
  - [x] Lead time for changes (events_raw → dora_lead_time)
  - [x] Deployment frequency (events_raw → deployment_frequency)
  - [x] Change fail rate
  - [x] MTTR
- [ ] 2.3 Flow metrics
  - [x] PR idle time (events_raw → pr_idle_time)
  - [x] WIP
  - [x] Aging WIP
- [ ] 2.4 Backfill jobs and retention windows
  - [x] Seed script added (services/metrics/scripts/backfill_events.py)
  - [ ] Retention policy + scheduler
- [x] 2.5 Grafana dashboards: delivery panels for lead time, PR idle, deploy freq (JSON exported)
- [x] CI: GitHub Action to parse/compile dbt on PRs (.github/workflows/dbt.yml)
  - [x] Retention purge workflow (.github/workflows/retention.yml)

### Metrics API

- `/v1/metrics/dora/lead-time`
- `/v1/metrics/dora/deployment-frequency`
- `/v1/metrics/dora/change-fail-rate`
- `/v1/metrics/dora/mttr`

### Retention

- Script: `services/metrics/scripts/purge_old_events.py`
- Targets: `make purge.events` (RETENTION_DAYS default 30)

Milestone exit for Phase 1: raw events reliably land; `projects` CRUD green; migrations and local workflows documented.

---

## Architecture Decisions (ADRs, lightweight)

1. **Web/API**: FastAPI on Python 3.12 for velocity and ecosystem fit. Alternatives considered: NestJS, Go Fiber. Decision drivers: team Python proficiency, rich async tooling, FastAPI OpenAPI support.
2. **Persistence**: Postgres + SQLAlchemy 2.x. Driver: `psycopg` v3. Rationale: sturdy OLTP default; easy to add pgvector later.
3. **Migrations**: Alembic for DDL/versioning; mandated for any schema change. Decision: block merges lacking migration or rationale.
4. **Observability**: `starlette-exporter` for metrics; `structlog` for JSON logs. OTel to be added when cross-service tracing exists.
5. **Eventing**: Start without a broker in Phase 1; persist webhooks to Postgres; revisit NATS/Kafka in Phase 2/3 when throughput requires.
6. **Orchestration**: Defer Temporal until after Phase 1; initial cron/poll or lightweight workers acceptable to validate value.
7. **HITL**: Human-in-the-loop default for outward actions; approvals API lands before any auto-actions to public channels.

Each ADR can be promoted to a standalone document if it grows in scope.

---

## Tracking in GitHub (issues, PRs, and project board)

- **Issues**: create one issue per WBS bullet. Use labels: `phase:1`, `type:feature|task|bug|infra`, `area:gateway|db|connectors|metrics|ui`.
- **Linking code to work**: reference issues in PR descriptions and commits using `Fixes #123` or `Closes #123` to auto-close on merge.
- **Milestones**: `Phase 1`, `Phase 2`, etc., with due windows aligned to this plan.
- **Project board**: columns `Backlog` → `In Progress` → `Review` → `Done`. Default automation moves issues on PR open/merge.
- **Templates**: use issue and PR templates (see `.github/`) to capture context, acceptance criteria, and validation steps.

This repository remains the canonical source; if external task tools are used, sync summaries back here.

---
