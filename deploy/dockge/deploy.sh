#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

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

docker compose --env-file .env -f compose.yaml config -q
docker compose --env-file .env -f compose.yaml pull
docker compose --env-file .env -f compose.yaml up -d --no-build --remove-orphans
docker compose --env-file .env -f compose.yaml ps
