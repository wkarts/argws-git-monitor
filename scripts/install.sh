#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail() { printf '\n[ERRO] %s\n' "$1" >&2; exit 1; }
info() { printf '\n[ARGWS Git Monitor] %s\n' "$1"; }
warning() { printf '\n[AVISO] %s\n' "$1" >&2; }

env_value() {
  local key="$1"
  awk -F= -v key="$key" '
    $1 == key {
      sub(/^[^=]*=/, "")
      gsub(/^"|"$/, "")
      print
      exit
    }
  ' .env
}

command -v docker >/dev/null 2>&1 || fail "Docker não encontrado. Instale Docker Engine/Desktop com o plugin Compose."
docker compose version >/dev/null 2>&1 || fail "O plugin 'docker compose' não está disponível."
docker info >/dev/null 2>&1 || fail "O serviço Docker não está em execução ou o usuário não possui permissão."

mkdir -p data-postgres data-redis data-rabbitmq

if [[ ! -f .env ]]; then
  scripts/generate-env.sh
fi

INSTALL_SOURCE="$(env_value INSTALL_SOURCE)"
INSTALL_SOURCE="${INSTALL_SOURCE:-ghcr}"

compose=(docker compose -f compose.yaml)
if [[ "$INSTALL_SOURCE" == "ghcr" ]]; then
  compose+=(-f compose.ghcr.yaml)
fi

info "Validando a configuração Docker"
"${compose[@]}" config -q

if [[ "$INSTALL_SOURCE" == "local" ]]; then
  info "Construindo as imagens localmente"
  "${compose[@]}" up -d --build --remove-orphans
else
  info "Baixando as imagens oficiais do GHCR"
  if "${compose[@]}" pull; then
    info "Iniciando a stack com as imagens publicadas"
    "${compose[@]}" up -d --no-build --remove-orphans
  else
    warning "Não foi possível baixar uma ou mais imagens do GHCR. Será realizado o build local como contingência."
    compose=(docker compose -f compose.yaml)
    "${compose[@]}" up -d --build --remove-orphans
  fi
fi

PUBLIC_URL="$(env_value PUBLIC_BASE_URL)"
PUBLIC_URL="${PUBLIC_URL:-http://localhost:8080}"
HTTP_PORT="$(env_value APP_HTTP_PORT)"
HTTP_PORT="${HTTP_PORT:-8080}"
HEALTH_URL="http://127.0.0.1:${HTTP_PORT}/api/v1/health/ready"

health_ok=0
for _ in $(seq 1 90); do
  if command -v curl >/dev/null 2>&1; then
    curl -fsS --max-time 3 "$HEALTH_URL" >/dev/null 2>&1 && health_ok=1 && break
  elif command -v wget >/dev/null 2>&1; then
    wget -q -T 3 -O /dev/null "$HEALTH_URL" >/dev/null 2>&1 && health_ok=1 && break
  else
    "${compose[@]}" ps --status running api web | grep -q 'api\|web' && health_ok=1 && break
  fi
  sleep 2
done

if [[ "$health_ok" -ne 1 ]]; then
  "${compose[@]}" ps
  "${compose[@]}" logs --tail=120 migrate api worker web >&2 || true
  fail "A verificação de saúde não foi concluída. Consulte os logs exibidos acima."
fi

info "Instalação concluída"
"${compose[@]}" ps
printf '\nAplicação: %s\n' "$PUBLIC_URL"
printf 'Credenciais: %s/CREDENCIAIS_INICIAIS.txt\n' "$ROOT"
printf 'Persistência: %s/data-postgres, %s/data-redis e %s/data-rabbitmq\n\n' "$ROOT" "$ROOT" "$ROOT"
