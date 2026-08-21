#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

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

if [[ -d .git ]]; then
  info "Atualizando o código-fonte"
  git pull --ff-only
fi

mkdir -p data-postgres data-redis data-rabbitmq
PROJECT_NAME="$(env_value COMPOSE_PROJECT_NAME)"
PROJECT_NAME="${PROJECT_NAME:-argws-git-monitor}"

legacy_detected=0
legacy_volumes=(
  "${PROJECT_NAME}_postgres_data"
  "${PROJECT_NAME}_redis_data"
  "${PROJECT_NAME}_rabbitmq_data"
)
targets=(data-postgres data-redis data-rabbitmq)

for index in "${!legacy_volumes[@]}"; do
  volume="${legacy_volumes[$index]}"
  target="${targets[$index]}"
  if docker volume inspect "$volume" >/dev/null 2>&1 \
    && ! find "$target" -mindepth 1 -maxdepth 1 -print -quit | grep -q .; then
    warning "Volume nomeado anterior detectado: $volume"
    legacy_detected=1
  fi
done

if [[ "$legacy_detected" -eq 1 ]]; then
  cat >&2 <<EOF

A atualização foi interrompida para evitar iniciar bancos vazios.
Migre os dados antigos antes de continuar:

  docker compose down
  bash deploy/migrate-named-volumes.sh --stack-dir "$ROOT" --project "$PROJECT_NAME"
  ./scripts/update.sh

Os volumes nomeados antigos não serão apagados pela migração.
EOF
  exit 1
fi

INSTALL_SOURCE="$(env_value INSTALL_SOURCE)"
INSTALL_SOURCE="${INSTALL_SOURCE:-ghcr}"

compose=(docker compose -f compose.yaml)
if [[ "$INSTALL_SOURCE" == "ghcr" ]]; then
  compose+=(-f compose.ghcr.yaml)
fi

"${compose[@]}" config -q

if [[ "$INSTALL_SOURCE" == "local" ]]; then
  info "Reconstruindo imagens locais :latest"
  "${compose[@]}" up -d --build --force-recreate --remove-orphans
else
  info "Atualizando imagens GHCR :latest"
  if "${compose[@]}" pull; then
    "${compose[@]}" up -d --no-build --force-recreate --remove-orphans
  else
    warning "Falha no pull do GHCR. Será realizado build local como contingência."
    compose=(docker compose -f compose.yaml)
    "${compose[@]}" up -d --build --force-recreate --remove-orphans
  fi
fi

docker image prune -f >/dev/null 2>&1 || true
"${compose[@]}" ps
info "Atualização concluída. A versão é lida do próprio aplicativo."
