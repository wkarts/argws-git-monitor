#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
URL="${1:-}"
[[ "$URL" =~ ^https?://[^/]+$ ]] || { echo "Uso: scripts/configure-domain.sh https://git.seu-dominio.com.br" >&2; exit 2; }
python3 - "$URL" <<'PY'
from pathlib import Path
import sys
url=sys.argv[1].rstrip('/')
p=Path('.env')
lines=p.read_text().splitlines()
changes={'PUBLIC_BASE_URL':url,'CORS_ORIGINS':url}
seen=set(); out=[]
for line in lines:
    if '=' in line and not line.lstrip().startswith('#'):
        key=line.split('=',1)[0]
        if key in changes:
            out.append(f'{key}={changes[key]}'); seen.add(key); continue
    out.append(line)
for key,value in changes.items():
    if key not in seen: out.append(f'{key}={value}')
p.write_text('\n'.join(out)+'\n')
PY
docker compose up -d --force-recreate api worker beat web
printf 'Domínio configurado: %s\n' "$URL"
