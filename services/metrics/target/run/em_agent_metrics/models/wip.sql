
  create view "postgres"."public"."wip__dbt_tmp"
    
    
  as (
    -- WIP (placeholder): daily count of items in progress
-- Define opened_at from PR open; define closed_at as first success deployment (approx)
with opened as (
  select delivery_id, min(received_at) as opened_at
  from public.events_raw
  where source = 'github' and event_type = 'pull_request'
  group by delivery_id
),
closed as (
  select delivery_id, min(received_at) as closed_at
  from public.events_raw
  where source = 'github' and event_type = 'deployment_status' and payload like '%"state": "success"%'
  group by delivery_id
),
spans as (
  select o.delivery_id,
         date_trunc('day', o.opened_at) as start_day,
         date_trunc('day', coalesce(c.closed_at, now())) as end_day
  from opened o
  left join closed c using (delivery_id)
),
days as (
  select generate_series(
           (select min(start_day) from spans),
           date_trunc('day', now()),
           interval '1 day')::date as day
),
active as (
  select d.day,
         count(*) as wip
  from days d
  join spans s
    on d.day between s.start_day and s.end_day
  group by 1
)
select day, wip
from active
order by day
  );