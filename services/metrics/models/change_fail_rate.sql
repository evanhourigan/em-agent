-- Change Failure Rate: percentage of deployments that cause incidents
-- Correlates successful deployments with incidents from Sentry, Datadog, or PagerDuty
-- that occur within 24 hours after deployment

WITH deployments AS (
  SELECT
    id,
    payload::json->'repository'->>'full_name' AS repo,
    payload::json->'workflow_run'->>'name' AS workflow_name,
    received_at AS deployed_at
  FROM public.events_raw
  WHERE source = 'github'
    AND event_type = 'workflow_run'
    AND payload::json->>'action' = 'completed'
    AND payload::json->'workflow_run'->>'conclusion' = 'success'
    AND (
      payload::json->'workflow_run'->>'name' ILIKE '%deploy%'
      OR payload::json->'workflow_run'->>'name' ILIKE '%production%'
    )
),
incidents AS (
  -- Sentry errors/issues
  SELECT
    payload::json->'data'->'issue'->>'title' AS incident_title,
    'sentry' AS incident_source,
    received_at AS incident_at
  FROM public.events_raw
  WHERE source = 'sentry'
    AND event_type LIKE 'issue.created%'

  UNION ALL

  -- Datadog monitor alerts
  SELECT
    payload::json->>'title' AS incident_title,
    'datadog' AS incident_source,
    received_at AS incident_at
  FROM public.events_raw
  WHERE source = 'datadog'
    AND (
      event_type LIKE 'monitor_%'
      OR payload::json->>'alert_type' IN ('error', 'warning')
    )

  UNION ALL

  -- PagerDuty incidents
  SELECT
    payload::json->'incident'->>'title' AS incident_title,
    'pagerduty' AS incident_source,
    received_at AS incident_at
  FROM public.events_raw
  WHERE source = 'pagerduty'
    AND event_type = 'incident.triggered'
),
deployments_with_incidents AS (
  SELECT
    d.id,
    d.repo,
    d.workflow_name,
    d.deployed_at,
    COUNT(i.incident_title) AS incident_count,
    CASE WHEN COUNT(i.incident_title) > 0 THEN 1 ELSE 0 END AS failed
  FROM deployments d
  LEFT JOIN incidents i
    ON i.incident_at >= d.deployed_at
    AND i.incident_at <= d.deployed_at + INTERVAL '24 hours'
  GROUP BY d.id, d.repo, d.workflow_name, d.deployed_at
)
SELECT
  date_trunc('week', deployed_at) AS week,
  COUNT(*) AS total_deployments,
  SUM(failed) AS failed_deployments,
  ROUND(100.0 * SUM(failed) / NULLIF(COUNT(*), 0), 2) AS change_fail_rate_pct
FROM deployments_with_incidents
GROUP BY 1
ORDER BY 1 DESC

