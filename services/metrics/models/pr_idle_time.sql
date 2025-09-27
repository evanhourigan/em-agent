-- PR idle time (placeholder): time from PR opened to first review request or comment
with prs as (
  select delivery_id, min(received_at) as opened_at
  from public.events_raw
  where source = 'github' and event_type in ('pull_request')
  group by delivery_id
),
reviews as (
  select delivery_id, min(received_at) as first_review_at
  from public.events_raw
  where source = 'github' and event_type in ('pull_request_review', 'pull_request_review_comment')
  group by delivery_id
)
select
  p.delivery_id,
  p.opened_at,
  r.first_review_at,
  extract(epoch from (coalesce(r.first_review_at, now()) - p.opened_at)) / 3600.0 as idle_hours
from prs p
left join reviews r on r.delivery_id = p.delivery_id

