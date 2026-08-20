#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
REPOSITORY="${1:-wkarts/argws-git-monitor}"
VISIBILITY="${2:-private}"
command -v git >/dev/null 2>&1 || { echo "Git não encontrado." >&2; exit 1; }
command -v gh >/dev/null 2>&1 || { echo "GitHub CLI (gh) não encontrado." >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "Execute 'gh auth login' antes desta publicação." >&2; exit 1; }

if [[ ! -d .git ]]; then git init -b main; fi
git check-ignore -q .env || { echo ".env não está protegido pelo .gitignore." >&2; exit 1; }
git check-ignore -q CREDENCIAIS_INICIAIS.txt || { echo "Credenciais não estão protegidas pelo .gitignore." >&2; exit 1; }
git config user.name >/dev/null 2>&1 || git config user.name "wkarts"
git config user.email >/dev/null 2>&1 || git config user.email "wkarts@users.noreply.github.com"

git add .
if ! git diff --cached --quiet; then
  git commit -m "feat: entrega inicial completa do ARGWS Git Monitor"
fi

if gh repo view "$REPOSITORY" >/dev/null 2>&1; then
  EXPECTED_REMOTE="https://github.com/${REPOSITORY}.git"
  if git remote get-url origin >/dev/null 2>&1; then
    git remote set-url origin "$EXPECTED_REMOTE"
  else
    git remote add origin "$EXPECTED_REMOTE"
  fi
  git push -u origin main
else
  gh repo create "$REPOSITORY" "--${VISIBILITY}" --source=. --remote=origin --push --description "PWA Docker para monitoramento operacional de repositórios GitHub"
fi
printf 'Publicado em https://github.com/%s\n' "$REPOSITORY"
