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
kubernetes_deployments AS (
  -- Kubernetes deployment events
  SELECT
    received_at,
    'kubernetes' AS platform,
    payload::json->'object'->'metadata'->>'name' AS workflow_name
  FROM public.events_raw
  WHERE source = 'kubernetes'
    AND (
      event_type LIKE '%deployment%'
      OR event_type LIKE 'update_deployment'
    )
),
argocd_deployments AS (
  -- ArgoCD sync successful events
  SELECT
    received_at,
    'argocd' AS platform,
    payload::json->'app'->'metadata'->>'name' AS workflow_name
  FROM public.events_raw
  WHERE source = 'argocd'
    AND event_type = 'sync_synced'
),
ecs_deployments AS (
  -- AWS ECS task running events
  SELECT
    received_at,
    'ecs' AS platform,
    payload::json->'detail'->>'group' AS workflow_name
  FROM public.events_raw
  WHERE source = 'ecs'
    AND event_type IN ('task_running', 'deployment')
),
heroku_deployments AS (
  -- Heroku release create events
  SELECT
    received_at,
    'heroku' AS platform,
    payload::json->'data'->'app'->>'name' AS workflow_name
  FROM public.events_raw
  WHERE source = 'heroku'
    AND event_type IN ('release_create', 'build_succeeded')
),
all_deployments AS (
  SELECT * FROM github_deployments
  UNION ALL
  SELECT * FROM circleci_deployments
  UNION ALL
  SELECT * FROM jenkins_deployments
  UNION ALL
  SELECT * FROM gitlab_deployments
  UNION ALL
  SELECT * FROM kubernetes_deployments
  UNION ALL
  SELECT * FROM argocd_deployments
  UNION ALL
  SELECT * FROM ecs_deployments
  UNION ALL
  SELECT * FROM heroku_deployments
)
SELECT
  date_trunc('day', received_at) AS day,
  COUNT(*) AS total_deployments,
  COUNT(*) FILTER (WHERE platform = 'github') AS github_deployments,
  COUNT(*) FILTER (WHERE platform = 'circleci') AS circleci_deployments,
  COUNT(*) FILTER (WHERE platform = 'jenkins') AS jenkins_deployments,
  COUNT(*) FILTER (WHERE platform = 'gitlab') AS gitlab_deployments,
  COUNT(*) FILTER (WHERE platform = 'kubernetes') AS kubernetes_deployments,
  COUNT(*) FILTER (WHERE platform = 'argocd') AS argocd_deployments,
  COUNT(*) FILTER (WHERE platform = 'ecs') AS ecs_deployments,
  COUNT(*) FILTER (WHERE platform = 'heroku') AS heroku_deployments
FROM all_deployments
GROUP BY 1
ORDER BY 1 DESC

