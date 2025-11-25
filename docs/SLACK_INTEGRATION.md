# Slack Integration Guide

**Status:** ✅ Production Ready
**Version:** 1.0
**Last Updated:** 2025-11-19

---

## Overview

The EM Agent Slack integration captures communication events from your Slack workspace to provide context for engineering operations, incident response, and team collaboration analysis.

This integration enables:
- **Communication Context**: Track discussions around incidents, deployments, and projects
- **Team Activity**: Monitor channel joins, mentions, and engagement patterns
- **Incident Timelines**: Correlate Slack activity with incident lifecycle
- **DORA Metrics Enhancement**: Understand communication patterns during deployments and incidents

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Slack Workspace                         │
│  • Channels (#engineering, #incidents, #deployments)        │
│  • Messages, Reactions, Mentions                             │
│  • File Shares, User Activity                                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ HTTPS POST
                         │ (Events API)
                         │
                    ┌────▼─────┐
                    │  Gateway │  (port 8000)
                    │  Service │
                    └────┬─────┘
                         │
                    ┌────▼──────┐
                    │events_raw │  PostgreSQL
                    │   Table   │
                    └────┬──────┘
                         │
                    ┌────▼─────┐
                    │   NATS   │  Event Bus
                    │  Stream  │
                    └──────────┘
```

---

## Features

### ✅ Real-time Event Capture

**Supported Event Types:**
- `message`: Channel messages and threads
- `reaction_added` / `reaction_removed`: Emoji reactions
- `app_mention`: Bot mentions (@em-agent)
- `member_joined_channel` / `member_left_channel`: Channel membership changes
- `file_shared`: File uploads and shares
- `channel_created` / `channel_archived`: Channel lifecycle
- Any other Slack Events API event

### ✅ Idempotency

- Uses Slack's `event_id` for deduplication
- Duplicate events return same database ID
- Prevents event replay and race conditions

### ✅ Security

- **Optional Signature Verification**: HMAC-SHA256 validation using signing secret
- **Timestamp Validation**: Prevents replay attacks (5-minute window)
- **Configurable Security**: Enable/disable signature checking per environment

### ✅ Storage

- **Immutable Events**: All events stored in `events_raw` table
- **Full Payload**: Complete JSON preserved for reprocessing
- **Headers Captured**: All HTTP headers stored for debugging
- **Event Bus Publishing**: Events published to NATS for downstream processing

---

## Setup Guide

### Step 1: Create Slack App

1. Go to [https://api.slack.com/apps](https://api.slack.com/apps)
2. Click **"Create New App"** → **"From scratch"**
3. Name: `EM Agent` (or your preferred name)
4. Select your workspace
5. Click **"Create App"**

### Step 2: Configure Event Subscriptions

1. In your Slack app settings, navigate to **"Event Subscriptions"**
2. Toggle **"Enable Events"** to ON
3. Set **Request URL** to:
   ```
   https://your-domain.com/webhooks/slack
   ```

   **Local Development:**
   ```
   https://your-ngrok-url.ngrok.io/webhooks/slack
   ```

4. Slack will send a verification challenge - the endpoint handles this automatically

### Step 3: Subscribe to Bot Events

In the **"Subscribe to bot events"** section, add these events:

**Recommended Events:**
- `message.channels` - Messages in public channels
- `message.groups` - Messages in private channels (if bot is member)
- `reaction_added` - Emoji reactions added
- `reaction_removed` - Emoji reactions removed
- `app_mention` - Bot mentions
- `member_joined_channel` - User joins channel
- `member_left_channel` - User leaves channel
- `file_shared` - Files uploaded to channels

**Optional Events (for advanced use cases):**
- `channel_created` - New channel created
- `channel_archived` - Channel archived
- `channel_rename` - Channel renamed
- `user_change` - User profile updated

Click **"Save Changes"**

### Step 4: Install App to Workspace

1. Navigate to **"Install App"** in sidebar
2. Click **"Install to Workspace"**
3. Review permissions and click **"Allow"**
4. Copy the **"Bot User OAuth Token"** (starts with `xoxb-`)

### Step 5: Configure Signing Secret (Optional but Recommended)

1. Navigate to **"Basic Information"**
2. Find **"Signing Secret"** under "App Credentials"
3. Click **"Show"** and copy the secret

### Step 6: Set Environment Variables

Add to your `.env` file or environment:

```bash
# Slack Configuration
SLACK_WEBHOOK_SECRET=your_signing_secret_here
SLACK_SIGNING_REQUIRED=true  # Set to false to disable signature verification

# Optional: For bot interactions (slash commands, etc.)
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_DEFAULT_CHANNEL=#incidents
```

### Step 7: Restart Gateway Service

```bash
docker compose restart gateway
```

### Step 8: Verify Integration

Check the gateway logs to see the verification challenge:

```bash
docker compose logs gateway --tail=50
```

You should see successful event processing.

---

## Testing the Integration

### Manual Test with curl

```bash
# Test URL verification
curl -X POST http://localhost:8000/webhooks/slack \
  -H "Content-Type: application/json" \
  -d '{
    "type": "url_verification",
    "challenge": "test_challenge_123",
    "token": "deprecated_token"
  }'

# Expected response:
# {"challenge":"test_challenge_123"}
```

### Test with Real Slack Events

1. Invite the bot to a channel:
   ```
   /invite @em-agent
   ```

2. Post a message in the channel:
   ```
   Hello @em-agent!
   ```

3. Check that events are being stored:
   ```bash
   docker compose exec db psql -U postgres -c \
     "SELECT id, event_type, delivery_id, received_at
      FROM events_raw
      WHERE source='slack'
      ORDER BY received_at DESC
      LIMIT 5;"
   ```

---

## Event Schema

### Webhook Endpoint

```
POST /webhooks/slack
```

### Request Headers

| Header | Required | Description |
|--------|----------|-------------|
| `Content-Type` | Yes | `application/json` |
| `X-Slack-Request-Timestamp` | No | Unix timestamp of request |
| `X-Slack-Signature` | No | HMAC-SHA256 signature |

### Request Payload (URL Verification)

```json
{
  "type": "url_verification",
  "challenge": "3eZbrw1aBm2rZgRNFdxV2595E9CY3gmdALWMmHkvFXO7tYXAYM8P",
  "token": "Jhj5dZrVaK7ZwHHjRyZWjbDl"
}
```

**Response:**
```json
{
  "challenge": "3eZbrw1aBm2rZgRNFdxV2595E9CY3gmdALWMmHkvFXO7tYXAYM8P"
}
```

### Request Payload (Message Event)

```json
{
  "token": "deprecated_verification_token",
  "team_id": "T061EG9R6",
  "api_app_id": "A0FFV41KK",
  "event": {
    "type": "message",
    "channel": "C061EG9T2",
    "user": "U061F7AUR",
    "text": "Hello world!",
    "ts": "1234567890.123456",
    "event_ts": "1234567890.123456",
    "channel_type": "channel"
  },
  "type": "event_callback",
  "event_id": "Ev06BN0FJF",
  "event_time": 1234567890
}
```

**Response:**
```json
{
  "status": "ok",
  "id": 42
}
```

### Database Storage

Events are stored in the `events_raw` table:

| Column | Type | Example | Description |
|--------|------|---------|-------------|
| `id` | SERIAL | 42 | Unique event ID |
| `source` | VARCHAR(50) | `slack` | Always "slack" |
| `event_type` | VARCHAR(100) | `message` | Slack event type |
| `delivery_id` | VARCHAR(255) | `slack-Ev06BN0FJF` | Unique delivery ID (event_id) |
| `signature` | VARCHAR(255) | `v0=a2114...` | HMAC signature (if provided) |
| `headers` | JSONB | `{...}` | All HTTP headers |
| `payload` | TEXT | `{...}` | Full JSON payload |
| `received_at` | TIMESTAMP | `2025-11-19 10:30:00` | Ingestion timestamp |

---

## Event Types Reference

### Message Events

**Type:** `message`

```json
{
  "event": {
    "type": "message",
    "channel": "C061EG9T2",
    "user": "U061F7AUR",
    "text": "Deploying v2.3.0 to production",
    "ts": "1234567890.123456",
    "thread_ts": "1234567880.123456"  // Present if threaded
  }
}
```

**Use Cases:**
- Track deployment announcements
- Incident communication timelines
- Team collaboration patterns

### Reaction Events

**Type:** `reaction_added` / `reaction_removed`

```json
{
  "event": {
    "type": "reaction_added",
    "user": "U061F7AUR",
    "reaction": "white_check_mark",
    "item": {
      "type": "message",
      "channel": "C061EG9T2",
      "ts": "1234567890.123456"
    },
    "event_ts": "1234567891.000001"
  }
}
```

**Use Cases:**
- Acknowledgment tracking
- Approval workflows (✅ = approved)
- Sentiment analysis

### App Mention Events

**Type:** `app_mention`

```json
{
  "event": {
    "type": "app_mention",
    "user": "U061F7AUR",
    "text": "<@U0G9QF9C6> help with incident INC-123",
    "ts": "1234567892.123456",
    "channel": "C061EG9T2"
  }
}
```

**Use Cases:**
- Bot interaction triggers
- Manual incident reporting
- Team assistance requests

### Channel Join Events

**Type:** `member_joined_channel`

```json
{
  "event": {
    "type": "member_joined_channel",
    "user": "U061F7AUR",
    "channel": "C061EG9T2",
    "channel_type": "C",
    "team": "T061EG9R6",
    "inviter": "U123ABC456"
  }
}
```

**Use Cases:**
- Incident responder tracking
- Team expansion monitoring
- Onboarding analytics

---

## Security Configuration

### Production (Signature Verification Enabled)

```bash
# .env
SLACK_SIGNING_REQUIRED=true
SLACK_WEBHOOK_SECRET=abc123def456...
```

The webhook validates:
1. **Timestamp freshness**: Request must be within 5 minutes
2. **HMAC-SHA256 signature**: Computed as:
   ```
   v0=HMAC-SHA256(signing_secret, "v0:{timestamp}:{body}")
   ```

### Development (Signature Verification Disabled)

```bash
# .env
SLACK_SIGNING_REQUIRED=false
```

**⚠️ Warning:** Only disable signature verification in local development. Always enable in production.

---

## Querying Slack Events

### Recent Messages

```sql
SELECT
  id,
  event_type,
  payload::json->'event'->>'text' as message_text,
  payload::json->'event'->>'channel' as channel_id,
  received_at
FROM events_raw
WHERE source = 'slack'
  AND event_type = 'message'
ORDER BY received_at DESC
LIMIT 10;
```

### Messages in Date Range

```sql
SELECT
  payload::json->'event'->>'text' as message,
  payload::json->'event'->>'user' as user_id,
  received_at
FROM events_raw
WHERE source = 'slack'
  AND event_type = 'message'
  AND received_at BETWEEN '2025-11-19 00:00:00' AND '2025-11-19 23:59:59'
ORDER BY received_at DESC;
```

### Reaction Summary

```sql
SELECT
  payload::json->'event'->>'reaction' as emoji,
  COUNT(*) as count
FROM events_raw
WHERE source = 'slack'
  AND event_type = 'reaction_added'
GROUP BY emoji
ORDER BY count DESC;
```

### Channel Activity

```sql
SELECT
  payload::json->'event'->>'channel' as channel_id,
  event_type,
  COUNT(*) as event_count
FROM events_raw
WHERE source = 'slack'
GROUP BY channel_id, event_type
ORDER BY event_count DESC;
```

---

## Use Cases & Examples

### 1. Incident Timeline Reconstruction

Track all Slack activity during an incident:

```sql
SELECT
  received_at,
  event_type,
  payload::json->'event'->>'text' as content,
  payload::json->'event'->>'user' as user_id
FROM events_raw
WHERE source = 'slack'
  AND payload::json->'event'->>'channel' = 'C_INCIDENTS'
  AND received_at BETWEEN
    (SELECT created_at FROM incidents WHERE id = 'INC-123') AND
    (SELECT resolved_at FROM incidents WHERE id = 'INC-123')
ORDER BY received_at ASC;
```

### 2. Deployment Communication Tracking

Find deployment-related messages:

```sql
SELECT
  received_at,
  payload::json->'event'->>'text' as message,
  payload::json->'event'->>'user' as deployer
FROM events_raw
WHERE source = 'slack'
  AND event_type = 'message'
  AND (
    payload::json->'event'->>'text' ILIKE '%deploy%' OR
    payload::json->'event'->>'text' ILIKE '%release%'
  )
ORDER BY received_at DESC;
```

### 3. Team Response Time Analysis

Measure time to first reaction (acknowledgment):

```sql
WITH messages AS (
  SELECT
    payload::json->'event'->>'ts' as msg_ts,
    payload::json->'event'->>'channel' as channel,
    received_at as message_time
  FROM events_raw
  WHERE source = 'slack'
    AND event_type = 'message'
    AND payload::json->'event'->>'text' ILIKE '%incident%'
),
reactions AS (
  SELECT
    payload::json->'event'->'item'->>'ts' as msg_ts,
    MIN(received_at) as first_reaction_time
  FROM events_raw
  WHERE source = 'slack'
    AND event_type = 'reaction_added'
  GROUP BY msg_ts
)
SELECT
  m.msg_ts,
  m.message_time,
  r.first_reaction_time,
  EXTRACT(EPOCH FROM (r.first_reaction_time - m.message_time)) / 60 as response_minutes
FROM messages m
LEFT JOIN reactions r ON m.msg_ts = r.msg_ts
ORDER BY response_minutes ASC NULLS LAST;
```

---

## Troubleshooting

### Problem: Verification Challenge Fails

**Symptoms:**
- Slack shows "Your URL didn't respond with the value of the challenge parameter"

**Solution:**
1. Check gateway is running: `docker compose ps gateway`
2. Check logs: `docker compose logs gateway --tail=50`
3. Verify URL is publicly accessible (use ngrok for local dev)
4. Test endpoint manually:
   ```bash
   curl -X POST https://your-domain.com/webhooks/slack \
     -H "Content-Type: application/json" \
     -d '{"type":"url_verification","challenge":"test123","token":"test"}'
   ```

### Problem: Events Not Being Stored

**Symptoms:**
- Slack shows events sent successfully
- Database queries return no results

**Solution:**
1. Check database connection:
   ```bash
   docker compose exec db psql -U postgres -c "SELECT COUNT(*) FROM events_raw WHERE source='slack';"
   ```

2. Check gateway logs for errors:
   ```bash
   docker compose logs gateway | grep -i slack
   ```

3. Verify idempotency isn't blocking events (check for duplicate event_ids)

### Problem: Signature Verification Fails

**Symptoms:**
- HTTP 401 errors in gateway logs
- "invalid signature" in error details

**Solution:**
1. Verify signing secret is correct:
   - Compare `.env` value with Slack app settings
   - Ensure no extra spaces or quotes

2. Check timestamp drift:
   - Ensure server time is accurate (NTP synchronized)
   - Verify firewall isn't delaying requests >5 minutes

3. Temporarily disable for testing:
   ```bash
   SLACK_SIGNING_REQUIRED=false
   docker compose restart gateway
   ```

### Problem: Too Many Events / Rate Limiting

**Symptoms:**
- Database growing rapidly
- High CPU/memory usage
- Slow query performance

**Solution:**
1. **Filter events at Slack app level:**
   - Only subscribe to needed event types
   - Unsubscribe from high-volume events like `message.im` (DMs)

2. **Implement event filtering in webhook handler** (future enhancement)

3. **Add database partitioning:**
   ```sql
   -- Partition events_raw by date
   CREATE TABLE events_raw_2025_11 PARTITION OF events_raw
   FOR VALUES FROM ('2025-11-01') TO ('2025-12-01');
   ```

4. **Archive old events:**
   ```sql
   DELETE FROM events_raw
   WHERE source = 'slack'
     AND received_at < NOW() - INTERVAL '90 days';
   ```

---

## Performance Considerations

### Event Volume Estimation

**Typical Slack workspace (50 users):**
- ~500 messages/day → ~15,000/month
- ~200 reactions/day → ~6,000/month
- ~50 channel joins/day → ~1,500/month

**Database Growth:**
- Average event size: ~2KB
- Monthly storage: ~45MB (500 events/day * 2KB * 30 days)
- Yearly storage: ~540MB

### Optimization Tips

1. **Index frequently queried fields:**
   ```sql
   CREATE INDEX idx_slack_events_channel
   ON events_raw ((payload::json->'event'->>'channel'))
   WHERE source = 'slack';

   CREATE INDEX idx_slack_events_type
   ON events_raw (event_type)
   WHERE source = 'slack';
   ```

2. **Use JSONB for payload** (requires migration):
   ```sql
   ALTER TABLE events_raw
   ALTER COLUMN payload TYPE JSONB
   USING payload::JSONB;
   ```

3. **Implement event sampling for high-volume channels:**
   - Only capture every Nth message in noisy channels
   - Focus on critical channels (#incidents, #deployments)

---

## Integration with Other Services

### NATS Event Bus

All Slack events are published to NATS subject `events.slack`:

```python
# Subscribe to Slack events
import asyncio
from nats.aio.client import Client as NATS

nc = NATS()
await nc.connect("nats://localhost:4222")

async def message_handler(msg):
    data = json.loads(msg.data.decode())
    print(f"Received Slack event: {data['event_type']}")

    # Process event (e.g., trigger incident workflow)
    if data['event_type'] == 'app_mention':
        # Handle bot mention
        pass

await nc.subscribe("events.slack", cb=message_handler)
```

### RAG Indexing

Slack messages can be indexed for semantic search:

```bash
# Index Slack messages for searchability
curl -X POST http://localhost:8001/index/bulk \
  -H "Content-Type: application/json" \
  -d '{
    "documents": [
      {
        "id": "slack-msg-123",
        "text": "Deploying v2.3.0 to production. All checks passed.",
        "metadata": {
          "source": "slack",
          "channel": "C061EG9T2",
          "user": "U061F7AUR",
          "ts": "1234567890.123456"
        }
      }
    ]
  }'
```

### Future Enhancements

Planned features for the Slack integration:

- [ ] **Bi-directional integration**: Post to Slack from EM Agent
- [ ] **Slash commands**: `/em incident create`, `/em deploy status`
- [ ] **Interactive messages**: Approve deployments, ack incidents via buttons
- [ ] **User mapping**: Link Slack users to GitHub/Jira identities
- [ ] **Channel auto-archival**: Archive incident channels after resolution
- [ ] **Thread summarization**: AI-powered summaries of long threads
- [ ] **Sentiment analysis**: Track team mood during incidents

---

## API Reference

### Webhook Handler

**File:** `services/gateway/app/api/v1/routers/webhooks.py:404-507`

**Function:** `slack_webhook()`

**Parameters:**
- `request: Request` - FastAPI request object
- `session: Session` - Database session
- `x_slack_request_timestamp: str | None` - Request timestamp header
- `x_slack_signature: str | None` - HMAC signature header

**Returns:**
```python
{
    "status": "ok",
    "id": int  # Database event ID
}
```

**Special Cases:**
- URL verification returns: `{"challenge": str}`
- Duplicate events return same ID: `{"status": "ok", "id": existing_id}`
- Signature failure raises: `HTTPException(401, "invalid signature")`

---

## Testing

### Unit Tests

**File:** `tests/gateway/test_webhooks.py:958-1164`

**Test Cases:**
1. `test_slack_url_verification` - URL verification challenge
2. `test_slack_webhook_message_event` - Message event handling
3. `test_slack_webhook_reaction_added` - Reaction event
4. `test_slack_webhook_app_mention` - Bot mention event
5. `test_slack_webhook_idempotency` - Duplicate event handling
6. `test_slack_webhook_member_joined_channel` - Channel join event

**Run tests:**
```bash
pytest tests/gateway/test_webhooks.py::TestSlackWebhook -v
```

### Manual Testing

See "Testing the Integration" section above.

---

## Support & Resources

### Official Documentation
- [Slack Events API](https://api.slack.com/events-api)
- [Event Types Reference](https://api.slack.com/events)
- [Signature Verification](https://api.slack.com/authentication/verifying-requests-from-slack)

### EM Agent Resources
- Architecture: `docs/ARCHITECTURE_DEEP_DIVE.md`
- Other Integrations: `docs/LINEAR_INTEGRATION.md`, `docs/PAGERDUTY_INTEGRATION.md`
- Database Schema: `services/gateway/migrations/versions/0003_events_raw.py`

### Getting Help
- Review gateway logs: `docker compose logs gateway -f`
- Check database: `docker compose exec db psql -U postgres`
- Verify webhook endpoint: `curl http://localhost:8000/health`

---

**Document Version:** 1.0
**Integration Status:** ✅ Production Ready
**Last Tested:** 2025-11-19
**Test Coverage:** 6 test cases, all passing
