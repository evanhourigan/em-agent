-- Deployment frequency (placeholder): daily count of deployment events
select
  date_trunc('day', received_at) as day,
  count(*) as deployments
from public.events_raw
where source = 'github' and event_type in ('deployment_status', 'release')
group by 1
order by 1