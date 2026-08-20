#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

URL="${1:-}"
[[ "$URL" =~ ^https?://[^/]+$ ]] || {
  echo "Uso: scripts/configure-domain.sh https://git.seu-dominio.com.br" >&2
  exit 2
}

python3 - "$URL" <<'PY'
from pathlib import Path
import sys

url = sys.argv[1].rstrip("/")
path = Path(".env")
lines = path.read_text(encoding="utf-8").splitlines()
changes = {"PUBLIC_BASE_URL": url, "CORS_ORIGINS": url}
seen = set()
output = []

for line in lines:
    if "=" in line and not line.lstrip().startswith("#"):
        key = line.split("=", 1)[0]
        if key in changes:
            output.append(f"{key}={changes[key]}")
            seen.add(key)
            continue
    output.append(line)

for key, value in changes.items():
    if key not in seen:
        output.append(f"{key}={value}")

path.write_text("\n".join(output) + "\n", encoding="utf-8")
PY

INSTALL_SOURCE="$(
  awk -F= '
    $1 == "INSTALL_SOURCE" {
      sub(/^[^=]*=/, "")
      gsub(/^"|"$/, "")
      print
      exit
    }
  ' .env
)"
INSTALL_SOURCE="${INSTALL_SOURCE:-ghcr}"

compose=(docker compose -f compose.yaml)
if [[ "$INSTALL_SOURCE" == "ghcr" ]]; then
  compose+=(-f compose.ghcr.yaml)
fi

"${compose[@]}" up -d --force-recreate api worker beat web
printf 'Domínio configurado: %s\n' "$URL"
