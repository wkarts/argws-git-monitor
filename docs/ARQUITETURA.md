# Arquitetura

## Visão geral

```text
GitHub REST + Webhooks
          |
          v
Nginx/PWA -> FastAPI -> PostgreSQL
                 |          |
                 v          v
              RabbitMQ    auditoria/estado
                 |
                 v
               Celery <-> Redis
```

## Backend

O backend segue módulos de domínio:

- `api/routes`: contratos HTTP.
- `schemas`: validação e serialização Pydantic.
- `models`: persistência SQLAlchemy 2.
- `services`: cliente GitHub, sincronização, saúde, criptografia e alertas.
- `tasks`: workers e agendamento Celery.
- `migrations`: evolução do PostgreSQL por Alembic.

As transações de sincronização são curtas: chamadas externas são feitas fora da transação principal, e o resultado é persistido de forma consolidada.

## Frontend

Vue 3 com Composition API, TypeScript, Pinia e Vue Router. O frontend possui shell responsivo, dashboard específico para desktop e mobile, páginas agregadas de Actions/PRs/Releases/Issues e componentes visuais reutilizáveis. Ele usa um único endpoint relativo (`/api/v1`) para funcionar sem recompilação quando o domínio muda. O Nginx faz o proxy para a API dentro da rede Docker.

## Persistência

PostgreSQL é a fonte de verdade. Redis armazena resultados temporários e RabbitMQ entrega tarefas. Os três usam volumes nomeados e sobrevivem à recriação dos containers.

## Saúde

A pontuação considera:

- conclusão do último workflow;
- workflow em execução;
- erro de sincronização;
- inatividade de pushes;
- repositório arquivado/desabilitado;
- volume de PRs/issues.

Estados: `healthy`, `running`, `attention`, `failing`, `unknown`.

## Segurança de token

O navegador envia o token uma única vez por HTTPS. A API valida o token em `/user`, cifra com Fernet e armazena apenas o texto cifrado e os quatro últimos caracteres. Respostas futuras nunca contêm o token.
