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
