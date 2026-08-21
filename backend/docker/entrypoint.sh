#!/bin/sh
set -eu

COMMAND="${1:-api}"

log_to_file() {
  message="$1"
  if [ -n "${LOG_FILE:-}" ]; then
    mkdir -p "$(dirname "$LOG_FILE")"
    printf '%s %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$message" >> "$LOG_FILE"
  fi
}

run_with_log() {
  if [ -z "${LOG_FILE:-}" ]; then
    "$@"
    return
  fi

  mkdir -p "$(dirname "$LOG_FILE")"
  if "$@" >> "$LOG_FILE" 2>&1; then
    return 0
  fi

  rc=$?
  echo "[ARGWS Git Monitor] Comando falhou; últimas linhas do log:" >&2
  tail -n 200 "$LOG_FILE" >&2 || true
  return "$rc"
}

case "$COMMAND" in
  migrate)
    echo "[ARGWS Git Monitor] Aplicando migrations..."
    log_to_file "Iniciando Alembic upgrade head"
    run_with_log alembic upgrade head
    log_to_file "Alembic concluído; executando bootstrap"
    echo "[ARGWS Git Monitor] Criando/atualizando dados iniciais..."
    run_with_log python -m app.bootstrap
    log_to_file "Migration/bootstrap concluídos"
    ;;
  api)
    log_to_file "Inicializando API"
    exec uvicorn app.main:app \
      --host 0.0.0.0 \
      --port "${API_PORT:-8000}" \
      --workers "${API_WORKERS:-2}" \
      --proxy-headers \
      --forwarded-allow-ips="*"
    ;;
  worker)
    log_to_file "Inicializando Celery worker"
    exec celery -A app.tasks.celery_app.celery_app worker \
      --loglevel="${LOG_LEVEL:-INFO}" \
      --concurrency="${CELERY_CONCURRENCY:-2}" \
      --max-tasks-per-child="${CELERY_MAX_TASKS_PER_CHILD:-100}"
    ;;
  beat)
    log_to_file "Inicializando Celery beat"
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
