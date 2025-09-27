-- Lead time for changes (placeholder): difference between first commit (push) and deployment event per delivery id
with commits as (
  select delivery_id, min(received_at) as first_commit_at
  from public.events_raw
  where source = 'github' and event_type in ('push', 'pull_request')
  group by delivery_id
),
deploys as (
  select delivery_id, min(received_at) as first_deploy_at
  from public.events_raw
  where source = 'github' and event_type in ('deployment_status', 'release')
  group by delivery_id
)
select
  c.delivery_id,
  c.first_commit_at,
  d.first_deploy_at,
  extract(epoch from (d.first_deploy_at - c.first_commit_at)) / 3600.0 as lead_time_hours
from commits c
join deploys d on d.delivery_id = c.delivery_id
where d.first_deploy_at > c.first_commit_at
