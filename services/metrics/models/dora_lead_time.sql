-- Lead time for changes: time from PR merge to successful deployment
-- Measures the elapsed time between when code is merged and when it's deployed to production
with pr_merges as (
  select
    payload::json->'pull_request'->>' number' as pr_number,
    payload::json->'repository'->>'full_name' as repo,
    received_at as merged_at
  from public.events_raw
  where source = 'github'
    and event_type = 'pull_request'
    and payload::json->>'action' = 'closed'
    and (payload::json->'pull_request'->>'merged')::boolean = true
),
deployments as (
  select
    payload::json->'repository'->>'full_name' as repo,
    received_at as deployed_at
  from public.events_raw
  where source = 'github'
    and event_type = 'workflow_run'
    and payload::json->>'action' = 'completed'
    and payload::json->'workflow_run'->>'conclusion' = 'success'
    and (
      payload::json->'workflow_run'->>'name' ilike '%deploy%'
      or payload::json->'workflow_run'->>'name' ilike '%production%'
    )
)
select
  pr.repo,
  pr.pr_number,
  pr.merged_at,
  min(d.deployed_at) as first_deploy_after_merge,
  extract(epoch from (min(d.deployed_at) - pr.merged_at)) / 3600.0 as lead_time_hours
from pr_merges pr
join deployments d
  on d.repo = pr.repo
  and d.deployed_at > pr.merged_at
group by pr.repo, pr.pr_number, pr.merged_at
order by pr.merged_at desc
