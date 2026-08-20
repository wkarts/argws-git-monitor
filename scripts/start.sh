#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

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
  "${compose[@]}" up -d --no-build --remove-orphans
else
  "${compose[@]}" up -d --remove-orphans
fi

"${compose[@]}" ps
