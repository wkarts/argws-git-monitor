#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FORCE=false
PORT=8080
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) FORCE=true ;;
    --port) shift; PORT="${1:?Informe a porta após --port}" ;;
    *) echo "Uso: $0 [--force] [--port 8080]" >&2; exit 2 ;;
  esac
  shift
done
[[ "$PORT" =~ ^[0-9]+$ ]] || { echo "Porta inválida: $PORT" >&2; exit 2; }
ENV_PATH="$ROOT/.env"
CREDENTIALS_PATH="$ROOT/CREDENCIAIS_INICIAIS.txt"
if [[ -f "$ENV_PATH" && "$FORCE" != true ]]; then
  echo "$ENV_PATH já existe; nenhuma alteração realizada."
  exit 0
fi
command -v base64 >/dev/null 2>&1 || { echo "Comando base64 não encontrado." >&2; exit 1; }

random_urlsafe() {
  local bytes="$1"
  head -c "$bytes" /dev/urandom | base64 | tr '+/' '-_' | tr -d '=\n\r'
}
fernet_key() {
  head -c 32 /dev/urandom | base64 | tr '+/' '-_' | tr -d '\n\r'
}

ADMIN_PASSWORD="$(random_urlsafe 18)"
POSTGRES_PASSWORD="$(random_urlsafe 24)"
RABBIT_PASSWORD="$(random_urlsafe 24)"
APP_SECRET="$(random_urlsafe 64)"
ENCRYPTION_KEY="$(fernet_key)"
WEBHOOK_SECRET="$(random_urlsafe 48)"
URL="http://localhost:${PORT}"

cat > "$ENV_PATH" <<EOF
COMPOSE_PROJECT_NAME=argws-git-monitor
APP_NAME="ARGWS Git Monitor"
APP_VERSION=0.2.0
APP_ENV=production
APP_DEBUG=false
LOG_LEVEL=INFO
APP_HTTP_PORT=${PORT}
APP_BIND_ADDRESS=0.0.0.0
PUBLIC_BASE_URL=${URL}
CORS_ORIGINS=${URL},http://127.0.0.1:${PORT}
APP_SECRET_KEY=${APP_SECRET}
ENCRYPTION_KEY=${ENCRYPTION_KEY}
INITIAL_ADMIN_NAME="Administrador ARGWS"
INITIAL_ADMIN_EMAIL=admin@argws.com.br
INITIAL_ADMIN_PASSWORD=${ADMIN_PASSWORD}
INITIAL_ADMIN_MUST_CHANGE_PASSWORD=true
POSTGRES_DB=gitmonitor
POSTGRES_USER=gitmonitor
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
RABBITMQ_DEFAULT_USER=gitmonitor
RABBITMQ_DEFAULT_PASS=${RABBIT_PASSWORD}
RABBITMQ_MANAGEMENT_PORT=15672
GITHUB_API_URL=https://api.github.com
GITHUB_WEBHOOK_SECRET=${WEBHOOK_SECRET}
GITHUB_REPOSITORY_LIMIT=300
GITHUB_REQUEST_TIMEOUT_SECONDS=30
GITHUB_CONCURRENCY=5
SYNC_INTERVAL_SECONDS=600
DEMO_DATA_ENABLED=true
NOTIFICATION_RETENTION_DAYS=90
API_WORKERS=2
CELERY_CONCURRENCY=2
CELERY_MAX_TASKS_PER_CHILD=100
IMAGE_TAG=local
EOF

cat > "$CREDENTIALS_PATH" <<EOF
ARGWS GIT MONITOR - CREDENCIAIS INICIAIS
============================================================

Aplicação: ${URL}
E-mail:    admin@argws.com.br
Senha:     ${ADMIN_PASSWORD}

RabbitMQ (somente localhost): http://localhost:15672
Usuário:   gitmonitor
Senha:     ${RABBIT_PASSWORD}

A aplicação exige a troca da senha administrativa no primeiro acesso.
Este arquivo e o .env estão ignorados pelo Git.
EOF
chmod 600 "$ENV_PATH" "$CREDENTIALS_PATH" 2>/dev/null || true
printf 'Segredos gerados em %s\nCredenciais gravadas em %s\n' "$ENV_PATH" "$CREDENTIALS_PATH"
