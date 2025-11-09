# PagerDuty Integration Guide

**Add PagerDuty for incident management and MTTR tracking**

---

## Overview

EM Agent now supports **PagerDuty** for incident response and reliability tracking. This integration:

- **Ingests incident events** via webhooks (real-time)
- **Crawls historical incidents** for RAG knowledge base
- **Tracks incident lifecycle** (triggered, acknowledged, resolved)
- **Enables MTTR metrics** (Mean Time To Recovery) for DORA tracking
- **Indexes post-mortems** for organizational learning

**Why PagerDuty?** Essential for tracking service reliability, on-call effectiveness, and incident response times - key metrics for production-ready teams.

---

## Quick Start

### 1. Get Your PagerDuty API Token

1. Go to https://[your-subdomain].pagerduty.com/api_keys
2. Click **Create New API Key**
3. Name it "EM Agent Integration"
4. **Access level:** Read Only (or Full Access if you plan bidirectional sync later)
5. Copy the token

### 2. Configure Environment Variables

```bash
# In your .env file or docker-compose.yml
PAGERDUTY_API_TOKEN=your_api_token_here
PAGERDUTY_WEBHOOK_SECRET=your_webhook_secret  # Optional, for signature verification
```

### 3. Set Up Webhook in PagerDuty

1. Go to https://[your-subdomain].pagerduty.com/extensions
2. Click **New Extension**
3. **Extension Type:** Generic V3 Webhook
4. **Name:** EM Agent Webhook
5. **URL:** `https://your-em-agent-domain.com/webhooks/pagerduty`
6. **Scope:** Choose services to monitor (or select all)
7. **Webhook Signature Secret:** (optional, for verification)
8. Click **Save**

### 4. Test the Integration

```bash
# Test webhook endpoint
curl -X POST http://localhost:8000/webhooks/pagerduty \
  -H "Content-Type: application/json" \
  -d '{
    "event": {
      "event_type": "incident.triggered",
      "data": {
        "id": "P123ABC",
        "incident_number": 42,
        "title": "Database high CPU usage",
        "service": {
          "summary": "Production Database"
        },
        "urgency": "high"
      }
    }
  }'

# Should return: {"status":"ok","id":1}
```

### 5. Crawl Historical Incidents (Optional)

```bash
# Crawl recent resolved incidents
curl -X POST http://localhost:8001/crawl/pagerduty \
  -H "Content-Type: application/json" \
  -d '{
    "statuses": ["resolved"],
    "limit": 100
  }'

# Should return: {"indexed": 25}
```

---

## Architecture

### Event Flow

```
PagerDuty → Webhook → Gateway → events_raw → NATS → Workers
                                       ↓
                                   dbt models → MTTR Metrics API
```

1. **PagerDuty sends webhook** when incident is triggered/acknowledged/resolved
2. **Gateway stores** in `events_raw` table with `source='pagerduty'`
3. **NATS publishes** event to `events.pagerduty` topic
4. **dbt transforms** events into MTTR metrics
5. **Metrics API** exposes MTTR for DORA dashboards

### Connector Architecture

```
Connectors Service → PagerDuty REST API → Incidents → RAG Index → Search
```

1. **Connector calls** PagerDuty Incidents API with status filters
2. **Incidents are fetched** (100 per request, paginated)
3. **Content is extracted** (title, description, notes/post-mortems)
4. **RAG service indexes** incidents for semantic search
5. **Users can query** in Slack: `/em-agent ask "what caused the database outage last week?"`

---

## Configuration Options

### Webhook Handler

| Environment Variable | Required | Description |
|---------------------|----------|-------------|
| `PAGERDUTY_WEBHOOK_SECRET` | No | HMAC secret for signature verification (recommended for production) |

### Connector Crawler

| Environment Variable | Required | Description |
|---------------------|----------|-------------|
| `PAGERDUTY_API_TOKEN` | Yes | API token from PagerDuty settings |

---

## API Reference

### POST /webhooks/pagerduty

Receives PagerDuty webhook events (V3 format).

**Headers:**
- `X-PagerDuty-Signature`: HMAC-SHA256 signature (optional)
- `Content-Type`: `application/json`

**Payload Example:**
```json
{
  "event": {
    "id": "abc-123",
    "event_type": "incident.triggered",
    "resource_type": "incident",
    "occurred_at": "2025-11-09T10:00:00Z",
    "agent": {
      "type": "service"
    },
    "data": {
      "id": "P123ABC",
      "incident_number": 42,
      "title": "Database high CPU usage",
      "description": "CPU utilization above 90% for 5 minutes",
      "status": "triggered",
      "urgency": "high",
      "priority": {
        "summary": "P1"
      },
      "service": {
        "id": "service-123",
        "summary": "Production Database"
      },
      "assignments": [
        {
          "assignee": {
            "summary": "Alice (On-Call)"
          }
        }
      ],
      "created_at": "2025-11-09T10:00:00Z",
      "html_url": "https://yourcompany.pagerduty.com/incidents/P123ABC"
    }
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "id": 123
}
```

### POST /crawl/pagerduty

Crawls historical incidents for RAG indexing.

**Payload:**
```json
{
  "statuses": ["triggered", "acknowledged", "resolved"],
  "limit": 100
}
```

**Parameters:**
- `statuses`: (optional) Filter by status (default: all statuses)
- `limit`: (optional, default: 100) Max number of incidents to fetch

**Response:**
```json
{
  "indexed": 25
}
```

---

## dbt Metrics Integration

Once events are flowing, calculate MTTR (Mean Time To Recovery) metrics:

### MTTR (Mean Time To Recovery)

```sql
-- Calculate average time from incident triggered to resolved
WITH incident_lifecycle AS (
  SELECT
    payload::json->'event'->'data'->>'id' as incident_id,
    MIN(CASE
      WHEN payload::json->'event'->>'event_type' = 'incident.triggered'
      THEN received_at
    END) as triggered_at,
    MAX(CASE
      WHEN payload::json->'event'->>'event_type' = 'incident.resolved'
      THEN received_at
    END) as resolved_at
  FROM events_raw
  WHERE source = 'pagerduty'
    AND payload::json->'event'->>'event_type' IN ('incident.triggered', 'incident.resolved')
  GROUP BY 1
)
SELECT
  AVG(EXTRACT(epoch FROM resolved_at - triggered_at) / 60) as mttr_minutes
FROM incident_lifecycle
WHERE resolved_at IS NOT NULL AND triggered_at IS NOT NULL;
```

### MTTR by Service

```sql
-- MTTR broken down by service
SELECT
  payload::json->'event'->'data'->'service'->>'summary' as service,
  AVG(EXTRACT(epoch FROM resolved_at - triggered_at) / 60) as mttr_minutes,
  COUNT(*) as incident_count
FROM incident_lifecycle
WHERE resolved_at IS NOT NULL
GROUP BY 1
ORDER BY mttr_minutes DESC;
```

### Incident Urgency Distribution

```sql
-- Track high vs low urgency incidents
SELECT
  payload::json->'event'->'data'->>'urgency' as urgency,
  COUNT(DISTINCT payload::json->'event'->'data'->>'id') as incident_count
FROM events_raw
WHERE source = 'pagerduty'
  AND payload::json->'event'->>'event_type' = 'incident.triggered'
GROUP BY 1
ORDER BY incident_count DESC;
```

### Acknowledgment Time

```sql
-- Time from triggered to acknowledged
WITH incident_ack AS (
  SELECT
    payload::json->'event'->'data'->>'id' as incident_id,
    MIN(CASE
      WHEN payload::json->'event'->>'event_type' = 'incident.triggered'
      THEN received_at
    END) as triggered_at,
    MIN(CASE
      WHEN payload::json->'event'->>'event_type' = 'incident.acknowledged'
      THEN received_at
    END) as acknowledged_at
  FROM events_raw
  WHERE source = 'pagerduty'
  GROUP BY 1
)
SELECT
  AVG(EXTRACT(epoch FROM acknowledged_at - triggered_at) / 60) as avg_ack_time_minutes
FROM incident_ack
WHERE acknowledged_at IS NOT NULL;
```

---

## RAG Knowledge Base

Incidents indexed by the connector become searchable:

```bash
# In Slack
/em-agent ask "what caused the database outage last week?"

# Returns:
# Based on PagerDuty incident #42 "Database high CPU usage":
# The outage was caused by a missing index on the users table causing
# full table scans. Resolution: Added index, CPU dropped to 15%.
#
# Post-mortem notes from @alice: "Need to add index monitoring alerts"
#
# Source: https://yourcompany.pagerduty.com/incidents/P123ABC
```

**Use Cases:**
- Incident response (search similar past incidents)
- Post-mortem reviews (what did we learn?)
- On-call training (common issues and resolutions)
- Pattern detection (why do we keep having database issues?)

---

## Supported Events

### Incident Events

| Event | Description | Use Case |
|-------|-------------|----------|
| `incident.triggered` | New incident created | Track incident start time, MTTR baseline |
| `incident.acknowledged` | Incident ack'd by on-call | Track acknowledgment time |
| `incident.escalated` | Incident escalated to next level | Track escalation patterns |
| `incident.resolved` | Incident resolved | Calculate MTTR, close incident |
| `incident.reopened` | Resolved incident reopened | Track flaky fixes, recurring issues |

### Optional Events

| Event | Description | Use Case |
|-------|-------------|----------|
| `incident.annotated` | Note added to incident | Index post-mortem content |
| `incident.priority_updated` | Priority changed | Track severity escalations |
| `incident.delegated` | Incident reassigned | Track handoffs |

---

## Comparison: PagerDuty vs. Other Integrations

| Feature | PagerDuty | GitHub Issues | Jira | Linear |
|---------|-----------|---------------|------|--------|
| **Focus** | Incident management | Project tracking | Project tracking | Project tracking |
| **Webhook Events** | ✅ Incident lifecycle | ✅ Issue lifecycle | ✅ Issue lifecycle | ✅ Issue lifecycle |
| **MTTR Metrics** | ✅ Native | ⚠️ Requires custom mapping | ⚠️ Requires custom mapping | ⚠️ Requires custom mapping |
| **On-Call Tracking** | ✅ Native | ❌ No | ❌ No | ❌ No |
| **Post-Mortems** | ✅ Via notes | ⚠️ Via comments | ⚠️ Via comments | ⚠️ Via comments |
| **Best For** | Production incidents | Feature tracking | Enterprise workflows | Modern startups |

**Key Advantage:** PagerDuty is purpose-built for incident response, providing the most accurate MTTR metrics for DORA tracking.

---

## Troubleshooting

### Webhook Not Receiving Events

1. **Check PagerDuty webhook logs**
   - Go to https://[subdomain].pagerduty.com/extensions
   - Click on your webhook
   - View "Recent Delivery Attempts"

2. **Verify endpoint is accessible**
   ```bash
   curl https://your-domain.com/webhooks/pagerduty
   # Should return: {"detail":"Method Not Allowed"} (POST expected)
   ```

3. **Check gateway logs**
   ```bash
   docker compose logs gateway | grep pagerduty
   ```

### Crawler Returns 401 Unauthorized

1. **Verify API token**
   ```bash
   curl -X GET "https://api.pagerduty.com/incidents?limit=1" \
     -H "Authorization: Token token=$PAGERDUTY_API_TOKEN" \
     -H "Accept: application/vnd.pagerduty+json;version=2"
   # Should return recent incidents
   ```

2. **Check token permissions**
   - API token needs at least Read Only access
   - Some endpoints require Full Access

### Incidents Not Appearing in RAG

1. **Check if indexed**
   ```bash
   curl http://localhost:8000/v1/rag/search \
     -H "Content-Type: application/json" \
     -d '{"q":"database outage","top_k":5}'
   ```

2. **Verify connector ran**
   ```bash
   docker compose logs connectors | grep pagerduty
   # Should show: "indexed 25 documents"
   ```

3. **Re-index if needed**
   ```bash
   curl -X POST http://localhost:8001/crawl/pagerduty \
     -d '{"statuses":["resolved"],"limit":100}'
   ```

---

## Security Considerations

### Webhook Signature Verification

**Recommended for production:**

1. Generate a secret in PagerDuty webhook settings
2. Add to environment: `PAGERDUTY_WEBHOOK_SECRET=your_secret`
3. EM Agent will verify HMAC-SHA256 signature
4. Rejects invalid signatures with 401 Unauthorized

### API Token Storage

**Best practices:**

- ✅ Store in environment variables or secrets manager
- ✅ Use Read Only access unless write needed
- ✅ Rotate tokens annually
- ❌ Never commit tokens to git

### Network Security

- Use HTTPS for webhook endpoints (Let's Encrypt)
- Rate limiting recommended (burst during major incidents)
- Monitor for unusual API usage patterns

---

## FAQ

### Can I track on-call rotations?

**Not yet.** Current integration tracks incidents only.

**Roadmap:** Schedule API integration for on-call tracking coming in Phase 7.

### Does this replace PagerDuty Analytics?

**No, it complements them.** PagerDuty Analytics provides incident trends, on-call metrics, etc. EM Agent adds:
- Cross-tool DORA metrics (deploy frequency + MTTR)
- RAG-powered incident search
- Custom policy enforcement (alert if MTTR > 1hr)
- Integration with project management tools (link incidents to Jira issues)

### What about alerts and monitoring?

**PagerDuty integration focuses on incidents, not raw alerts.** This provides:
- Higher signal-to-noise ratio (incidents, not every alert)
- Human response metrics (MTTR, acknowledgment time)
- Post-mortem indexing for learning

For alert-level tracking, integrate your monitoring tool (Datadog, New Relic, etc.) separately.

### Can I create incidents from EM Agent?

**Not yet.** Current integration is **read-only** (webhook ingestion + crawling).

**Roadmap:** Bidirectional sync (create/update incidents via API) coming in Phase 7.

---

## Roadmap

**Coming Soon:**

- [ ] Incident creation via Slack (`/em-agent create-incident "API is down"`)
- [ ] On-call schedule tracking (who's on call now?)
- [ ] Incident → Slack thread sync (discuss incidents in Slack)
- [ ] Service dependency mapping (incident impact analysis)
- [ ] Auto-tagging incidents with similar past incidents
- [ ] SLA tracking (P1 must resolve within 1hr)

**Submit feature requests:** https://github.com/evanhourigan/em-agent/issues

---

## Support

**Documentation:** https://github.com/evanhourigan/em-agent/tree/main/docs
**Issues:** https://github.com/evanhourigan/em-agent/issues
**PagerDuty API Docs:** https://developer.pagerduty.com/api-reference/

---

**Version:** 1.0
**Last Updated:** 2025-11-09
**Compatibility:** PagerDuty REST API v2, EM Agent >= 0.2.0
