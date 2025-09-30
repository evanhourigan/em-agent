-- Change fail rate (placeholder): fraction of deployments per day with failure state
with deploys as (
  select date_trunc('day', received_at) as day,
         count(*) filter (where payload like '%"state": "failure"%') as failures,
         count(*) filter (where payload like '%"state": "success"%') as successes,
         count(*) as total
  from public.events_raw
  where source = 'github' and event_type = 'deployment_status'
  group by 1
)
select day,
       failures,
       total,
       case when total > 0 then failures::float / total else 0 end as change_fail_rate
from deploys
order by day