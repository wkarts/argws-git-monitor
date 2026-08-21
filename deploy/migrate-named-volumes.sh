#!/usr/bin/env bash
set -Eeuo pipefail

STACK_DIR="$(pwd)"
PROJECT_NAME=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --stack-dir)
      shift
      STACK_DIR="${1:?Informe o diretório após --stack-dir}"
      ;;
    --project)
      shift
      PROJECT_NAME="${1:?Informe o projeto após --project}"
      ;;
    *)
      echo "Uso: bash deploy/migrate-named-volumes.sh [--stack-dir DIRETORIO] [--project NOME]" >&2
      exit 2
      ;;
  esac
  shift
done

command -v docker >/dev/null 2>&1 || {
  echo "Docker não encontrado." >&2
  exit 1
}
docker info >/dev/null 2>&1 || {
  echo "Docker não está em execução ou o usuário não possui acesso." >&2
  exit 1
}

STACK_DIR="$(cd "$STACK_DIR" && pwd)"
ENV_FILE="$STACK_DIR/.env"

if [[ -z "$PROJECT_NAME" && -f "$ENV_FILE" ]]; then
  PROJECT_NAME="$(awk -F= '$1 == "COMPOSE_PROJECT_NAME" {print $2; exit}' "$ENV_FILE" | tr -d '"\r')"
fi
PROJECT_NAME="${PROJECT_NAME:-argws-git-monitor}"

services=(postgres redis rabbitmq)
volumes=(
  "${PROJECT_NAME}_postgres_data"
  "${PROJECT_NAME}_redis_data"
  "${PROJECT_NAME}_rabbitmq_data"
)
targets=(
  "$STACK_DIR/data-postgres"
  "$STACK_DIR/data-redis"
  "$STACK_DIR/data-rabbitmq"
)

for target in "${targets[@]}"; do
  mkdir -p "$target"
  if find "$target" -mindepth 1 -maxdepth 1 -print -quit | grep -q .; then
    echo "O destino já contém dados e não será sobrescrito: $target" >&2
    exit 1
  fi
done

found=0
for index in "${!volumes[@]}"; do
  service="${services[$index]}"
  volume="${volumes[$index]}"
  target="${targets[$index]}"

  if ! docker volume inspect "$volume" >/dev/null 2>&1; then
    echo "[AVISO] Volume anterior não encontrado: $volume"
    continue
  fi

  if [[ -n "$(docker ps -q --filter "volume=$volume")" ]]; then
    echo "Há container em execução usando $volume. Pare a stack antes da migração." >&2
    exit 1
  fi

  echo "Copiando $volume para $target..."
  docker run --rm \
    -v "$volume:/source:ro" \
    -v "$target:/target" \
    alpine:3.22 \
    sh -eu -c 'cp -a /source/. /target/'

  found=$((found + 1))
  echo "[OK] $service migrado."
done

if [[ "$found" -eq 0 ]]; then
  echo "Nenhum volume nomeado anterior foi encontrado. Nada foi alterado."
  exit 0
fi

cat <<EOF

Migração concluída sem remover os volumes antigos.

Diretório da stack: $STACK_DIR
Projeto Compose: $PROJECT_NAME

Novos diretórios:
- $STACK_DIR/data-postgres
- $STACK_DIR/data-redis
- $STACK_DIR/data-rabbitmq

Agora suba a versão 0.2.3 usando o compose relativo da pasta escolhida.
Somente remova os volumes nomeados antigos depois de validar login, dados e backups.
EOF
