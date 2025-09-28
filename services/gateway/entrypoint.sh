#!/bin/sh
set -euo pipefail

# Run DB migrations before starting the API
alembic -c /app/alembic.ini upgrade head

# Access log toggle (default off). Set UVICORN_ACCESS_LOG=true to enable
ACCESS_ARGS="--no-access-log"
if [ "${UVICORN_ACCESS_LOG:-false}" = "true" ]; then
  ACCESS_ARGS=""
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 $ACCESS_ARGS


