#!/usr/bin/env bash
set -euo pipefail

# Ensure Python uses the src/ path
export PYTHONPATH=${PYTHONPATH:-/app/src}
: "${ALEMBIC_DATABASE_URL:?ALEMBIC_DATABASE_URL must be set for migrations}"

# Run database migrations (alembic env will also ensure metadata schema exists)
echo "Running Alembic migrations..."
alembic upgrade head

echo "Starting Uvicorn API..."
: "${HOST:=0.0.0.0}"
: "${PORT:=8000}"
: "${UVICORN_RELOAD:=false}"

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

exit $API_STATUS
