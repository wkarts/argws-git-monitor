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
docker info >/dev/null 2>&1 || {
  echo "Docker não está em execução ou o usuário não possui acesso." >&2
  exit 1
}

if [[ ! -f .env ]]; then
  bash generate-env.sh
fi

docker compose --env-file .env -f compose.ghcr.yaml config -q
docker compose --env-file .env -f compose.ghcr.yaml pull
docker compose --env-file .env -f compose.ghcr.yaml up -d --no-build --remove-orphans

PORT="$(awk -F= '$1 == "APP_HTTP_PORT" {print $2; exit}' .env)"
PORT="${PORT:-8080}"

for _ in $(seq 1 90); do
  if curl -fsS --max-time 3 "http://127.0.0.1:${PORT}/api/v1/health/ready" >/dev/null 2>&1; then
    docker compose --env-file .env -f compose.ghcr.yaml ps
    echo "ARGWS Git Monitor disponível em http://127.0.0.1:${PORT}"
    echo "Dados em $ROOT/data-postgres, $ROOT/data-redis e $ROOT/data-rabbitmq"
    exit 0
  fi
  sleep 2
done

docker compose --env-file .env -f compose.ghcr.yaml ps
docker compose --env-file .env -f compose.ghcr.yaml logs --tail=150 migrate api web >&2 || true
echo "A aplicação não ficou pronta dentro do tempo esperado." >&2
exit 1
