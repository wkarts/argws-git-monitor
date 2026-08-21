#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
mkdir -p data-postgres data-redis data-rabbitmq

command -v docker >/dev/null 2>&1 || {
  echo "Docker não encontrado." >&2
  exit 1
}
docker compose version >/dev/null 2>&1 || {
  echo "Docker Compose v2 não encontrado." >&2
  exit 1
}

[[ -f .env ]] || {
  echo "Gere o ambiente primeiro: bash generate-env.sh --url https://git.seu-dominio.com.br" >&2
  exit 1
}

docker compose --env-file .env -f compose.yaml config -q
docker compose --env-file .env -f compose.yaml pull
docker compose --env-file .env -f compose.yaml up -d --no-build --remove-orphans

PORT="$(awk -F= '$1 == "APP_HTTP_PORT" {print $2; exit}' .env)"
PORT="${PORT:-8080}"

for _ in $(seq 1 90); do
  if curl -fsS --max-time 3 "http://127.0.0.1:${PORT}/api/v1/health/ready" >/dev/null 2>&1; then
    docker compose --env-file .env -f compose.yaml ps
    echo "Stack pronta em http://127.0.0.1:${PORT} para o reverse proxy do CloudPanel."
    echo "Dados em $ROOT/data-postgres, $ROOT/data-redis e $ROOT/data-rabbitmq"
    exit 0
  fi
  sleep 2
done

docker compose --env-file .env -f compose.yaml ps
docker compose --env-file .env -f compose.yaml logs --tail=150 migrate api web >&2 || true
echo "A stack não ficou pronta dentro do tempo esperado." >&2
exit 1
