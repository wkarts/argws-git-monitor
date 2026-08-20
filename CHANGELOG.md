# Changelog

## 0.2.1 — 2026-08-20

- corrige o fluxo pós-merge para gerar automaticamente a GitHub Release quando a versão declarada ainda não possui tag;
- publica imagens Docker separadas para API e Web no GHCR, com tags `latest`, `sha-*`, `0.2.1` e `0.2`;
- adiciona build multi-arquitetura para `linux/amd64` e `linux/arm64`;
- adiciona inspeção obrigatória dos manifests GHCR antes da publicação da release;
- inclui ZIP, TAR.GZ e `SHA256SUMS.txt` como artefatos permanentes da GitHub Release;
- inclui `compose.dockge.yaml` autônomo para Dockge e Portainer, sem necessidade de build local;
- torna os instaladores Windows e Linux orientados ao GHCR, com fallback automático para build local;
- corrige a documentação das tags Docker, que não utilizam o prefixo `v`;
- moderniza o CodeQL e as GitHub Actions para versões compatíveis com Node.js 24;
- encerra os Pull Requests automáticos abertos pelo Dependabot e desativa novos PRs automáticos de atualização de versão;
- preserva atualização de dependências como manutenção controlada e validada pela CI.

## 0.2.0 — 2026-08-20

- dashboard reconstruído para reproduzir o contrato visual aprovado, com métricas, saúde segmentada, atividades recentes e tabela compacta de repositórios;
- navegação desktop completa para Dashboard, Repositórios, Pull Requests, Actions, Releases, Issues, Alertas e Configurações;
- experiência mobile-first com navegação inferior, painel “Mais”, lista de projetos e alerta crítico de build;
- cabeçalho com usuário, contador de notificações e acesso ao GitHub;
- páginas operacionais agregadas para Actions, PRs, Releases e Issues;
- endpoints protegidos `/api/v1/operations/*` com escopo por usuário, filtros e paginação;
- ações reais para cancelar e reexecutar workflows preservadas na nova interface;
- nova identidade visual, componentes de métricas, donut de saúde e paginação reutilizável;
- documentação, prévias visuais e validações atualizadas.

## 0.1.0 — 2026-08-20

### Entregue

- API FastAPI com autenticação, refresh rotativo e senha Argon2.
- Integração GitHub REST para repositórios, commits, branches, Actions, PRs e releases.
- Token GitHub criptografado com Fernet.
- Sincronização assíncrona e periódica via Celery, RabbitMQ e Redis.
- Webhooks assinados e idempotentes.
- Dashboard, saúde, alertas, filtros e operação de Actions.
- PWA Vue 3/TypeScript mobile-first.
- Docker Compose completo, migrations e bootstrap idempotente.
- Scripts Windows/Linux, backup, restauração e publicação no GitHub.
- CI, release GHCR, CodeQL e Dependabot.
