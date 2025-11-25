# EM Agent Integration Demo Script

**A comprehensive demo showcasing all 7 integrations and DORA metrics**

---

## Demo Overview

**Duration:** 15-20 minutes
**Audience:** Engineering leaders, platform teams, DevOps engineers
**Goal:** Demonstrate comprehensive engineering metrics across the full SDLC

---

## Pre-Demo Setup

### 1. Start Services (5 minutes before demo)

```bash
# Start all services
docker compose up -d

# Verify health
curl http://localhost:8000/health
curl http://localhost:8001/health

# Check database
docker compose exec postgres psql -U em_agent -c "SELECT COUNT(*) FROM events_raw;"
```

### 2. Pre-load Demo Data (optional)

```bash
# Run the automated test to create sample events
python3 tests/e2e_integration_test.py
```

---

## Demo Script

### ACT 1: The Problem (2 minutes)

**[Show messy spreadsheet or multiple dashboard tabs]**

> "Engineering teams today use 5-10 different tools: GitHub for code, Linear for planning, PagerDuty for incidents, Jira for enterprise workflows...
>
> Each tool has its own dashboard. Each metric is siloed. You can't answer simple questions like:
> - What's our true deployment frequency across all work?
> - How does incident response time correlate with sprint velocity?
> - Which engineer needs help right now?
>
> **EM Agent solves this by unifying all your tools into one metrics pipeline.**"

### ACT 2: The Solution - Architecture (3 minutes)

**[Show architecture diagram or draw on whiteboard]**

```
GitHub Issues  ─┐
Linear         ─┤
PagerDuty      ─┤
Jira           ─┼→ Webhooks → Gateway → events_raw → dbt → DORA Metrics
Shortcut       ─┤                  ↓
Slack          ─┤              RAG Search
GitHub PRs     ─┘
```

> "EM Agent uses an event-driven architecture:
> 1. **Webhooks** capture every event in real-time
> 2. **Gateway** stores raw events immutably
> 3. **dbt** transforms events into metrics
> 4. **RAG** makes everything searchable
>
> Let me show you each integration..."

### ACT 3: Live Integration Demos (8 minutes)

#### Demo 1: GitHub Issues - Project Tracking (1.5 min)

**[Terminal 1]**

```bash
# Send a GitHub issue event
curl -X POST http://localhost:8000/webhooks/github \
  -H "X-GitHub-Event: issues" \
  -H "X-GitHub-Delivery: demo-issue-1" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "opened",
    "issue": {
      "number": 42,
      "title": "Add OAuth2 authentication",
      "state": "open",
      "labels": [{"name": "feature"}, {"name": "priority-high"}],
      "assignee": {"login": "alice"}
    },
    "repository": {
      "name": "api-service",
      "owner": {"login": "acme-corp"}
    }
  }' | jq
```

**[Show response]**
```json
{"status":"ok","id":1}
```

**[Query database]**

```bash
docker compose exec postgres psql -U em_agent -c \
  "SELECT id, source, event_type, payload::json->'issue'->>'title' as title
   FROM events_raw
   WHERE source='github' AND event_type='issues'
   ORDER BY id DESC LIMIT 3;"
```

> "Issue captured! Now every state change (opened, assigned, closed) flows through our metrics pipeline.
> We can track cycle time, WIP per engineer, label distribution - all automatically."

---

#### Demo 2: Linear - Modern Issue Tracking (1.5 min)

**[Terminal 1]**

```bash
# Send a Linear issue event
curl -X POST http://localhost:8000/webhooks/linear \
  -H "Content-Type: application/json" \
  -d '{
    "action": "update",
    "type": "Issue",
    "data": {
      "id": "lin-123",
      "identifier": "ENG-42",
      "title": "Add OAuth2 authentication",
      "state": {"name": "In Progress"},
      "team": {"name": "Backend Team"},
      "assignee": {"name": "Alice"},
      "priority": 1
    },
    "url": "https://linear.app/acme/issue/ENG-42"
  }' | jq
```

> "Linear uses GraphQL, we handle that seamlessly. Same metrics, different tool.
> Notice the identifier ENG-42 matches our GitHub issue - we can correlate across tools!"

**[Show crawler]**

```bash
# (Skip if no API key)
echo "With LINEAR_API_KEY configured, we can also crawl historical issues:"
echo "curl -X POST http://localhost:8001/crawl/linear -d '{\"limit\":50}'"
echo "This indexes all past decisions for semantic search..."
```

---

#### Demo 3: PagerDuty - Incident Management (2 min)

**[Terminal 1]**

```bash
# Trigger an incident
curl -X POST http://localhost:8000/webhooks/pagerduty \
  -H "Content-Type: application/json" \
  -d '{
    "event": {
      "event_type": "incident.triggered",
      "occurred_at": "2025-11-09T10:00:00Z",
      "data": {
        "id": "PDEMO001",
        "incident_number": 42,
        "title": "API Gateway 503 errors",
        "status": "triggered",
        "urgency": "high",
        "service": {"summary": "Production API"},
        "created_at": "2025-11-09T10:00:00Z"
      }
    }
  }' | jq
```

**[Wait 30 seconds, then acknowledge]**

```bash
# Acknowledge the incident
curl -X POST http://localhost:8000/webhooks/pagerduty \
  -H "Content-Type: application/json" \
  -d '{
    "event": {
      "event_type": "incident.acknowledged",
      "occurred_at": "2025-11-09T10:00:30Z",
      "data": {
        "id": "PDEMO001",
        "incident_number": 42,
        "title": "API Gateway 503 errors",
        "status": "acknowledged"
      }
    }
  }' | jq
```

**[Wait 2 minutes, then resolve]**

```bash
# Resolve the incident
curl -X POST http://localhost:8000/webhooks/pagerduty \
  -H "Content-Type: application/json" \
  -d '{
    "event": {
      "event_type": "incident.resolved",
      "occurred_at": "2025-11-09T10:02:30Z",
      "data": {
        "id": "PDEMO001",
        "incident_number": 42,
        "title": "API Gateway 503 errors",
        "status": "resolved"
      }
    }
  }' | jq
```

> "Now we can calculate MTTR - Mean Time To Recovery.
> This incident took 2.5 minutes from triggered to resolved.
> That feeds directly into our DORA metrics."

---

#### Demo 3.5: Slack - Communication Context (1.5 min)

**[Terminal 1]**

```bash
# Send a Slack message event
curl -X POST http://localhost:8000/webhooks/slack \
  -H "Content-Type: application/json" \
  -H "X-Slack-Request-Timestamp: $(date +%s)" \
  -H "X-Slack-Signature: v0=demo_signature" \
  -d '{
    "type": "event_callback",
    "event_id": "Ev_DEMO_001",
    "event_time": '$(date +%s)',
    "event": {
      "type": "message",
      "channel": "C_INCIDENTS",
      "user": "U_ALICE",
      "text": "Investigating API Gateway 503 errors - checking load balancer health",
      "ts": "'$(date +%s)'.123456"
    },
    "team_id": "T_ACME",
    "api_app_id": "A_EM_AGENT"
  }' | jq
```

**[Show response]**
```json
{"status":"ok","id":8}
```

> "Slack integration captures communication context!
> Now we can correlate incident timelines with team discussions.
> When did the team start discussing this? Who was involved?
> All automatically captured alongside technical events."

**[Send an app mention]**

```bash
# Bot mention for incident creation
curl -X POST http://localhost:8000/webhooks/slack \
  -H "Content-Type: application/json" \
  -d '{
    "type": "event_callback",
    "event_id": "Ev_DEMO_002",
    "event_time": '$(date +%s)',
    "event": {
      "type": "app_mention",
      "channel": "C_ENGINEERING",
      "user": "U_BOB",
      "text": "<@U_EM_AGENT> create incident: Database connection pool exhausted",
      "ts": "'$(date +%s)'.234567"
    },
    "team_id": "T_ACME",
    "api_app_id": "A_EM_AGENT"
  }' | jq
```

> "App mentions can trigger workflows - imagine automatic incident creation
> or deployment approvals, all from Slack where your team already is!"

---

#### Demo 4: All Integrations Together (3 min)

**[Show database summary]**

```bash
# Show all integrations
docker compose exec postgres psql -U em_agent -c \
  "SELECT source, event_type, COUNT(*) as count
   FROM events_raw
   GROUP BY source, event_type
   ORDER BY source, event_type;"
```

**[Expected output]**
```
   source   |    event_type     | count
------------+-------------------+-------
 github     | issues            |     1
 github     | pull_request      |     0
 jira       | unknown           |     0
 linear     | Issue:update      |     1
 pagerduty  | incident.triggered|     1
 pagerduty  | incident.acknowledged | 1
 pagerduty  | incident.resolved |     1
 shortcut   | story-create      |     0
```

> "Six integrations, one unified data model. Every event is immutable, auditable, and ready for metrics."

---

### ACT 4: The Metrics (4 minutes)

#### DORA Metric 1: MTTR (Mean Time To Recovery)

**[SQL Query]**

```bash
docker compose exec postgres psql -U em_agent -c "
WITH incident_lifecycle AS (
  SELECT
    payload::json->'event'->'data'->>'id' as incident_id,
    payload::json->'event'->'data'->>'title' as title,
    MIN(CASE WHEN payload::json->'event'->>'event_type' = 'incident.triggered'
        THEN received_at END) as triggered_at,
    MAX(CASE WHEN payload::json->'event'->>'event_type' = 'incident.resolved'
        THEN received_at END) as resolved_at
  FROM events_raw
  WHERE source = 'pagerduty'
  GROUP BY 1, 2
)
SELECT
  incident_id,
  title,
  EXTRACT(epoch FROM resolved_at - triggered_at) / 60 as mttr_minutes
FROM incident_lifecycle
WHERE resolved_at IS NOT NULL
ORDER BY mttr_minutes DESC;
"
```

**[Expected output]**
```
 incident_id |         title           | mttr_minutes
-------------+-------------------------+--------------
 PDEMO001    | API Gateway 503 errors  |         2.5
```

> "2.5 minutes MTTR - that's our recovery time. This is one of the four DORA metrics."

---

#### DORA Metric 2: Deployment Frequency

> "For deployment frequency, we track GitHub PR merges:

```sql
SELECT
  DATE(received_at) as day,
  COUNT(*) as deploys
FROM events_raw
WHERE source = 'github'
  AND event_type = 'pull_request'
  AND payload::json->>'action' = 'closed'
  AND payload::json->'pull_request'->>'merged' = 'true'
GROUP BY 1
ORDER BY 1 DESC;
```

*This would show daily deploy frequency*"

---

#### DORA Metric 3: Lead Time for Changes

> "Lead time is PR opened to merged:

```sql
WITH pr_lifecycle AS (
  SELECT
    payload::json->'pull_request'->>'number' as pr_number,
    MIN(CASE WHEN payload::json->>'action' = 'opened'
        THEN received_at END) as opened_at,
    MAX(CASE WHEN payload::json->>'action' = 'closed'
        AND payload::json->'pull_request'->>'merged' = 'true'
        THEN received_at END) as merged_at
  FROM events_raw
  WHERE source = 'github' AND event_type = 'pull_request'
  GROUP BY 1
)
SELECT AVG(EXTRACT(epoch FROM merged_at - opened_at) / 3600) as avg_hours
FROM pr_lifecycle
WHERE merged_at IS NOT NULL;
```

*This gives average PR lead time in hours*"

---

#### DORA Metric 4: Change Failure Rate

> "Change failure rate tracks bugs found after deployment:

```sql
WITH deploys AS (
  SELECT DATE(received_at) as day, COUNT(*) as count
  FROM events_raw
  WHERE source='github' AND event_type='pull_request'
    AND payload::json->'pull_request'->>'merged' = 'true'
  GROUP BY 1
),
bugs AS (
  SELECT DATE(received_at) as day, COUNT(*) as count
  FROM events_raw
  WHERE source IN ('github', 'linear', 'jira')
    AND (payload::json->'issue'->'labels' @> '[{\"name\":\"bug\"}]'::jsonb
      OR payload::json->'data'->>'title' ILIKE '%bug%')
  GROUP BY 1
)
SELECT
  COALESCE(bugs.count, 0)::float / NULLIF(deploys.count, 0) as failure_rate
FROM deploys
LEFT JOIN bugs ON deploys.day = bugs.day;
```

*This shows what percentage of deploys introduce bugs*"

---

### ACT 5: RAG Search - The "Ah-Ha" Moment (2 minutes)

**[Search for incident resolution]**

```bash
# First, index the incident (normally done by crawler)
curl -X POST http://localhost:8001/ingest/doc \
  -H "Content-Type: application/json" \
  -d '{
    "id": "pagerduty:incident:PDEMO001",
    "content": "Incident #42: API Gateway 503 errors. Root cause: Nginx worker processes exhausted. Resolution: Increased worker_processes from 4 to 16. MTTR: 2.5 minutes. Service: Production API.",
    "meta": {
      "source": "pagerduty",
      "title": "Incident #42",
      "urgency": "high"
    }
  }' | jq
```

**[Search]**

```bash
# Search for "API errors"
curl -X POST http://localhost:8000/v1/rag/search \
  -H "Content-Type: application/json" \
  -d '{"q":"API Gateway errors resolution","top_k":5}' | jq '.results[] | {title:.meta.title, snippet:.snippet}'
```

> "This is the magic. 6 months from now, when you have another API error, just ask:
>
> **'What caused API errors before?'**
>
> Instant answer from past incidents, pull requests, Linear issues, Jira tickets - all searchable."

---

### ACT 6: The Business Value (2 minutes)

**[Show comparison chart on whiteboard or slides]**

```
Without EM Agent:
- Log into 6 different tools
- Export data to spreadsheets
- Manual calculations
- Metrics are 1 week stale
- Can't correlate across tools
= 4-8 hours per week

With EM Agent:
- One API
- Real-time metrics
- Auto-calculated DORA metrics
- Cross-tool correlation
- Searchable knowledge base
= 30 seconds per query
```

> "**ROI Calculation:**
> - Engineering Manager saves 6 hours/week
> - Director gets real-time visibility
> - Teams learn from past incidents instantly
> - DORA metrics show improvement over time
>
> **This is your engineering metrics platform.**"

---

## Demo Variations

### For Technical Audience

Focus on:
- Event-driven architecture
- GraphQL vs REST API handling
- dbt transformations
- RAG vector search

### For Business Audience

Focus on:
- DORA metrics and industry benchmarks
- Time savings (hours per week)
- Knowledge retention
- Faster incident resolution

### For Platform Teams

Focus on:
- Composable architecture
- Adding new integrations
- Policy as code (OPA)
- Observability (Prometheus, OpenTelemetry)

---

## Post-Demo Q&A Prep

### Common Questions

**Q: How do you handle API rate limits?**
> "We use exponential backoff with retries. Webhooks are instant, crawlers are scheduled. PagerDuty limits to 1000/hour, Linear to 5000/hour - we stay well under that."

**Q: What about data privacy?**
> "All data stays in your infrastructure. We don't send anything to external services. Events are stored in your Postgres database. RAG search is local using TF-IDF or pgvector."

**Q: Can we add Asana / Monday.com / custom tool?**
> "Absolutely! Each integration is ~150 lines of code. Follow the same pattern: webhook handler + crawler. I can show you the Linear integration as a template."

**Q: What about historical data?**
> "Each integration has a crawler. For example, crawl 100 recent PagerDuty incidents, or 50 Linear issues from last sprint. All indexed for search."

**Q: How do you handle schema changes from vendors?**
> "We store raw events immutably. If PagerDuty changes their schema, we can re-process old events. dbt models are versioned separately."

---

## Technical Deep Dive (if time permits)

### Show the Code

```bash
# GitHub Issues webhook handler
cat services/gateway/app/api/v1/routers/webhooks.py | grep -A 20 "def github_webhook"

# Linear crawler
cat services/connectors/app/main.py | grep -A 30 "def crawl_linear"

# dbt MTTR model
cat services/dbt/models/mttr.sql
```

### Show the Tests

```bash
# Run webhook tests
pytest tests/gateway/test_webhooks.py::TestGitHubIssuesWebhook -v

# Show coverage
pytest tests/gateway/test_webhooks.py --cov=services/gateway/app/api/v1/routers/webhooks --cov-report=term-missing
```

---

## Demo Checklist

**Before Demo:**
- [ ] Docker services running
- [ ] Database has some demo data
- [ ] Terminal windows sized properly
- [ ] URLs typed into text file for copy/paste
- [ ] jq installed for pretty JSON
- [ ] Backup slides ready

**During Demo:**
- [ ] Speak clearly, avoid jargon
- [ ] Show, don't just tell
- [ ] Pause for questions
- [ ] Use analogies (event bus = Slack for services)
- [ ] Have fun!

**After Demo:**
- [ ] Share documentation links
- [ ] Offer to set up their webhooks
- [ ] Schedule follow-up for questions
- [ ] Send thank you / next steps email

---

## Resources for Audience

**Documentation:**
- GitHub Issues Integration: `docs/GITHUB_ISSUES_INTEGRATION.md`
- Linear Integration: `docs/LINEAR_INTEGRATION.md`
- PagerDuty Integration: `docs/PAGERDUTY_INTEGRATION.md`
- Architecture Deep Dive: `docs/ARCHITECTURE_DEEP_DIVE.md`

**Try It Yourself:**
- Quick Start: `README.md`
- E2E Tests: `python3 tests/e2e_integration_test.py`
- Demo Script: `docs/DEMO_SCRIPT.md` (this file)

**GitHub:** https://github.com/evanhourigan/em-agent

---

**Last Updated:** 2025-11-09
**Demo Version:** 1.0
**Presenter:** [Your Name]
