#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -d .git ]]; then
  git pull --ff-only
fi
docker compose config -q
docker compose up -d --build --remove-orphans
docker image prune -f >/dev/null 2>&1 || true
docker compose ps
