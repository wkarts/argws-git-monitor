# Operação

## Estado da stack

```bash
docker compose ps
./scripts/status.sh
```

## Logs

```bash
docker compose logs -f --tail=200
docker compose logs -f api worker beat
docker compose logs migrate
```

## Reinício seguro

```bash
docker compose restart api worker beat web
```

## Atualização a partir do código

```bash
./scripts/update.sh
```

## Atualização por imagens GHCR

```bash
IMAGE_TAG=v0.2.0 docker compose -f compose.yaml -f compose.ghcr.yaml pull
IMAGE_TAG=v0.2.0 docker compose -f compose.yaml -f compose.ghcr.yaml up -d --no-build
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

A restauração para temporariamente API, worker, beat e web, preservando os containers de dados.

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

- `/api/v1/health/live`: processo da API.
- `/api/v1/health/ready`: PostgreSQL e Redis.
- `/api/v1/docs`: Swagger/OpenAPI.
- `/metrics`: Prometheus, restrito à rede privada pelo Nginx.
