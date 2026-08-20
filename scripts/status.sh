#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
docker compose ps
printf '\n--- SAÚDE ---\n'
URL="$(awk -F= '$1=="PUBLIC_BASE_URL" {sub(/^[^=]*=/,""); gsub(/^\"|\"$/ ,""); print; exit}' .env 2>/dev/null || true)"
URL="${URL:-http://localhost:8080}"
if command -v curl >/dev/null 2>&1; then curl -fsS "${URL%/}/api/v1/health/ready" && printf '\n'; fi
