# Metrics Service (dbt)

This directory contains a minimal dbt project for metrics experimentation.

## Usage

Install dbt (locally):

```bash
dbt --version || pipx install dbt-postgres
```

Run models:

```bash
cd services/metrics
DBT_PROFILES_DIR=$(pwd) dbt debug
DBT_PROFILES_DIR=$(pwd) dbt run
```

Connection defaults to local Postgres (compose db) via `profiles.yml`.

## Models

- `dora_example`: placeholder view
- `dora_lead_time`: computes lead time in hours from `events_raw` by pairing first commit (push/pr) with first deployment (deployment_status/release) per delivery id.
- `deployment_frequency`: daily deployment counts
- `change_fail_rate`: daily fraction of failed deployments
- `mttr`: time from failed deployment to restore (success)
