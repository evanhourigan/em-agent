#!/bin/sh
set -euo pipefail

ACCESS_ARGS="--no-access-log"
if [ "${UVICORN_ACCESS_LOG:-false}" = "true" ]; then
  ACCESS_ARGS=""
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 $ACCESS_ARGS


