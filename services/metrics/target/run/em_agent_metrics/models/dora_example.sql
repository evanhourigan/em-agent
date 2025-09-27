
  create view "postgres"."public"."dora_example__dbt_tmp"
    
    
  as (
    select 'deployment_frequency' as metric, 0::int as value
union all
select 'lead_time_for_changes' as metric, 0::int as value
  );