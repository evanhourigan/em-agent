-- Aging WIP (placeholder): current open items and their age in days
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
)
select o.delivery_id,
       o.opened_at,
       coalesce(c.closed_at, now()) as end_at,
       extract(epoch from (coalesce(c.closed_at, now()) - o.opened_at)) / (3600.0 * 24.0) as age_days
from opened o
left join closed c using (delivery_id)
where c.closed_at is null
order by age_days desc