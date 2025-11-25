-- Deployment frequency: daily count of successful deployment workflow runs
-- Tracks GitHub Actions workflows that contain "deploy" or "production" in their name
-- and completed successfully
select
  date_trunc('day', received_at) as day,
  count(*) as deployments
from public.events_raw
where source = 'github'
  and event_type = 'workflow_run'
  and payload::json->>'action' = 'completed'
  and payload::json->'workflow_run'->>'conclusion' = 'success'
  and (
    payload::json->'workflow_run'->>'name' ilike '%deploy%'
    or payload::json->'workflow_run'->>'name' ilike '%production%'
  )
group by 1
order by 1 desc

