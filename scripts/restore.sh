#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
FILE="${1:-}"
[[ -n "$FILE" && -f "$FILE" ]] || { echo "Uso: scripts/restore.sh backups/arquivo.dump" >&2; exit 2; }
set -a; source .env; set +a
if [[ -f "${FILE}.sha256" ]]; then sha256sum -c "${FILE}.sha256"; fi

restart_application() {
  docker compose up -d api worker beat web >/dev/null 2>&1 || true
}
trap restart_application EXIT

docker compose stop web api worker beat
docker compose exec -T postgres pg_restore \
  --clean --if-exists --no-owner \
  -U "${POSTGRES_USER:-gitmonitor}" \
  -d "${POSTGRES_DB:-gitmonitor}" < "$FILE"

docker compose up -d api worker beat web
trap - EXIT
docker compose ps
