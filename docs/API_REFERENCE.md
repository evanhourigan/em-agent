# API Reference - v1.1.0

Complete API documentation for EM Agent Gateway.

**Base URL:** `http://localhost:8000` (development)

---

## Table of Contents

1. [Health & Metrics](#health--metrics)
2. [DORA Metrics](#dora-metrics)
3. [Webhooks - All 21 Integrations](#webhooks---all-21-integrations)
4. [Projects](#projects)
5. [Signals & Policy](#signals--policy)
6. [Workflows & Approvals](#workflows--approvals)
7. [Reports](#reports)
8. [RAG (Retrieval-Augmented Generation)](#rag)
9. [Slack Commands](#slack-commands)
10. [Authentication](#authentication)

---

## Health & Metrics

### GET /health

Health check endpoint with database connectivity test.

**Response:**
```json
{
  "status": "ok",
  "db": {
    "ok": true,
    "details": "ok"
  }
}
```

### GET /ready

Readiness probe with database roundtrip test.

**Response:**
```json
{
  "ready": true,
  "db_roundtrip_ms": 12.5
}
```

### GET /metrics

Prometheus metrics exposition endpoint.

**Response:** Prometheus text format with custom application metrics:
- `approvals_decisions_total{status="approve|reject|override"}`
- `approvals_latency_seconds` (histogram)
- `workflows_auto_vs_hitl_total{mode="auto|hitl"}`
- `http_requests_total`, `http_request_duration_seconds`, etc.

---

## DORA Metrics

All DORA metric endpoints return JSON arrays suitable for dashboards and visualization.

### GET /v1/metrics/dora/deployment-frequency

Daily deployment counts across all 8 platforms.

**Query Parameters:**
- `days` (optional): Number of days to include (default: 30)

**Response:**
```json
[
  {
    "day": "2025-11-24T00:00:00",
    "total_deployments": 12,
    "github_deployments": 5,
    "circleci_deployments": 3,
    "jenkins_deployments": 1,
    "gitlab_deployments": 0,
    "kubernetes_deployments": 2,
    "argocd_deployments": 1,
    "ecs_deployments": 0,
    "heroku_deployments": 0
  }
]
```

### GET /v1/metrics/dora/lead-time

Time from PR merge to deployment (in hours).

**Response:**
```json
[
  {
    "repo": "org/service-name",
    "pr_number": "123",
    "merged_at": "2025-11-24T10:00:00",
    "first_deploy_after_merge": "2025-11-24T11:30:00",
    "lead_time_hours": 1.5
  }
]
```

### GET /v1/metrics/dora/change-fail-rate

Weekly change failure rate (deployments causing incidents).

**Response:**
```json
[
  {
    "week": "2025-11-18T00:00:00",
    "total_deployments": 50,
    "failed_deployments": 3,
    "change_fail_rate_pct": 6.0
  }
]
```

### GET /v1/metrics/dora/mttr

Mean Time To Restore from incidents (multi-source).

**Response:**
```json
[
  {
    "incident_id": "P123ABC",
    "source": "pagerduty",
    "title": "Database outage",
    "triggered_at": "2025-11-24T12:00:00",
    "resolved_at": "2025-11-24T12:45:00",
    "mttr_hours": 0.75,
    "mttr_minutes": 45.0
  }
]
```

### GET /v1/metrics/code-quality

Code coverage and quality gate trends (weekly).

**Response:**
```json
[
  {
    "week": "2025-11-18T00:00:00",
    "source": "codecov",
    "project": "my-repo",
    "avg_coverage": 85.5,
    "max_coverage": 88.0,
    "min_coverage": 82.0,
    "quality_status": null,
    "event_count": 12
  },
  {
    "week": "2025-11-18T00:00:00",
    "source": "sonarqube",
    "project": "my-project",
    "avg_coverage": null,
    "quality_status": "OK",
    "event_count": 8
  }
]
```

---

## Webhooks - All 21 Integrations

All webhook endpoints follow the pattern: `POST /webhooks/{integration}`

**Common Response:**
```json
{
  "status": "ok",
  "event_id": "evt_abc123"
}
```

**Error Response (integration disabled):**
```json
{
  "detail": "Integration disabled"
}
```
*HTTP 503 Service Unavailable*

### Project Management

#### POST /webhooks/github
**Headers:**
- `X-GitHub-Event`: Event type (pull_request, issues, workflow_run, etc.)
- `X-GitHub-Delivery`: Unique delivery ID (for idempotency)
- `X-Hub-Signature-256` (optional): HMAC signature

**Supported Events:**
- `pull_request` - PR opened, closed, merged, etc.
- `issues` - Issue created, updated, closed
- `workflow_run` - GitHub Actions workflow completed

#### POST /webhooks/jira
**Headers:**
- `X-Atlassian-Webhook-Identifier`: Unique delivery ID

**Supported Events:**
- `issue_created`, `issue_updated`, `issue_deleted`

#### POST /webhooks/shortcut
**Headers:**
- `X-Shortcut-Signature`: HMAC SHA-256 signature

**Supported Events:**
- `story-create`, `story-update`, `story-delete`
- `epic-create`, `epic-update`

#### POST /webhooks/linear
**Headers:**
- `Linear-Signature`: HMAC SHA-256 signature
- `Linear-Delivery`: Unique delivery ID

**Supported Events:**
- Issue create, update, delete
- Project updates

### Incident Management & Observability

#### POST /webhooks/pagerduty
**Headers:**
- `X-PagerDuty-Signature`: HMAC SHA-256 signature

**Supported Events:**
- `incident.triggered`, `incident.acknowledged`, `incident.resolved`

#### POST /webhooks/slack
**Supported Events:**
- `url_verification` - Webhook verification
- `event_callback` - Message events, reactions, mentions

#### POST /webhooks/datadog
**Supported Events:**
- Monitor alerts (triggered, recovered, no data)
- Custom events
- APM trace alerts

#### POST /webhooks/sentry
**Headers:**
- `Sentry-Hook-Resource`: Resource type (issue, event)

**Supported Events:**
- `issue.created`, `issue.resolved`, `issue.assigned`, `issue.ignored`
- Error events

### CI/CD Platforms

#### POST /webhooks/circleci
**Headers:**
- `Circleci-Event-Type`: Event type
- `Circleci-Signature`: HMAC SHA-256 signature

**Supported Events:**
- `workflow-completed`, `job-completed`
- `ping` - Webhook verification

#### POST /webhooks/jenkins
**Supported Events:**
- Build completion (SUCCESS, FAILURE, UNSTABLE)
- Pipeline events

#### POST /webhooks/gitlab
**Headers:**
- `X-Gitlab-Event`: Event type
- `X-Gitlab-Token`: Secret token

**Supported Events:**
- Pipeline Hook, Job Hook, Deployment Hook
- Push, Merge Request

### Deployment Platforms

#### POST /webhooks/kubernetes
**Supported Events:**
- Deployment, Pod, ReplicaSet events
- Admission webhook format
- Event object format

#### POST /webhooks/argocd
**Supported Events:**
- Application sync (Synced, OutOfSync, Degraded)
- Health status updates

#### POST /webhooks/ecs
**Supported Events:**
- Task state changes (via EventBridge)
- Service deployment events
- Container instance state

#### POST /webhooks/heroku
**Headers:**
- `Heroku-Webhook-Id`: Unique delivery ID

**Supported Events:**
- Release, build events
- Dyno state changes

### Code Quality

#### POST /webhooks/codecov
**Supported Events:**
- Coverage upload
- Coverage notifications
- Coverage change tracking

#### POST /webhooks/sonarqube
**Headers:**
- `X-Sonar-Webhook-HMAC-SHA256`: HMAC signature

**Supported Events:**
- Quality Gate status changes
- Analysis completion

### Observability Platforms (v1.1.0)

#### POST /webhooks/newrelic
**Supported Events:**
- Alert notifications (open, closed, acknowledged)
- APM events (error rate, throughput, response time)
- Deployment markers
- Infrastructure alerts
- Synthetics monitor events

**Event Types:**
- `alert_open`, `alert_closed`, `alert_acknowledged`
- `deployment`

#### POST /webhooks/prometheus
Prometheus Alertmanager webhook format.

**Supported Events:**
- Alert notifications (firing, resolved)
- Grouped alerts from Alertmanager
- Custom alert labels and annotations

**Event Types:**
- `alert_firing`, `alert_resolved`

**Example Payload:**
```json
{
  "status": "firing",
  "groupKey": "alertgroup-123",
  "alerts": [
    {
      "status": "firing",
      "labels": {"alertname": "HighCPU", "severity": "critical"},
      "annotations": {"summary": "CPU above 90%"}
    }
  ]
}
```

#### POST /webhooks/cloudwatch
AWS CloudWatch alarms delivered via SNS.

**Headers:**
- `x-amz-sns-message-type`: SNS message type (Notification, SubscriptionConfirmation)
- `x-amz-sns-message-id`: Unique message ID (for idempotency)

**Supported Events:**
- CloudWatch Alarm state changes (ALARM, OK, INSUFFICIENT_DATA)
- EventBridge events via SNS
- SNS subscription confirmation

**Event Types:**
- `alarm_alarm`, `alarm_ok`, `alarm_insufficient_data`
- `eventbridge_*` (for EventBridge events)

**Example Payload (via SNS):**
```json
{
  "Type": "Notification",
  "MessageId": "sns-msg-123",
  "Message": "{\"AlarmName\":\"HighCPU\",\"NewStateValue\":\"ALARM\"}",
  "Timestamp": "2025-11-25T10:00:00.000Z"
}
```

---

## Projects

### GET /v1/projects

List all projects.

**Response:**
```json
[
  {
    "id": 1,
    "key": "core",
    "name": "Core Platform",
    "created_at": "2025-11-24T10:00:00"
  }
]
```

### POST /v1/projects

Create a new project.

**Request:**
```json
{
  "key": "core",
  "name": "Core Platform"
}
```

### PATCH /v1/projects/{id}

Update a project.

**Request:**
```json
{
  "name": "Core Platform Team"
}
```

### DELETE /v1/projects/{id}

Delete a project.

**Response:** HTTP 204 No Content

---

## Signals & Policy

### POST /v1/signals/evaluate

Evaluate signals with YAML rules.

**Request:**
```json
{
  "yaml": "- { name: stale48h, kind: stale_pr, older_than_hours: 48 }\n- { name: wip_limit, kind: wip_limit_exceeded, limit: 5 }"
}
```

**Response:**
```json
{
  "signals": [
    {
      "name": "stale48h",
      "kind": "stale_pr",
      "matched": true,
      "details": { "pr_count": 3 }
    }
  ]
}
```

### POST /v1/policy/evaluate

Evaluate policy for a given signal kind.

**Request:**
```json
{
  "kind": "stale_pr"
}
```

**Response:**
```json
{
  "action": "notify",
  "requires_approval": false
}
```

---

## Workflows & Approvals

### POST /v1/workflows/run

Queue a workflow job (policy-gated).

**Request:**
```json
{
  "rule_kind": "stale_pr",
  "subject": "pr:123",
  "action": "close"
}
```

**Response (auto-approved):**
```json
{
  "action_id": 1,
  "status": "queued",
  "job_id": 42
}
```

**Response (requires approval):**
```json
{
  "action_id": 1,
  "status": "awaiting_approval"
}
```

### GET /v1/workflows/jobs

List workflow jobs.

**Response:**
```json
[
  {
    "id": 42,
    "rule_kind": "stale_pr",
    "subject": "pr:123",
    "action": "close",
    "status": "completed",
    "created_at": "2025-11-24T10:00:00"
  }
]
```

### GET /v1/approvals

List pending approvals.

**Response:**
```json
[
  {
    "id": 1,
    "subject": "pr:456",
    "action": "block",
    "status": "pending",
    "created_at": "2025-11-24T11:00:00"
  }
]
```

### POST /v1/approvals/{id}/decision

Make approval decision.

**Request:**
```json
{
  "decision": "approve",
  "reason": "Verified with team lead"
}
```

**Response:**
```json
{
  "id": 1,
  "status": "approved",
  "job_id": 43
}
```

---

## Reports

### POST /v1/reports/standup

Generate standup report (JSON).

**Request:**
```json
{
  "older_than_hours": 48
}
```

**Response:**
```json
{
  "stale_prs": [
    { "id": 123, "title": "Add auth", "age_hours": 72 }
  ],
  "summary": "3 stale PRs need attention"
}
```

### POST /v1/reports/standup/post

Post standup report to Slack.

**Request:**
```json
{
  "older_than_hours": 48,
  "channel": "#eng"
}
```

### POST /v1/reports/sprint-health

Generate sprint health report.

**Request:**
```json
{
  "days": 14
}
```

### POST /v1/reports/sprint-health/post

Post sprint health to Slack.

---

## RAG

### POST /v1/rag/search

Search indexed documents.

**Request:**
```json
{
  "q": "architecture decision",
  "top_k": 3
}
```

**Response:**
```json
{
  "results": [
    {
      "id": "adr-1",
      "content": "...",
      "score": 0.85,
      "meta": { "url": "https://..." }
    }
  ]
}
```

---

## Slack Commands

### POST /v1/slack/commands

Execute Slack slash commands.

**Request:**
```json
{
  "text": "signals"
}
```

**Supported Commands:**
- `signals` - List active signals
- `approvals` - List pending approvals
- `standup [hours]` - Standup report
- `standup post [channel] [hours]` - Post to Slack
- `sprint [days]` - Sprint health
- `sprint post [channel] [days]` - Post to Slack
- `ask [query]` - Query RAG
- `triage` - Triage summary

---

## Authentication

Authentication is optional (controlled by `AUTH_ENABLED` environment variable).

### POST /v1/auth/token

Get access token.

**Request:**
```json
{
  "username": "user@example.com",
  "password": "secret"
}
```

**Response:**
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

**Use in requests:**
```
Authorization: Bearer eyJ...
```

---

## Rate Limiting

Default: 120 requests/minute per IP

**Rate Limit Headers:**
- `X-RateLimit-Limit`: Requests allowed per window
- `X-RateLimit-Remaining`: Requests remaining
- `X-RateLimit-Reset`: Unix timestamp when limit resets

**Error Response (429):**
```json
{
  "detail": "Rate limit exceeded. Try again in 60 seconds."
}
```

---

## Error Responses

### 400 Bad Request
```json
{
  "detail": "Invalid request format"
}
```

### 422 Unprocessable Entity
```json
{
  "detail": "Validation error",
  "errors": [
    {
      "loc": ["body", "email"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### 503 Service Unavailable
```json
{
  "detail": "Database error occurred"
}
```

### 500 Internal Server Error
```json
{
  "detail": "Internal server error"
}
```

---

## Environment Variables

**Required:**
- `DATABASE_URL` - PostgreSQL connection string

**Optional:**
- `SLACK_WEBHOOK_URL` - Slack webhook for notifications
- `SLACK_BOT_TOKEN` - Slack bot token
- `SLACK_SIGNING_SECRET` - Slack signing secret
- `SLACK_SIGNING_REQUIRED` - Enforce Slack signature verification
- `AUTH_ENABLED` - Enable JWT authentication
- `JWT_SECRET_KEY` - Secret key for JWT tokens (min 32 chars)
- `RATE_LIMIT_ENABLED` - Enable rate limiting (default: true)
- `RATE_LIMIT_PER_MIN` - Requests per minute (default: 120)
- `OTEL_ENABLED` - Enable OpenTelemetry tracing
- `OTEL_EXPORTER_OTLP_ENDPOINT` - OTLP endpoint
- `AGENT_LLM_ENABLED` - Enable LLM summarization
- `OPENAI_API_KEY` - OpenAI API key
- `CORS_ALLOW_ORIGINS` - Allowed origins (comma-separated)

**Integration Feature Flags:**
- `INTEGRATIONS_GITHUB_ENABLED` (default: true)
- `INTEGRATIONS_JIRA_ENABLED` (default: true)
- `INTEGRATIONS_SHORTCUT_ENABLED` (default: true)
- `INTEGRATIONS_LINEAR_ENABLED` (default: true)
- `INTEGRATIONS_PAGERDUTY_ENABLED` (default: true)
- `INTEGRATIONS_SLACK_ENABLED` (default: true)
- `INTEGRATIONS_GITHUB_ACTIONS_ENABLED` (default: true)
- `INTEGRATIONS_DATADOG_ENABLED` (default: true)
- `INTEGRATIONS_SENTRY_ENABLED` (default: true)
- `INTEGRATIONS_CIRCLECI_ENABLED` (default: true)
- `INTEGRATIONS_JENKINS_ENABLED` (default: true)
- `INTEGRATIONS_GITLAB_ENABLED` (default: true)
- `INTEGRATIONS_KUBERNETES_ENABLED` (default: true)
- `INTEGRATIONS_ARGOCD_ENABLED` (default: true)
- `INTEGRATIONS_ECS_ENABLED` (default: true)
- `INTEGRATIONS_HEROKU_ENABLED` (default: true)
- `INTEGRATIONS_CODECOV_ENABLED` (default: true)
- `INTEGRATIONS_SONARQUBE_ENABLED` (default: true)

---

For deployment instructions, see [DEPLOYMENT.md](./DEPLOYMENT.md).
