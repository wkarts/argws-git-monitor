# Política de versão dos deploys

## Contrato

Os ambientes de produção e os modelos de implantação do ARGWS Git Monitor seguem uma única regra:

```text
API GHCR: ghcr.io/wkarts/argws-git-monitor-api:latest
WEB GHCR: ghcr.io/wkarts/argws-git-monitor-web:latest
```

Nenhum modelo de deploy deve exigir ou gravar um número de versão da aplicação.

Variáveis proibidas como mecanismo de versionamento do deploy:

```text
APP_VERSION
IMAGE_TAG
VITE_APP_VERSION
```

## Fonte da versão exibida

A versão é responsabilidade do próprio artefato:

- backend: metadata do pacote Python `argws-git-monitor-api`;
- frontend: `version` do `frontend/package.json`, injetado pelo Vite durante a compilação.

O arquivo `VERSION` permanece como fonte de versionamento do processo de release e deve coincidir com `backend/pyproject.toml` e `frontend/package.json`.

## Atualização

Um servidor não deve alterar o `.env` para atualizar de versão. O processo correto é:

```bash
docker compose pull
docker compose up -d --no-build --force-recreate --remove-orphans
```

O `pull` atualiza o conteúdo apontado por `latest`; o `--force-recreate` garante que os containers em execução sejam reconstruídos a partir do digest recém-baixado.

## Persistência

A política de `latest` não altera o armazenamento. Os dados continuam em bind mounts relativos:

```text
./data-postgres
./data-redis
./data-rabbitmq
```

Esses diretórios não devem ser removidos durante uma atualização.
