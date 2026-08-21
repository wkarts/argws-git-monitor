# Operação

## Pacotes oficiais de deploy

```text
deploy/cloudpanel/
deploy/dockge/
deploy/portainer/
deploy/docker/
```

Consulte `deploy/README.md` para escolher a modalidade correta.

## Armazenamento persistente

A versão 0.2.3 mantém os dados dentro do diretório físico de cada stack. Os arquivos Compose utilizam apenas bind mounts relativos:

```yaml
postgres:
  volumes:
    - ./data-postgres:/var/lib/postgresql/data

redis:
  volumes:
    - ./data-redis:/data

rabbitmq:
  volumes:
    - ./data-rabbitmq:/var/lib/rabbitmq
```

Estrutura esperada:

```text
pasta-da-stack/
├── compose.yaml
├── .env
├── data-postgres/
├── data-redis/
└── data-rabbitmq/
```

Não mova somente o `compose.yaml`: mova ou faça backup do diretório completo da stack.

## Estado da stack

Na instalação pela raiz:

```bash
./scripts/status.sh
```

Docker separado por GHCR:

```bash
cd deploy/docker
docker compose --env-file .env -f compose.ghcr.yaml ps
```

Dockge separado:

```bash
cd deploy/dockge
docker compose --env-file .env -f compose.yaml ps
```

## Logs

Na raiz:

```bash
./scripts/logs.sh
```

Em um pacote separado:

```bash
docker compose --env-file .env -f compose.yaml logs -f --tail=200
```

## Reinício seguro

```bash
docker compose restart api worker beat web
```

## Atualização pela raiz

```bash
./scripts/update.sh
```

O script:

- cria `./data-postgres`, `./data-redis` e `./data-rabbitmq`;
- verifica se ainda existem volumes nomeados antigos;
- interrompe a atualização quando encontra dados antigos ainda não migrados;
- usa GHCR ou build local conforme `INSTALL_SOURCE`.

## Migração das versões 0.2.2 ou anteriores

As versões anteriores utilizavam volumes Docker nomeados. Antes do primeiro deploy da 0.2.3:

```bash
docker compose down
bash deploy/migrate-named-volumes.sh --stack-dir /caminho/da/stack
```

Com nome de projeto explícito:

```bash
bash deploy/migrate-named-volumes.sh \
  --stack-dir /caminho/da/stack \
  --project argws-git-monitor
```

O migrador:

1. localiza os volumes `${COMPOSE_PROJECT_NAME}_postgres_data`, `${COMPOSE_PROJECT_NAME}_redis_data` e `${COMPOSE_PROJECT_NAME}_rabbitmq_data`;
2. recusa a migração se algum volume estiver em uso;
3. recusa sobrescrever uma pasta `data-*` não vazia;
4. copia os dados para o diretório da stack;
5. preserva os volumes anteriores para rollback.

Na instalação pela raiz:

```bash
make migrate-storage
```

Depois de validar a aplicação e o backup, os volumes antigos podem ser removidos manualmente. Não os remova antes da validação.

## Atualização pelo pacote Docker GHCR

```bash
cd deploy/docker
docker compose --env-file .env -f compose.ghcr.yaml pull
docker compose --env-file .env -f compose.ghcr.yaml up -d --no-build --remove-orphans
```

## Atualização pelo Dockge

```bash
cd /diretorio/fisico/da/stack/argws-git-monitor
docker compose --env-file .env -f compose.yaml pull
docker compose --env-file .env -f compose.yaml up -d --no-build --remove-orphans
```

## Imagens versionadas

```text
ghcr.io/wkarts/argws-git-monitor-api:0.2.3
ghcr.io/wkarts/argws-git-monitor-web:0.2.3
```

Pull manual:

```bash
docker pull ghcr.io/wkarts/argws-git-monitor-api:0.2.3
docker pull ghcr.io/wkarts/argws-git-monitor-web:0.2.3
```

Pacotes privados:

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u wkarts --password-stdin
```

## Build local

```bash
cd deploy/docker
bash generate-env.sh
bash deploy-local.sh
```

## CloudPanel

O pacote `deploy/cloudpanel/dockge/` mantém a Web em `127.0.0.1:8080`. O reverse proxy está em:

```text
deploy/cloudpanel/nginx/argws-git-monitor.conf
```

Os dados continuam na pasta física da stack Dockge, nunca no diretório do site do CloudPanel.

Verificação:

```bash
curl -fsS http://127.0.0.1:8080/api/v1/health/ready
curl -fsS https://git.seu-dominio.com.br/api/v1/health/ready
```

## Backup

Backup lógico do PostgreSQL:

```bash
./scripts/backup.sh
```

Backup físico da stack deve incluir, no mínimo:

```text
.env
compose.yaml
data-postgres/
data-redis/
data-rabbitmq/
backups/
```

Para um backup físico consistente em produção, pare os serviços que escrevem dados ou use snapshots consistentes do sistema de arquivos, além do dump lógico do PostgreSQL.

## Restauração lógica

```bash
./scripts/restore.sh backups/argws-git-monitor_AAAAMMDD_HHMMSS.dump
```

## Remoção dos containers sem apagar os dados

```bash
docker compose down
```

As pastas `./data-*` permanecem intactas.

## Remoção de volumes Docker

```bash
docker compose down -v
```

Na versão 0.2.3, esse comando não apaga PostgreSQL, Redis ou RabbitMQ, porque eles são bind mounts relativos e não volumes nomeados.

## Remoção física completa dos dados

Somente depois de backup e confirmação explícita:

```bash
rm -rf ./data-postgres ./data-redis ./data-rabbitmq
```

Esse comando é irreversível.

## Endpoints de diagnóstico

- `/api/v1/health/live`: processo da API;
- `/api/v1/health/ready`: PostgreSQL e Redis;
- `/api/v1/docs`: Swagger/OpenAPI;
- `/metrics`: métricas Prometheus.
