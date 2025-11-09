# GitHub Issues Integration Guide

**Track issue lifecycle and project management metrics using GitHub Issues**

---

## Overview

EM Agent supports **GitHub Issues** as a native project management integration. This allows you to:

- **Ingest issue updates** via webhooks (real-time)
- **Track issue lifecycle** (creation, state changes, labels, assignments, completion)
- **Enable metrics** using the same DORA framework as PRs
- **Correlate issues with PRs** for full delivery tracking

**Key Advantage:** If you're already using GitHub for code, adding issue tracking requires zero additional authentication or setup - the same webhook handles both!

---

## Quick Start

### 1. Set Up Webhook in GitHub

GitHub Issues events are received through the same webhook endpoint as PR events.

**If you already have a GitHub webhook configured:**
1. Go to your repo settings → Webhooks
2. Edit your existing webhook
3. Under "Which events would you like to trigger this webhook?", ensure **Issues** is checked
4. Save

**If you need to create a new webhook:**
1. Go to `https://github.com/YOUR_ORG/YOUR_REPO/settings/hooks`
2. Click **Add webhook**
3. **Payload URL:** `https://your-em-agent-domain.com/webhooks/github`
4. **Content type:** `application/json`
5. **Secret:** (optional, for signature verification - set `GITHUB_WEBHOOK_SECRET` env var)
6. **Events:** Select individual events:
   - ✅ Issues
   - ✅ Pull requests
   - ✅ Pushes
   - ✅ Workflow runs
7. Click **Add webhook**

### 2. Test the Integration

```bash
# Test webhook endpoint with a sample issue event
curl -X POST http://localhost:8000/webhooks/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: issues" \
  -H "X-GitHub-Delivery: test-12345" \
  -d '{
    "action": "opened",
    "issue": {
      "number": 42,
      "title": "Add authentication feature",
      "state": "open",
      "labels": [{"name": "feature"}],
      "assignee": {"login": "alice"}
    },
    "repository": {
      "name": "my-repo",
      "owner": {"login": "my-org"}
    }
  }'

# Should return: {"status":"ok","id":1}
```

### 3. Verify Event Storage

```bash
# Check that the event was stored
docker compose exec postgres psql -U em_agent -c \
  "SELECT id, source, event_type, delivery_id FROM events_raw WHERE source='github' AND event_type='issues' ORDER BY received_at DESC LIMIT 5;"
```

---

## Architecture

### Event Flow

```
GitHub Issues → Webhook → Gateway → events_raw → NATS → Workers
                                          ↓
                                      dbt models → Metrics API
```

1. **GitHub sends webhook** when issue is opened, closed, labeled, assigned, etc.
2. **Gateway stores** in `events_raw` table with `source='github'`, `event_type='issues'`
3. **NATS publishes** event to `events.github` topic
4. **dbt transforms** events into metrics (issue cycle time, WIP, velocity)
5. **Metrics API** exposes data for dashboards and alerts

### Why Issues + PRs Together?

Tracking both issues and PRs enables **full delivery lifecycle** metrics:

```
Issue Opened → PR Opened → PR Merged → Issue Closed
     |             |            |            |
  Planning      Coding       Review      Delivered
```

**Metrics Enabled:**
- **Plan-to-Code Time:** Time from issue creation to first PR
- **Code-to-Merge Time:** PR review and merge time (existing metric)
- **Merge-to-Close Time:** Deployment and verification time
- **Total Cycle Time:** Issue open → issue close

---

## Supported Events

### Issue Lifecycle Events

| Event Action | Description | Use Case |
|-------------|-------------|----------|
| `opened` | New issue created | Track new work entering the system |
| `closed` | Issue closed/resolved | Calculate cycle time, throughput |
| `reopened` | Closed issue reopened | Track rework rate |
| `assigned` | Issue assigned to user | WIP tracking per engineer |
| `unassigned` | Assignment removed | Capacity management |
| `labeled` | Label added | Categorize work (bug, feature, tech debt) |
| `unlabeled` | Label removed | Track changing priorities |
| `milestoned` | Added to milestone | Sprint/release planning |
| `demilestoned` | Removed from milestone | Scope changes |

### Example Webhook Payload

```json
{
  "action": "opened",
  "issue": {
    "id": 123456789,
    "number": 42,
    "title": "Implement user authentication",
    "state": "open",
    "labels": [
      {"name": "feature"},
      {"name": "priority-high"}
    ],
    "assignee": {
      "login": "alice"
    },
    "milestone": {
      "title": "v1.0"
    },
    "created_at": "2025-11-09T10:00:00Z",
    "updated_at": "2025-11-09T10:00:00Z"
  },
  "repository": {
    "name": "em-agent",
    "owner": {"login": "evanhourigan"}
  }
}
```

---

## Configuration Options

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GITHUB_WEBHOOK_SECRET` | No | HMAC secret for signature verification (recommended for production) |

**Note:** GitHub Issues use the same webhook endpoint as PRs, so no additional configuration is needed beyond the existing GitHub integration.

---

## dbt Metrics Integration

Once issue events are flowing, you can create dbt models to calculate project management metrics:

### Issue Cycle Time

```sql
-- Calculate average time from issue open to close
WITH issue_lifecycle AS (
  SELECT
    payload::json->'issue'->>'number' as issue_number,
    MIN(CASE WHEN payload::json->>'action' = 'opened' THEN received_at END) as opened_at,
    MAX(CASE WHEN payload::json->>'action' = 'closed' THEN received_at END) as closed_at
  FROM events_raw
  WHERE source = 'github'
    AND event_type = 'issues'
  GROUP BY 1
)
SELECT
  issue_number,
  EXTRACT(epoch FROM closed_at - opened_at) / 3600 as cycle_time_hours
FROM issue_lifecycle
WHERE closed_at IS NOT NULL;
```

### WIP Tracking

```sql
-- Track work-in-progress by assignee
SELECT
  payload::json->'assignee'->>'login' as assignee,
  COUNT(DISTINCT payload::json->'issue'->>'number') as open_issues
FROM events_raw
WHERE source = 'github'
  AND event_type = 'issues'
  AND payload::json->>'action' = 'assigned'
  AND payload::json->'issue'->>'state' = 'open'
GROUP BY 1
ORDER BY 2 DESC;
```

### Label Distribution

```sql
-- Track issue types (bug vs feature vs tech debt)
SELECT
  label->>'name' as label,
  COUNT(DISTINCT payload::json->'issue'->>'number') as issue_count
FROM events_raw,
  json_array_elements(payload::json->'issue'->'labels') as label
WHERE source = 'github'
  AND event_type = 'issues'
  AND payload::json->>'action' = 'labeled'
GROUP BY 1
ORDER BY 2 DESC;
```

### Issue-to-PR Correlation

```sql
-- Find PRs that reference issues (via "closes #42" syntax)
WITH issue_prs AS (
  SELECT
    payload::json->'pull_request'->>'number' as pr_number,
    payload::json->'pull_request'->>'body' as pr_body,
    regexp_matches(
      payload::json->'pull_request'->>'body',
      'closes #(\d+)',
      'gi'
    ) as issue_refs
  FROM events_raw
  WHERE source = 'github'
    AND event_type = 'pull_request'
    AND payload::json->>'action' = 'opened'
)
SELECT
  pr_number,
  array_agg(DISTINCT (issue_refs[1])::int) as closed_issues
FROM issue_prs
WHERE issue_refs IS NOT NULL
GROUP BY 1;
```

---

## Use Cases

### 1. Sprint Velocity Tracking

Track issues completed per sprint using milestones:

```bash
# Query completed issues in milestone "Sprint 12"
curl http://localhost:8000/v1/metrics/issues \
  -H "Content-Type: application/json" \
  -d '{
    "filters": {
      "milestone": "Sprint 12",
      "state": "closed"
    }
  }'
```

**Metric:** Count of closed issues = sprint velocity

### 2. Bug Escape Rate

Track how many bugs are opened after release:

```sql
-- Bugs labeled after PR merge
SELECT
  COUNT(*) as bugs_after_merge
FROM events_raw
WHERE source = 'github'
  AND event_type = 'issues'
  AND payload::json->>'action' = 'labeled'
  AND payload::json->'label'->>'name' = 'bug'
  AND received_at > (
    SELECT MAX(received_at)
    FROM events_raw
    WHERE source = 'github'
      AND event_type = 'pull_request'
      AND payload::json->>'action' = 'closed'
      AND payload::json->'pull_request'->>'merged' = 'true'
  );
```

**Metric:** Bugs opened / PRs merged = bug escape rate

### 3. Stale Issue Detection

Alert on issues that have been open for too long:

```sql
-- Issues open longer than 30 days
WITH open_issues AS (
  SELECT
    payload::json->'issue'->>'number' as issue_number,
    payload::json->'issue'->>'title' as title,
    MIN(received_at) as opened_at
  FROM events_raw
  WHERE source = 'github'
    AND event_type = 'issues'
    AND payload::json->>'action' = 'opened'
  GROUP BY 1, 2
)
SELECT
  issue_number,
  title,
  EXTRACT(epoch FROM NOW() - opened_at) / 86400 as days_open
FROM open_issues
WHERE EXTRACT(epoch FROM NOW() - opened_at) / 86400 > 30
ORDER BY days_open DESC;
```

**Use with Policy Engine:** Create OPA rule to auto-ping assignees on stale issues.

---

## Comparison: Issues vs. Other Trackers

| Feature | GitHub Issues | Jira | Shortcut | Linear |
|---------|--------------|------|----------|--------|
| **Setup** | ✅ Zero config (same webhook as PRs) | ⚠️ Separate integration | ⚠️ Separate integration | ⚠️ Separate integration |
| **PR Linking** | ✅ Native (closes #42) | ⚠️ Manual JIRA-123 | ⚠️ Manual sc-123 | ✅ Native |
| **Simplicity** | ✅ Labels + milestones | ❌ Complex workflows | ✅ Simple states | ✅ Simple states |
| **Cost** | ✅ Free | ❌ $$ per user | ⚠️ $ per user | ⚠️ $ per user |
| **Best For** | Open source, small teams | Enterprise | Startups | Modern teams |

**Key Advantage:** If your code is on GitHub, Issues provides the tightest integration with zero additional auth setup.

---

## Troubleshooting

### Webhook Not Receiving Issue Events

1. **Check webhook configuration**
   - Go to `https://github.com/YOUR_ORG/YOUR_REPO/settings/hooks`
   - Click on your webhook
   - Scroll to "Recent Deliveries"
   - Click on a delivery to see request/response

2. **Verify "Issues" event is enabled**
   - Edit webhook
   - Under "Which events would you like to trigger this webhook?"
   - Ensure **Issues** is checked

3. **Check gateway logs**
   ```bash
   docker compose logs gateway | grep "X-GitHub-Event: issues"
   ```

### Events Stored But Not in dbt Models

1. **Check event_type format**
   ```bash
   docker compose exec postgres psql -U em_agent -c \
     "SELECT DISTINCT event_type FROM events_raw WHERE source='github';"
   ```

   Should include: `issues`

2. **Verify dbt models are running**
   ```bash
   docker compose exec dbt dbt run --models tag:github
   ```

### Missing Issue-PR Correlation

**Problem:** PRs don't link to issues

**Solution:** Use GitHub's closing keywords in PR descriptions:
- `closes #42`
- `fixes #42`
- `resolves #42`

These are parsed by dbt models to correlate issues with PRs.

---

## Security Considerations

### Webhook Signature Verification

**Recommended for production:**

1. Generate a secret token
2. Add to GitHub webhook settings
3. Set environment variable: `GITHUB_WEBHOOK_SECRET=your_secret`
4. EM Agent will verify HMAC-SHA256 signature on all requests
5. Rejects invalid signatures with 401 Unauthorized

### Fine-Grained Permissions

When creating GitHub Apps or Personal Access Tokens:

**Minimum permissions needed:**
- Repository webhooks: Read & Write
- Issues: Read-only
- Pull requests: Read-only

**NOT needed:**
- Code access
- Admin permissions
- Org permissions

---

## Advanced: GitHub Projects Integration

GitHub Projects (Kanban boards) can also be tracked:

```bash
# Enable project events in webhook
# Events: "Projects", "Project Cards"
```

**Use Case:** Track cards moving between columns (Backlog → In Progress → Done) for Kanban metrics.

---

## FAQ

### Can I track issues from multiple repos?

**Yes!** Configure webhooks for each repo pointing to the same EM Agent endpoint. Events will be stored with repository info in the payload.

```sql
-- Filter by repo
SELECT *
FROM events_raw
WHERE source = 'github'
  AND event_type = 'issues'
  AND payload::json->'repository'->>'name' = 'my-repo';
```

### Do I need GitHub Enterprise?

**No.** GitHub Issues webhooks work on:
- ✅ GitHub.com (free tier)
- ✅ GitHub Pro
- ✅ GitHub Enterprise Cloud
- ✅ GitHub Enterprise Server

### What about GitHub Discussions?

**Supported!** Add "Discussions" to your webhook events. They'll be stored as `event_type='discussion'`.

**Use Case:** Track community questions for support metrics.

### Can I create issues from EM Agent?

**Not yet.** Current integration is **read-only** (webhook ingestion).

**Roadmap:** Bidirectional sync (create/update issues via GitHub API) coming in Phase 7.

---

## Roadmap

**Coming Soon:**

- [ ] Issue creation via Slack (`/em-agent create-issue "Bug in login"`)
- [ ] Auto-labeling based on content (ML-powered)
- [ ] Issue → Slack thread sync (discuss issues in Slack)
- [ ] Custom fields tracking (projects, effort estimates)
- [ ] Advanced issue-PR correlation (detect implicit links)

**Submit feature requests:** https://github.com/evanhourigan/em-agent/issues

---

## Support

**Documentation:** https://github.com/evanhourigan/em-agent/tree/main/docs
**Issues:** https://github.com/evanhourigan/em-agent/issues
**GitHub Webhooks Docs:** https://docs.github.com/en/webhooks/webhook-events-and-payloads#issues

---

**Version:** 1.0
**Last Updated:** 2025-11-09
**Compatibility:** GitHub REST API v3, EM Agent >= 0.2.0
