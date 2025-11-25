-- Mean Time To Restore (MTTR): time from incident detection to resolution
-- Tracks incidents from PagerDuty, Sentry, and Datadog

WITH incidents AS (
  -- PagerDuty incidents (triggered → resolved)
  SELECT
    payload::json->'incident'->>'id' AS incident_id,
    'pagerduty' AS source,
    payload::json->'incident'->>'title' AS title,
    MIN(CASE WHEN event_type = 'incident.triggered' THEN received_at END) AS triggered_at,
    MIN(CASE WHEN event_type = 'incident.resolved' THEN received_at END) AS resolved_at
  FROM public.events_raw
  WHERE source = 'pagerduty'
    AND event_type IN ('incident.triggered', 'incident.resolved')
  GROUP BY payload::json->'incident'->>'id', payload::json->'incident'->>'title'

  UNION ALL

  -- Sentry issues (created → resolved)
  SELECT
    payload::json->'data'->'issue'->>'id' AS incident_id,
    'sentry' AS source,
    payload::json->'data'->'issue'->>'title' AS title,
    MIN(CASE WHEN event_type LIKE 'issue.created%' THEN received_at END) AS triggered_at,
    MIN(CASE WHEN event_type LIKE 'issue.resolved%' THEN received_at END) AS resolved_at
  FROM public.events_raw
  WHERE source = 'sentry'
    AND event_type IN ('issue.created', 'issue.resolved')
  GROUP BY payload::json->'data'->'issue'->>'id', payload::json->'data'->'issue'->>'title'

  UNION ALL

  -- Datadog monitors (triggered → recovered)
  -- Note: Datadog doesn't always have distinct IDs, so we group by alert content
  SELECT
    COALESCE(payload::json->>'alert_id', payload::json->>'id')::TEXT AS incident_id,
    'datadog' AS source,
    payload::json->>'title' AS title,
    MIN(CASE WHEN event_type LIKE 'monitor_%' OR payload::json->>'event_type' = 'trigger' THEN received_at END) AS triggered_at,
    MIN(CASE WHEN payload::json->>'event_type' = 'recovery' THEN received_at END) AS resolved_at
  FROM public.events_raw
  WHERE source = 'datadog'
    AND (event_type LIKE 'monitor_%' OR payload::json->>'event_type' IN ('trigger', 'recovery'))
  GROUP BY incident_id, payload::json->>'title'
)
SELECT
  incident_id,
  source,
  title,
  triggered_at,
  resolved_at,
  EXTRACT(EPOCH FROM (resolved_at - triggered_at)) / 3600.0 AS mttr_hours,
  EXTRACT(EPOCH FROM (resolved_at - triggered_at)) / 60.0 AS mttr_minutes
FROM incidents
WHERE triggered_at IS NOT NULL
  AND resolved_at IS NOT NULL
  AND resolved_at > triggered_at
ORDER BY triggered_at DESC

