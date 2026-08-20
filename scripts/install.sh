#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail() { printf '\n[ERRO] %s\n' "$1" >&2; exit 1; }
info() { printf '\n[ARGWS Git Monitor] %s\n' "$1"; }

command -v docker >/dev/null 2>&1 || fail "Docker não encontrado. Instale Docker Engine/Desktop com o plugin Compose."
docker compose version >/dev/null 2>&1 || fail "O plugin 'docker compose' não está disponível."
docker info >/dev/null 2>&1 || fail "O serviço Docker não está em execução ou o usuário não possui permissão."

if [[ ! -f .env ]]; then
  scripts/generate-env.sh
fi

info "Validando a configuração Docker"
docker compose config -q

info "Construindo e iniciando todos os serviços"
docker compose up -d --build --remove-orphans

PUBLIC_URL="$(awk -F= '$1=="PUBLIC_BASE_URL" {sub(/^[^=]*=/,""); gsub(/^\"|\"$/ ,""); print; exit}' .env)"
PUBLIC_URL="${PUBLIC_URL:-http://localhost:8080}"
HEALTH_URL="${PUBLIC_URL%/}/api/v1/health/ready"

health_ok=0
for _ in $(seq 1 90); do
  if command -v curl >/dev/null 2>&1; then
    curl -fsS --max-time 3 "$HEALTH_URL" >/dev/null 2>&1 && health_ok=1 && break
  elif command -v wget >/dev/null 2>&1; then
    wget -q -T 3 -O /dev/null "$HEALTH_URL" >/dev/null 2>&1 && health_ok=1 && break
  else
    docker compose ps --status running api web | grep -q 'api\|web' && health_ok=1 && break
  fi
  sleep 2
done

if [[ "$health_ok" -ne 1 ]]; then
  docker compose ps
  docker compose logs --tail=120 migrate api worker web >&2 || true
  fail "A verificação de saúde não foi concluída. Consulte os logs exibidos acima."
fi

info "Instalação concluída"
docker compose ps
printf '\nAplicação: %s\n' "$PUBLIC_URL"
printf 'Credenciais: %s/CREDENCIAIS_INICIAIS.txt\n\n' "$ROOT"
