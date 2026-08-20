# Operação

## Estado da stack

```bash
./scripts/status.sh
```

Ou diretamente:

```bash
docker compose ps
```

## Logs

```bash
./scripts/logs.sh
```

Consultas específicas:

```bash
docker compose logs -f --tail=200
docker compose logs -f api worker beat
docker compose logs migrate
```

## Reinício seguro

```bash
docker compose restart api worker beat web
```

## Atualização padrão

```bash
./scripts/update.sh
```

O script respeita `INSTALL_SOURCE` no `.env`:

- `ghcr`: baixa as imagens publicadas e inicia sem build;
- `local`: atualiza o código e reconstrói as imagens;
- se o pull do GHCR falhar, o modo `ghcr` usa build local como contingência.

## Atualização por imagens GHCR

A tag das imagens não usa o prefixo `v`:

```bash
IMAGE_TAG=0.2.1 docker compose -f compose.yaml -f compose.ghcr.yaml pull
IMAGE_TAG=0.2.1 docker compose -f compose.yaml -f compose.ghcr.yaml up -d --no-build --remove-orphans
```

Com a stack autônoma para Dockge/Portainer:

```bash
IMAGE_TAG=0.2.1 docker compose -f compose.dockge.yaml pull
IMAGE_TAG=0.2.1 docker compose -f compose.dockge.yaml up -d --no-build --remove-orphans
```

Imagens:

```text
ghcr.io/wkarts/argws-git-monitor-api:0.2.1
ghcr.io/wkarts/argws-git-monitor-web:0.2.1
```

Se os pacotes estiverem privados, autentique antes do pull:

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u wkarts --password-stdin
```

## Build local

```bash
docker compose -f compose.yaml up -d --build --remove-orphans
```

Para definir o modo local como padrão:

```dotenv
INSTALL_SOURCE=local
IMAGE_TAG=local
```

## Backup

```bash
./scripts/backup.sh
```

O arquivo `.dump` é criado em `backups/` com SHA-256. Copie o backup para armazenamento externo seguro.

## Restauração

```bash
./scripts/restore.sh backups/argws-git-monitor_AAAAMMDD_HHMMSS.dump
```

A restauração interrompe temporariamente API, worker, beat e web, preservando os containers de dados.

## Remoção sem perder dados

```bash
docker compose down
```

## Remoção completa, incluindo dados

```bash
docker compose down -v
```

O último comando elimina PostgreSQL, Redis e RabbitMQ de forma irreversível.

## Endpoints de diagnóstico

- `/api/v1/health/live`: processo da API;
- `/api/v1/health/ready`: PostgreSQL e Redis;
- `/api/v1/docs`: Swagger/OpenAPI;
- `/metrics`: Prometheus, restrito à rede privada pelo Nginx.
