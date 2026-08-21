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

if [[ ! -f .env ]]; then
  bash generate-env.sh
fi

compose=(docker compose --env-file .env -f compose.yaml)
"${compose[@]}" config -q
"${compose[@]}" pull
"${compose[@]}" up -d --no-build --force-recreate --remove-orphans
"${compose[@]}" ps
printf 'Imagens: GHCR :latest\n'
printf 'Versão: lida do próprio aplicativo\n'
printf 'Dados persistentes em:\n- %s/data-postgres\n- %s/data-redis\n- %s/data-rabbitmq\n- %s/data-logs\n' "$ROOT" "$ROOT" "$ROOT" "$ROOT"
