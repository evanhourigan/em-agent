-- Mean time to restore (placeholder): duration from failed deployment to next success per delivery
with fails as (
  select delivery_id, min(received_at) as failed_at
  from public.events_raw
  where source = 'github' and event_type = 'deployment_status' and payload like '%"state": "failure"%'
  group by delivery_id
),
success as (
  select delivery_id, min(received_at) as restored_at
  from public.events_raw
  where source = 'github' and event_type = 'deployment_status' and payload like '%"state": "success"%'
  group by delivery_id
)
select f.delivery_id,
       f.failed_at,
       s.restored_at,
       extract(epoch from (s.restored_at - f.failed_at)) / 3600.0 as mttr_hours
from fails f
join success s on s.delivery_id = f.delivery_id and s.restored_at > f.failed_at