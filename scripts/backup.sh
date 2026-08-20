#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
set -a; source .env; set +a
mkdir -p backups
STAMP="$(date +%Y%m%d_%H%M%S)"
TARGET="backups/argws-git-monitor_${STAMP}.dump"
docker compose exec -T postgres pg_dump -Fc -U "${POSTGRES_USER:-gitmonitor}" -d "${POSTGRES_DB:-gitmonitor}" > "$TARGET"
[[ -s "$TARGET" ]] || { rm -f "$TARGET"; echo "Backup vazio; operação cancelada." >&2; exit 1; }
sha256sum "$TARGET" > "${TARGET}.sha256"
printf 'Backup criado: %s\n' "$TARGET"
