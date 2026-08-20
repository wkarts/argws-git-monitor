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

INSTALL_SOURCE="$(env_value INSTALL_SOURCE)"
INSTALL_SOURCE="${INSTALL_SOURCE:-ghcr}"

compose=(docker compose -f compose.yaml)
if [[ "$INSTALL_SOURCE" == "ghcr" ]]; then
  compose+=(-f compose.ghcr.yaml)
fi

"${compose[@]}" config -q

if [[ "$INSTALL_SOURCE" == "local" ]]; then
  info "Reconstruindo as imagens locais"
  "${compose[@]}" up -d --build --remove-orphans
else
  info "Atualizando imagens pelo GHCR"
  if "${compose[@]}" pull; then
    "${compose[@]}" up -d --no-build --remove-orphans
  else
    warning "Falha no pull do GHCR. Será realizado build local como contingência."
    compose=(docker compose -f compose.yaml)
    "${compose[@]}" up -d --build --remove-orphans
  fi
fi

docker image prune -f >/dev/null 2>&1 || true
"${compose[@]}" ps
