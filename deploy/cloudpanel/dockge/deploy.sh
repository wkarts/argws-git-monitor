#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
mkdir -p \
  data-postgres data-redis data-rabbitmq \
  data-logs/api data-logs/worker data-logs/beat data-logs/migrate \
  data-logs/web data-logs/postgres data-logs/redis data-logs/rabbitmq

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

compose=(docker compose --env-file .env -f compose.yaml)
"${compose[@]}" config -q
"${compose[@]}" pull
"${compose[@]}" up -d --no-build --force-recreate --remove-orphans

PORT="$(awk -F= '$1 == "APP_HTTP_PORT" {print $2; exit}' .env)"
PORT="${PORT:-8080}"

for _ in $(seq 1 90); do
  if curl -fsS --max-time 3 "http://127.0.0.1:${PORT}/api/v1/health/ready" >/dev/null 2>&1; then
    "${compose[@]}" ps
    echo "Stack pronta em http://127.0.0.1:${PORT} para o reverse proxy do CloudPanel."
    echo "Imagens GHCR: :latest"
    echo "Versão: obtida do próprio aplicativo"
    echo "Dados em $ROOT/data-postgres, $ROOT/data-redis, $ROOT/data-rabbitmq e $ROOT/data-logs"
    exit 0
  fi
  sleep 2
done

"${compose[@]}" ps
"${compose[@]}" logs --tail=150 migrate api web >&2 || true
echo "A stack não ficou pronta dentro do tempo esperado." >&2
exit 1
