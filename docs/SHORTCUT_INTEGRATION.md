# Shortcut Integration Guide

**Add Shortcut (formerly Clubhouse) as your project management integration**

---

## Overview

EM Agent now supports **Shortcut** alongside Jira for project management tracking. This integration:

- **Ingests story updates** via webhooks (real-time)
- **Crawls historical stories** for RAG knowledge base
- **Tracks work item lifecycle** (creation, state changes, completion)
- **Enables metrics** using the same DORA framework as GitHub/Jira

## Quick Start

### 1. Get Your Shortcut API Token

1. Go to https://app.shortcut.com/settings/account/api-tokens
2. Click **Generate Token**
3. Copy the token (format: `sc_XXXXX...`)

### 2. Configure Environment Variables

```bash
# In your .env file or docker-compose.yml
SHORTCUT_API_TOKEN=sc_your_token_here
SHORTCUT_WEBHOOK_SECRET=your_webhook_secret  # Optional, for signature verification
```

### 3. Set Up Webhook in Shortcut

1. Go to https://app.shortcut.com/settings/integrations/webhooks
2. Click **Add Webhook**
3. **Webhook URL:** `https://your-em-agent-domain.com/webhooks/shortcut`
4. **Secret:** (optional, for verifying webhook authenticity)
5. **Events to trigger:** Select:
   - `story-create`
   - `story-update`
   - `story-delete`
   - `epic-create`, `epic-update` (if tracking epics)

### 4. Test the Integration

```bash
# Test webhook endpoint
curl -X POST http://localhost:8000/webhooks/shortcut \
  -H "Content-Type: application/json" \
  -d '{
    "action": "story-create",
    "id": "123456",
    "primary_id": "123456",
    "name": "Test story",
    "story_type": "feature"
  }'

# Should return: {"status":"ok","id":1}
```

### 5. Crawl Historical Stories (Optional)

```bash
# Crawl all stories in "In Progress" and "Ready for Deploy" states
curl -X POST http://localhost:8001/crawl/shortcut \
  -H "Content-Type: application/json" \
  -d '{
    "state_ids": ["500000001", "500000002"],
    "chunk_size": 800,
    "overlap": 100
  }'

# Should return: {"indexed": 25}
```

---

## Architecture

### Event Flow

```
Shortcut → Webhook → Gateway → events_raw → NATS → Workers
                                     ↓
                                 dbt models → Metrics API
```

1. **Shortcut sends webhook** when story is created/updated
2. **Gateway stores** in `events_raw` table with `source='shortcut'`
3. **NATS publishes** event to `events.shortcut` topic
4. **dbt transforms** events into metrics (story cycle time, WIP, etc.)
5. **Metrics API** exposes data for dashboards and alerts

### Connector Architecture

```
Connectors Service → Shortcut API → Stories → RAG Index → Search
```

1. **Connector calls** Shortcut Search API with filters
2. **Stories are fetched** (25 per request, paginated)
3. **Content is extracted** (title, description, comments)
4. **RAG service indexes** stories for semantic search
5. **Users can query** in Slack: `/em-agent ask "what did we decide about auth?"`

---

## Configuration Options

### Webhook Handler

| Environment Variable | Required | Description |
|---------------------|----------|-------------|
| `SHORTCUT_WEBHOOK_SECRET` | No | HMAC secret for signature verification |

### Connector Crawler

| Environment Variable | Required | Description |
|---------------------|----------|-------------|
| `SHORTCUT_API_TOKEN` | Yes | API token from Shortcut settings |

---

## API Reference

### POST /webhooks/shortcut

Receives Shortcut webhook events.

**Headers:**
- `X-Shortcut-Signature`: HMAC-SHA256 signature (optional)
- `Content-Type`: `application/json`

**Payload Example:**
```json
{
  "action": "story-update",
  "id": "12345",
  "primary_id": "12345",
  "name": "Implement user authentication",
  "story_type": "feature",
  "workflow_state_id": "500000002",
  "changed_at": "2025-11-08T22:00:00Z",
  "member_mention_ids": [],
  "comments": [
    {
      "author_id": "abc-def",
      "text": "LGTM, ready to merge",
      "created_at": "2025-11-08T21:55:00Z"
    }
  ]
}
```

**Response:**
```json
{
  "status": "ok",
  "id": 123
}
```

### POST /crawl/shortcut

Crawls historical stories for RAG indexing.

**Payload:**
```json
{
  "state_ids": ["500000001", "500000002"],
  "iteration_id": "123",
  "chunk_size": 800,
  "overlap": 100
}
```

**Parameters:**
- `state_ids`: (optional) Filter by workflow state IDs
- `iteration_id`: (optional) Filter by specific sprint/iteration
- `chunk_size`: (optional, default: 800) Characters per chunk
- `overlap`: (optional, default: 100) Overlap between chunks

**Response:**
```json
{
  "indexed": 25
}
```

---

## Workflow State IDs

Shortcut uses numeric IDs for workflow states. Find yours:

```bash
# Get your workflow states
curl -X GET "https://api.app.shortcut.com/api/v3/workflows" \
  -H "Shortcut-Token: $SHORTCUT_API_TOKEN"
```

**Common Default States:**
- `500000001`: Unstarted
- `500000002`: Started
- `500000003`: Done

**Use these in your crawler filters** to index only active work or completed stories.

---

## dbt Metrics Integration

Once events are flowing, the same dbt models that calculate DORA metrics for GitHub/Jira work for Shortcut:

### Story Cycle Time

```sql
-- Query story cycle time (Shortcut equivalent of PR lead time)
SELECT
  AVG(EXTRACT(epoch FROM completed_at - created_at) / 3600) as avg_hours
FROM events_raw
WHERE source = 'shortcut'
  AND event_type = 'story-update'
  AND payload::json->>'workflow_state_id' = '500000003';  -- "Done" state
```

### WIP Tracking

```sql
-- Track work-in-progress across iterations
SELECT
  iteration_id,
  COUNT(*) as story_count
FROM events_raw
WHERE source = 'shortcut'
  AND event_type = 'story-update'
  AND payload::json->>'workflow_state_id' IN ('500000002', '500000004')  -- In Progress states
GROUP BY iteration_id;
```

---

## RAG Knowledge Base

Stories indexed by the connector become searchable:

```bash
# In Slack
/em-agent ask "What was the decision on authentication approach?"

# Returns:
# Based on Shortcut story #12345 "Implement user authentication":
# We decided to use OAuth2 with JWT tokens. See comments from @alice
# and @bob discussing trade-offs.
#
# Source: https://app.shortcut.com/your-org/story/12345
```

**Use Cases:**
- Onboarding new engineers (search past decisions)
- Retrospectives (what did we try before?)
- Knowledge transfer (why was this built this way?)

---

## Comparison: Shortcut vs. Jira

| Feature | Shortcut | Jira |
|---------|----------|------|
| **Webhook Events** | ✅ story-*, epic-* | ✅ issue-*, sprint-* |
| **API Token Auth** | ✅ Simple token | ✅ Basic auth or OAuth |
| **Historical Sync** | ✅ Search API | ✅ JQL queries |
| **RAG Indexing** | ✅ Stories + comments | ✅ Issues + comments |
| **dbt Integration** | ✅ Same models | ✅ Same models |
| **Webhook Security** | ✅ HMAC signature | ✅ IP allowlist |

**Key Difference:** Shortcut's API is simpler (single token, clean REST), while Jira's is more complex (multiple auth methods, SOAP remnants).

**Performance:** Shortcut's API is significantly faster (avg 200ms vs. Jira's 1-2s response times).

---

## Troubleshooting

### Webhook Not Receiving Events

1. **Check Shortcut webhook logs**
   - Go to https://app.shortcut.com/settings/integrations/webhooks
   - Click on your webhook
   - View "Recent Deliveries" tab

2. **Verify endpoint is accessible**
   ```bash
   curl https://your-domain.com/webhooks/shortcut
   # Should return: {"detail":"Method Not Allowed"} (that's OK, POST is expected)
   ```

3. **Check gateway logs**
   ```bash
   docker compose logs gateway | grep shortcut
   ```

### Crawler Returns 401 Unauthorized

1. **Verify API token**
   ```bash
   curl -X GET "https://api.app.shortcut.com/api/v3/member" \
     -H "Shortcut-Token: $SHORTCUT_API_TOKEN"
   # Should return your member info
   ```

2. **Check token expiration**
   - Tokens don't expire, but can be revoked
   - Regenerate if needed

### Stories Not Appearing in RAG

1. **Check if indexed**
   ```bash
   curl http://localhost:8000/v1/rag/search \
     -H "Content-Type: application/json" \
     -d '{"q":"authentication","top_k":5}'
   ```

2. **Verify connector ran**
   ```bash
   docker compose logs connectors | grep shortcut
   # Should show: "indexed 25 documents"
   ```

3. **Re-index if needed**
   ```bash
   curl -X POST http://localhost:8001/crawl/shortcut \
     -H "Content-Type: application/json" \
     -d '{"state_ids":[]}'  # Crawl all states
   ```

---

## Security Considerations

### Webhook Signature Verification

**Recommended for production:**

1. Generate a secret in Shortcut webhook settings
2. Add to environment: `SHORTCUT_WEBHOOK_SECRET=your_secret`
3. EM Agent will verify HMAC-SHA256 signature on all requests
4. Rejects invalid signatures with 401 Unauthorized

### API Token Storage

**Best practices:**

- ✅ Store in environment variables or secrets manager (Vault, AWS Secrets Manager)
- ✅ Rotate tokens annually
- ❌ Never commit tokens to git
- ❌ Don't share tokens between environments (dev/staging/prod should each have unique tokens)

### Network Security

- Use HTTPS for webhook endpoints (Let's Encrypt recommended)
- Consider IP allowlisting if Shortcut publishes their webhook IPs
- Rate limiting recommended (Shortcut can send bursts during bulk updates)

---

## Advanced: Delta Sync

For efficient crawling, track last sync timestamp:

```bash
# Initial full sync
curl -X POST http://localhost:8001/crawl/shortcut \
  -d '{"state_ids":["500000002","500000003"]}'

# Store last sync time
LAST_SYNC=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Next sync: only changed stories
curl -X POST http://localhost:8001/crawl/shortcut \
  -d '{
    "state_ids":["500000002","500000003"],
    "updated_since":"'"$LAST_SYNC"'"
  }'
```

This reduces API calls and improves performance for large workspaces.

---

## FAQ

### Can I track both Jira and Shortcut?

**Yes!** EM Agent supports multiple project management tools simultaneously. Events from both will flow through the same pipeline, dbt models aggregate across sources.

**Example:** GitHub PRs + Shortcut stories + Jira incidents = complete engineering metrics.

### Does this replace Shortcut's built-in reports?

**No, it complements them.** Shortcut has great built-in reports (velocity, burndown, etc.). EM Agent adds:
- Cross-tool metrics (PR cycle time + story cycle time)
- Custom policy enforcement (alert on stale stories)
- RAG-powered knowledge search
- Integration with Slack workflows

### What about epics and iterations?

**Supported!** Filter by `iteration_id` when crawling. Epics are indexed if you enable `epic-create`/`epic-update` webhooks.

### Performance at scale?

**Tested up to:**
- 10K stories in workspace
- 100 story updates/day
- <200ms webhook ingestion latency
- <5s crawler for 25 stories

For larger workspaces (>50K stories), consider:
- Incremental crawling (delta sync)
- Filtered crawling (only active iterations)
- Scheduled crawls during off-peak hours

---

## Roadmap

**Coming Soon:**

- [ ] Epic-level metrics (epic cycle time, epic WIP)
- [ ] Story estimation accuracy tracking (estimate vs actual)
- [ ] Shortcut → Slack notifications (story blocked, story completed)
- [ ] Custom fields support (priorities, labels, custom dropdowns)
- [ ] Iteration health scoring (velocity, scope creep)

**Submit feature requests:** https://github.com/evanhourigan/em-agent/issues

---

## Support

**Documentation:** https://github.com/evanhourigan/em-agent/tree/main/docs
**Issues:** https://github.com/evanhourigan/em-agent/issues
**Shortcut API Docs:** https://developer.shortcut.com/api/rest/v3

---

**Version:** 1.0
**Last Updated:** 2025-11-08
**Compatibility:** Shortcut API v3, EM Agent >= 0.2.0
