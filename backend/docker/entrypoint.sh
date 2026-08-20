#!/bin/sh
set -eu

COMMAND="${1:-api}"

case "$COMMAND" in
  migrate)
    echo "[ARGWS Git Monitor] Aplicando migrations..."
    alembic upgrade head
    echo "[ARGWS Git Monitor] Criando dados iniciais..."
    python -m app.bootstrap
    ;;
  api)
    exec uvicorn app.main:app \
      --host 0.0.0.0 \
      --port "${API_PORT:-8000}" \
      --workers "${API_WORKERS:-2}" \
      --proxy-headers \
      --forwarded-allow-ips="*"
    ;;
  worker)
    exec celery -A app.tasks.celery_app.celery_app worker \
      --loglevel="${LOG_LEVEL:-INFO}" \
      --concurrency="${CELERY_CONCURRENCY:-2}" \
      --max-tasks-per-child="${CELERY_MAX_TASKS_PER_CHILD:-100}"
    ;;
  beat)
    exec celery -A app.tasks.celery_app.celery_app beat \
      --loglevel="${LOG_LEVEL:-INFO}" \
      --schedule=/tmp/celerybeat-schedule
    ;;
  test)
    exec pytest
    ;;
  *)
    exec "$@"
    ;;
esac
