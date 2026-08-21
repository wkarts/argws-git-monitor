#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_PATH="$ROOT/.env"
PORT=8080
BIND_ADDRESS="0.0.0.0"
PUBLIC_URL=""
FORCE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)
      shift
      PORT="${1:?Informe a porta após --port}"
      ;;
    --bind)
      shift
      BIND_ADDRESS="${1:?Informe o endereço após --bind}"
      ;;
    --url)
      shift
      PUBLIC_URL="${1:?Informe a URL após --url}"
      ;;
    --force)
      FORCE=true
      ;;
    *)
      echo "Uso: bash generate-env.sh [--port 8080] [--bind 0.0.0.0] [--url URL] [--force]" >&2
      exit 2
      ;;
  esac
  shift
done

[[ "$PORT" =~ ^[0-9]+$ ]] || { echo "Porta inválida: $PORT" >&2; exit 2; }
mkdir -p "$ROOT/data-postgres" "$ROOT/data-redis" "$ROOT/data-rabbitmq"

if [[ -f "$ENV_PATH" && "$FORCE" != true ]]; then
  echo "$ENV_PATH já existe. Use --force para substituir."
  echo "Diretórios persistentes confirmados em $ROOT/data-*"
  exit 0
fi

random_urlsafe() {
  head -c "$1" /dev/urandom | base64 | tr '+/' '-_' | tr -d '=\n\r'
}

fernet_key() {
  head -c 32 /dev/urandom | base64 | tr '+/' '-_' | tr -d '\n\r'
}

if [[ -z "$PUBLIC_URL" ]]; then
  PUBLIC_URL="http://localhost:${PORT}"
fi
PUBLIC_URL="${PUBLIC_URL%/}"

ADMIN_PASSWORD="$(random_urlsafe 18)"
POSTGRES_PASSWORD="$(random_urlsafe 24)"
RABBIT_PASSWORD="$(random_urlsafe 24)"
APP_SECRET="$(random_urlsafe 64)"
ENCRYPTION_KEY="$(fernet_key)"
WEBHOOK_SECRET="$(random_urlsafe 48)"

cat > "$ENV_PATH" <<EOF
COMPOSE_PROJECT_NAME=argws-git-monitor
APP_NAME="ARGWS Git Monitor"
APP_VERSION=0.2.3
APP_ENV=production
APP_DEBUG=false
LOG_LEVEL=INFO
APP_HTTP_PORT=${PORT}
APP_BIND_ADDRESS=${BIND_ADDRESS}
PUBLIC_BASE_URL=${PUBLIC_URL}
CORS_ORIGINS=${PUBLIC_URL}
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
IMAGE_TAG=0.2.3
API_IMAGE=ghcr.io/wkarts/argws-git-monitor-api
WEB_IMAGE=ghcr.io/wkarts/argws-git-monitor-web
EOF

chmod 600 "$ENV_PATH" 2>/dev/null || true

cat <<EOF
Arquivo criado: $ENV_PATH
Aplicação: $PUBLIC_URL
Usuário inicial: admin@argws.com.br
Senha inicial: $ADMIN_PASSWORD
Dados persistentes:
- $ROOT/data-postgres
- $ROOT/data-redis
- $ROOT/data-rabbitmq
EOF
