# API

A documentação navegável é publicada em `/api/v1/docs`.

Grupos principais:

- `/auth`: login, refresh, logout, conta e senha.
- `/dashboard`: visão consolidada.
- `/github`: conexões, importação, sincronização e webhooks remotos.
- `/repositories`: listagem, detalhes, monitoramento e operações de Actions.
- `/operations`: consultas agregadas e paginadas de Actions, Pull Requests, Releases e Issues.
- `/notifications`: consulta e leitura.
- `/webhooks/github`: recepção de eventos GitHub.
- `/health/live` e `/health/ready`: diagnóstico.

Todas as rotas operacionais exigem `Authorization: Bearer <access_token>`.


## Consultas operacionais agregadas

- `GET /operations/actions?q=&state=&page=&page_size=`
- `GET /operations/pull-requests?q=&draft=&page=&page_size=`
- `GET /operations/releases?q=&prerelease=&page=&page_size=`
- `GET /operations/issues?q=&page=&page_size=`

Todas as consultas são limitadas às conexões GitHub pertencentes ao usuário autenticado.
