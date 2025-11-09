# Linear Integration Guide

**Add Linear as your modern project management integration**

---

## Overview

EM Agent now supports **Linear** as a first-class project management integration. This integration:

- **Ingests issue updates** via webhooks (real-time)
- **Crawls historical issues** for RAG knowledge base using GraphQL
- **Tracks work item lifecycle** (creation, state changes, completion)
- **Enables metrics** using the same DORA framework as GitHub/Jira
- **Supports teams, cycles, and projects** for organization-wide tracking

**Why Linear?** Modern teams love Linear for its speed, keyboard shortcuts, and clean UX. This integration brings that data into your engineering metrics pipeline.

---

## Quick Start

### 1. Get Your Linear API Key

1. Go to https://linear.app/settings/api
2. Click **Create new key**
3. Name it "EM Agent Integration"
4. Copy the key (format: `lin_api_...`)

### 2. Configure Environment Variables

```bash
# In your .env file or docker-compose.yml
LINEAR_API_KEY=lin_api_your_key_here
LINEAR_WEBHOOK_SECRET=your_webhook_secret  # Optional, for signature verification
```

### 3. Set Up Webhook in Linear

1. Go to https://linear.app/[your-workspace]/settings/api/webhooks
2. Click **Create webhook**
3. **Webhook URL:** `https://your-em-agent-domain.com/webhooks/linear`
4. **Secret:** (optional, for verifying webhook authenticity)
5. **Events to trigger:** Select all or filter to:
   - `Issue` → `create`, `update`, `remove`
   - `Comment` → `create`, `update`, `remove`
   - `Project` → `create`, `update` (optional)
   - `Cycle` → `create`, `update` (optional)
6. Click **Create**

### 4. Test the Integration

```bash
# Test webhook endpoint
curl -X POST http://localhost:8000/webhooks/linear \
  -H "Content-Type: application/json" \
  -d '{
    "action": "create",
    "type": "Issue",
    "data": {
      "id": "abc-123",
      "identifier": "ENG-42",
      "title": "Add authentication",
      "state": {
        "name": "In Progress"
      }
    },
    "url": "https://linear.app/issue/ENG-42"
  }'

# Should return: {"status":"ok","id":1}
```

### 5. Crawl Historical Issues (Optional)

```bash
# Crawl all issues in "In Progress" and "Done" states
curl -X POST http://localhost:8001/crawl/linear \
  -H "Content-Type: application/json" \
  -d '{
    "state_ids": ["In Progress", "Done"],
    "limit": 50,
    "chunk_size": 800,
    "overlap": 100
  }'

# Should return: {"indexed": 25}
```

---

## Architecture

### Event Flow

```
Linear → Webhook → Gateway → events_raw → NATS → Workers
                                   ↓
                               dbt models → Metrics API
```

1. **Linear sends webhook** when issue is created/updated/deleted
2. **Gateway stores** in `events_raw` table with `source='linear'`
3. **NATS publishes** event to `events.linear` topic
4. **dbt transforms** events into metrics (issue cycle time, WIP, velocity)
5. **Metrics API** exposes data for dashboards and alerts

### Connector Architecture

```
Connectors Service → Linear GraphQL API → Issues → RAG Index → Search
```

1. **Connector calls** Linear GraphQL API with filters
2. **Issues are fetched** (50 per request, paginated)
3. **Content is extracted** (title, description, comments)
4. **RAG service indexes** issues for semantic search
5. **Users can query** in Slack: `/em-agent ask "what did we decide about auth?"`

---

## Configuration Options

### Webhook Handler

| Environment Variable | Required | Description |
|---------------------|----------|-------------|
| `LINEAR_WEBHOOK_SECRET` | No | HMAC secret for signature verification (recommended for production) |

### Connector Crawler

| Environment Variable | Required | Description |
|---------------------|----------|-------------|
| `LINEAR_API_KEY` | Yes | API key from Linear settings |

---

## API Reference

### POST /webhooks/linear

Receives Linear webhook events.

**Headers:**
- `Linear-Signature`: HMAC-SHA256 signature (optional)
- `Content-Type`: `application/json`

**Payload Example:**
```json
{
  "action": "update",
  "type": "Issue",
  "data": {
    "id": "abc-123",
    "identifier": "ENG-42",
    "title": "Implement user authentication",
    "description": "Add OAuth2 flow with JWT tokens",
    "state": {
      "id": "state-123",
      "name": "In Progress"
    },
    "priority": 1,
    "team": {
      "id": "team-123",
      "name": "Engineering"
    },
    "assignee": {
      "id": "user-123",
      "name": "Alice"
    },
    "createdAt": "2025-11-09T10:00:00.000Z",
    "updatedAt": "2025-11-09T14:30:00.000Z"
  },
  "url": "https://linear.app/mycompany/issue/ENG-42",
  "createdAt": "2025-11-09T14:30:00.000Z"
}
```

**Response:**
```json
{
  "status": "ok",
  "id": 123
}
```

### POST /crawl/linear

Crawls historical issues for RAG indexing using GraphQL.

**Payload:**
```json
{
  "team_id": "team-123",
  "state_ids": ["In Progress", "Done"],
  "limit": 50,
  "chunk_size": 800,
  "overlap": 100
}
```

**Parameters:**
- `team_id`: (optional) Filter by specific team ID
- `state_ids`: (optional) Filter by state names (e.g., "Todo", "In Progress", "Done")
- `limit`: (optional, default: 50) Max number of issues to fetch
- `chunk_size`: (optional, default: 800) Characters per chunk
- `overlap`: (optional, default: 100) Overlap between chunks

**Response:**
```json
{
  "indexed": 25
}
```

---

## Linear GraphQL API

Unlike REST APIs, Linear uses **GraphQL** for all data access. This provides powerful querying capabilities.

### Finding Team IDs

```graphql
query {
  teams {
    nodes {
      id
      name
      key
    }
  }
}
```

Run via curl:
```bash
curl -X POST https://api.linear.app/graphql \
  -H "Authorization: $LINEAR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "query { teams { nodes { id name key } } }"}'
```

### Finding State Names

```graphql
query {
  workflowStates {
    nodes {
      id
      name
      type
    }
  }
}
```

**Common State Names:**
- `Backlog`
- `Todo`
- `In Progress`
- `In Review`
- `Done`
- `Canceled`

---

## dbt Metrics Integration

Once events are flowing, the same dbt models that calculate DORA metrics for GitHub/Jira work for Linear:

### Issue Cycle Time

```sql
-- Calculate average time from issue start to completion
WITH issue_lifecycle AS (
  SELECT
    payload::json->'data'->>'identifier' as issue_identifier,
    MIN(CASE
      WHEN payload::json->'data'->'state'->>'name' = 'In Progress'
      THEN received_at
    END) as started_at,
    MAX(CASE
      WHEN payload::json->'data'->'state'->>'name' = 'Done'
      THEN received_at
    END) as completed_at
  FROM events_raw
  WHERE source = 'linear'
    AND event_type LIKE 'Issue:%'
  GROUP BY 1
)
SELECT
  issue_identifier,
  EXTRACT(epoch FROM completed_at - started_at) / 3600 as cycle_time_hours
FROM issue_lifecycle
WHERE completed_at IS NOT NULL AND started_at IS NOT NULL;
```

### WIP by Team

```sql
-- Track work-in-progress by team
SELECT
  payload::json->'data'->'team'->>'name' as team,
  COUNT(DISTINCT payload::json->'data'->>'identifier') as open_issues
FROM events_raw
WHERE source = 'linear'
  AND event_type = 'Issue:update'
  AND payload::json->'data'->'state'->>'name' = 'In Progress'
GROUP BY 1
ORDER BY 2 DESC;
```

### Priority Distribution

```sql
-- Track issue priority distribution
SELECT
  CASE
    WHEN (payload::json->'data'->>'priority')::int = 0 THEN 'No priority'
    WHEN (payload::json->'data'->>'priority')::int = 1 THEN 'Urgent'
    WHEN (payload::json->'data'->>'priority')::int = 2 THEN 'High'
    WHEN (payload::json->'data'->>'priority')::int = 3 THEN 'Medium'
    WHEN (payload::json->'data'->>'priority')::int = 4 THEN 'Low'
  END as priority,
  COUNT(DISTINCT payload::json->'data'->>'identifier') as issue_count
FROM events_raw
WHERE source = 'linear'
  AND event_type LIKE 'Issue:%'
GROUP BY 1
ORDER BY MIN((payload::json->'data'->>'priority')::int);
```

### Cycle Metrics

```sql
-- Issues completed per cycle (sprint)
SELECT
  payload::json->'data'->'cycle'->>'name' as cycle,
  COUNT(DISTINCT payload::json->'data'->>'identifier') as completed_issues
FROM events_raw
WHERE source = 'linear'
  AND event_type = 'Issue:update'
  AND payload::json->'data'->'state'->>'name' = 'Done'
  AND payload::json->'data'->'cycle' IS NOT NULL
GROUP BY 1
ORDER BY cycle DESC;
```

---

## RAG Knowledge Base

Issues indexed by the connector become searchable:

```bash
# In Slack
/em-agent ask "What was the decision on authentication approach?"

# Returns:
# Based on Linear issue ENG-42 "Implement user authentication":
# We decided to use OAuth2 with JWT tokens. See comments from @alice
# discussing trade-offs between session-based and token-based auth.
#
# Source: https://linear.app/mycompany/issue/ENG-42
```

**Use Cases:**
- Onboarding new engineers (search past decisions)
- Retrospectives (what did we try before?)
- Knowledge transfer (why was this built this way?)
- Product planning (what features did we discuss?)

---

## Supported Events

### Issue Events

| Event | Description | Use Case |
|-------|-------------|----------|
| `Issue:create` | New issue created | Track new work entering the system |
| `Issue:update` | Issue updated (state, assignee, priority, etc.) | Track lifecycle changes |
| `Issue:remove` | Issue deleted | Track scope changes |

### Comment Events

| Event | Description | Use Case |
|-------|-------------|----------|
| `Comment:create` | Comment added to issue | Index discussions for RAG |
| `Comment:update` | Comment edited | Update indexed content |
| `Comment:remove` | Comment deleted | Remove from RAG index |

### Project Events (Optional)

| Event | Description | Use Case |
|-------|-------------|----------|
| `Project:create` | Project created | Track project initiatives |
| `Project:update` | Project updated | Monitor project progress |

### Cycle Events (Optional)

| Event | Description | Use Case |
|-------|-------------|----------|
| `Cycle:create` | Cycle (sprint) created | Sprint planning |
| `Cycle:update` | Cycle updated | Sprint tracking |

---

## Comparison: Linear vs. Other Trackers

| Feature | Linear | GitHub Issues | Jira | Shortcut |
|---------|--------|---------------|------|----------|
| **API Type** | ✅ GraphQL | ✅ REST | ⚠️ REST (complex) | ✅ REST |
| **Speed** | ✅ Fast (~100ms) | ✅ Fast (~200ms) | ❌ Slow (~1-2s) | ✅ Fast (~200ms) |
| **Setup** | ✅ Simple token | ✅ Simple token | ⚠️ Complex auth | ✅ Simple token |
| **Webhook Events** | ✅ Issue, Comment, Project, Cycle | ✅ Issues, PRs | ✅ Issue, Sprint | ✅ Story, Epic |
| **RAG Indexing** | ✅ Issues + comments | ✅ Issues + comments | ✅ Issues + comments | ✅ Stories + comments |
| **dbt Integration** | ✅ Same models | ✅ Same models | ✅ Same models | ✅ Same models |
| **Best For** | Modern startups, fast teams | Open source, GitHub users | Enterprise, compliance-heavy | Startups, simple workflows |

**Key Advantage:** Linear's GraphQL API provides flexible querying with a single endpoint, making it easy to fetch exactly the data you need without over-fetching.

---

## Troubleshooting

### Webhook Not Receiving Events

1. **Check Linear webhook logs**
   - Go to https://linear.app/[workspace]/settings/api/webhooks
   - Click on your webhook
   - View "Recent deliveries" tab
   - Check for failed deliveries

2. **Verify endpoint is accessible**
   ```bash
   curl https://your-domain.com/webhooks/linear
   # Should return: {"detail":"Method Not Allowed"} (that's OK, POST is expected)
   ```

3. **Check gateway logs**
   ```bash
   docker compose logs gateway | grep linear
   ```

### Crawler Returns 401 Unauthorized

1. **Verify API key**
   ```bash
   curl -X POST https://api.linear.app/graphql \
     -H "Authorization: $LINEAR_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"query": "query { viewer { id name } }"}'
   # Should return your user info
   ```

2. **Check API key permissions**
   - Linear API keys inherit your user permissions
   - Ensure you have access to the teams/issues you're querying

### Issues Not Appearing in RAG

1. **Check if indexed**
   ```bash
   curl http://localhost:8000/v1/rag/search \
     -H "Content-Type: application/json" \
     -d '{"q":"authentication","top_k":5}'
   ```

2. **Verify connector ran**
   ```bash
   docker compose logs connectors | grep linear
   # Should show: "indexed 25 documents"
   ```

3. **Re-index if needed**
   ```bash
   curl -X POST http://localhost:8001/crawl/linear \
     -H "Content-Type: application/json" \
     -d '{"limit":50}'  # Crawl all issues
   ```

### GraphQL Query Errors

**Problem:** Crawler returns "GraphQL error: ..."

**Common Causes:**
1. **Invalid team_id:** Use the GraphQL explorer to find valid team IDs
2. **Invalid state names:** State names are case-sensitive ("In Progress" not "in progress")
3. **Rate limiting:** Linear limits to 1000 requests per hour

**Solution:** Check error message and adjust query parameters

---

## Security Considerations

### Webhook Signature Verification

**Recommended for production:**

1. Generate a secret in Linear webhook settings
2. Add to environment: `LINEAR_WEBHOOK_SECRET=your_secret`
3. EM Agent will verify HMAC-SHA256 signature on all requests
4. Rejects invalid signatures with 401 Unauthorized

### API Key Storage

**Best practices:**

- ✅ Store in environment variables or secrets manager (Vault, AWS Secrets Manager)
- ✅ Rotate keys annually
- ❌ Never commit keys to git
- ❌ Don't share keys between environments (dev/staging/prod should each have unique keys)

### Network Security

- Use HTTPS for webhook endpoints (Let's Encrypt recommended)
- Rate limiting recommended (Linear can send bursts during bulk updates)
- Monitor for unusual API usage patterns

---

## Advanced: GraphQL Pagination

For workspaces with >50 issues, use pagination:

```graphql
query {
  issues(first: 50, after: "cursor-here") {
    nodes {
      id
      title
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
```

**Implementation:**
```bash
# First page
CURSOR=""
while true; do
  RESULT=$(curl -X POST https://api.linear.app/graphql \
    -H "Authorization: $LINEAR_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"query\": \"query { issues(first: 50, after: \\\"$CURSOR\\\") { nodes { id title } pageInfo { hasNextPage endCursor } } }\"}")

  # Process results...

  HAS_NEXT=$(echo "$RESULT" | jq -r '.data.issues.pageInfo.hasNextPage')
  if [ "$HAS_NEXT" != "true" ]; then
    break
  fi

  CURSOR=$(echo "$RESULT" | jq -r '.data.issues.pageInfo.endCursor')
done
```

---

## FAQ

### Can I track multiple teams?

**Yes!** The crawler supports filtering by `team_id`. Run separate crawls for each team:

```bash
# Engineering team
curl -X POST http://localhost:8001/crawl/linear \
  -d '{"team_id":"team-eng-123","limit":50}'

# Design team
curl -X POST http://localhost:8001/crawl/linear \
  -d '{"team_id":"team-design-456","limit":50}'
```

Or omit `team_id` to crawl all teams you have access to.

### Does this replace Linear's built-in reports?

**No, it complements them.** Linear has great built-in reports (velocity, burndown, etc.). EM Agent adds:
- Cross-tool metrics (PR cycle time + issue cycle time)
- Custom policy enforcement (alert on stale issues)
- RAG-powered knowledge search
- Integration with Slack workflows

### What about Projects and Roadmaps?

**Supported!** Enable `Project` webhooks to track project-level data. Projects link multiple issues together for epic-level tracking.

### Performance at scale?

**Tested up to:**
- 5K issues in workspace
- 200 issue updates/day
- <100ms webhook ingestion latency
- <3s crawler for 50 issues

For larger workspaces (>20K issues):
- Use pagination for crawling
- Filter by team or cycle to reduce scope
- Schedule crawls during off-peak hours

### Can I create issues from EM Agent?

**Not yet.** Current integration is **read-only** (webhook ingestion + crawling).

**Roadmap:** Bidirectional sync (create/update issues via GraphQL) coming in Phase 7.

---

## Roadmap

**Coming Soon:**

- [ ] Issue creation via Slack (`/em-agent create-issue "Bug in login"`)
- [ ] Auto-assignment based on workload (ML-powered)
- [ ] Issue → Slack thread sync (discuss issues in Slack)
- [ ] Custom views support (favorites, saved filters)
- [ ] SLA tracking (P0 issues must close within 24h)
- [ ] Project-level metrics (project cycle time, scope creep)

**Submit feature requests:** https://github.com/evanhourigan/em-agent/issues

---

## Support

**Documentation:** https://github.com/evanhourigan/em-agent/tree/main/docs
**Issues:** https://github.com/evanhourigan/em-agent/issues
**Linear API Docs:** https://developers.linear.app/docs/graphql/working-with-the-graphql-api

---

**Version:** 1.0
**Last Updated:** 2025-11-09
**Compatibility:** Linear GraphQL API, EM Agent >= 0.2.0
