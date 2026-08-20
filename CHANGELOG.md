# Changelog

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
