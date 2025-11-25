-- Deployment frequency: daily count of successful deployments across all CI/CD platforms
-- Tracks deployments from GitHub Actions, CircleCI, Jenkins, and GitLab CI
WITH github_deployments AS (
  -- GitHub Actions workflow_run events
  SELECT
    received_at,
    'github' AS platform,
    payload::json->'workflow_run'->>'name' AS workflow_name
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
circleci_deployments AS (
  -- CircleCI workflow-completed events
  SELECT
    received_at,
    'circleci' AS platform,
    payload::json->'workflow'->>'name' AS workflow_name
  FROM public.events_raw
  WHERE source = 'circleci'
    AND event_type = 'workflow-completed'
    AND payload::json->'workflow'->>'status' = 'success'
    AND (
      payload::json->'workflow'->>'name' ILIKE '%deploy%'
      OR payload::json->'workflow'->>'name' ILIKE '%production%'
      OR payload::json->'pipeline'->>'name' ILIKE '%deploy%'
    )
),
jenkins_deployments AS (
  -- Jenkins build_success events
  SELECT
    received_at,
    'jenkins' AS platform,
    payload::json->>'name' AS workflow_name
  FROM public.events_raw
  WHERE source = 'jenkins'
    AND event_type = 'build_success'
    AND (
      payload::json->>'name' ILIKE '%deploy%'
      OR payload::json->>'name' ILIKE '%production%'
    )
),
gitlab_deployments AS (
  -- GitLab pipeline_success and deployment_success events
  SELECT
    received_at,
    'gitlab' AS platform,
    payload::json->'project'->>'name' AS workflow_name
  FROM public.events_raw
  WHERE source = 'gitlab'
    AND (
      event_type IN ('pipeline_success', 'deployment_success')
      OR (event_type = 'pipeline_running' AND payload::json->'object_attributes'->>'status' = 'success')
    )
    AND (
      payload::json->'project'->>'name' ILIKE '%deploy%'
      OR payload::json->'object_attributes'->>'ref' IN ('main', 'master', 'production')
    )
),
all_deployments AS (
  SELECT * FROM github_deployments
  UNION ALL
  SELECT * FROM circleci_deployments
  UNION ALL
  SELECT * FROM jenkins_deployments
  UNION ALL
  SELECT * FROM gitlab_deployments
)
SELECT
  date_trunc('day', received_at) AS day,
  COUNT(*) AS total_deployments,
  COUNT(*) FILTER (WHERE platform = 'github') AS github_deployments,
  COUNT(*) FILTER (WHERE platform = 'circleci') AS circleci_deployments,
  COUNT(*) FILTER (WHERE platform = 'jenkins') AS jenkins_deployments,
  COUNT(*) FILTER (WHERE platform = 'gitlab') AS gitlab_deployments
FROM all_deployments
GROUP BY 1
ORDER BY 1 DESC

