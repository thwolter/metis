#!/usr/bin/env bash
set -euo pipefail

# Ensure Python uses the src/ path
export PYTHONPATH=${PYTHONPATH:-/app/src}
: "${ALEMBIC_DATABASE_URL:?ALEMBIC_DATABASE_URL must be set for migrations}"

# Run database migrations (alembic env will also ensure metadata schema exists)
echo "Running Alembic migrations..."
alembic upgrade head

echo "Starting Dramatiq worker..."
# Start Dramatiq worker in background; it will import metadata.tasks and discover actors
# Tune concurrency via DRAMATIQ_PROCESSES and DRAMATIQ_THREADS envs
: "${DRAMATIQ_PROCESSES:=1}"
: "${DRAMATIQ_THREADS:=8}"

# shellcheck disable=SC2086
dramatiq -p ${DRAMATIQ_PROCESSES} -t ${DRAMATIQ_THREADS} metadata.tasks &
DRAMATIQ_PID=$!

echo "Starting Uvicorn API..."
: "${HOST:=0.0.0.0}"
: "${PORT:=8000}"
: "${UVICORN_RELOAD:=false}"

# Forward signals to children
_term() {
  echo "Caught SIGTERM, forwarding to children..."
  kill -TERM "$DRAMATIQ_PID" 2>/dev/null || true
}
trap _term TERM INT

# Build uvicorn command with optional live reload support
UVICORN_CMD=(uvicorn main:app --host "$HOST" --port "$PORT")
if [[ "${UVICORN_RELOAD}" == "true" ]]; then
  echo "Uvicorn live reload enabled"
  UVICORN_CMD+=(--reload)
  if [[ -n "${UVICORN_RELOAD_DIRS:-}" ]]; then
    IFS=':' read -ra __uvicorn_reload_dirs <<< "${UVICORN_RELOAD_DIRS}"
    for dir in "${__uvicorn_reload_dirs[@]}"; do
      if [[ -n "${dir}" ]]; then
        UVICORN_CMD+=(--reload-dir "${dir}")
      fi
    done
    unset __uvicorn_reload_dirs
  fi
fi

# Run API in foreground
"${UVICORN_CMD[@]}"
API_STATUS=$?

# When API exits, stop worker too
kill -TERM "$DRAMATIQ_PID" 2>/dev/null || true
wait "$DRAMATIQ_PID" 2>/dev/null || true

exit $API_STATUS
