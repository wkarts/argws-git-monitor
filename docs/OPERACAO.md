# Operação

## Pacotes oficiais de deploy

```text
deploy/cloudpanel/
deploy/dockge/
deploy/portainer/
deploy/docker/
```

Consulte `deploy/README.md` para escolher a modalidade correta.

## Estado da stack

Na instalação pela raiz:

```bash
./scripts/status.sh
```

Docker separado por GHCR:

```bash
docker compose \
  --env-file deploy/docker/.env \
  -f deploy/docker/compose.ghcr.yaml \
  ps
```

Dockge separado:

```bash
docker compose \
  --env-file deploy/dockge/.env \
  -f deploy/dockge/compose.yaml \
  ps
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

Nos pacotes separados, sempre informe o Compose e o ambiente correspondentes.

## Reinício seguro

```bash
docker compose restart api worker beat web
```

## Atualização padrão pela raiz

```bash
./scripts/update.sh
```

O script respeita `INSTALL_SOURCE` no `.env`:

- `ghcr`: baixa as imagens publicadas e inicia sem build;
- `local`: atualiza o código e reconstrói as imagens;
- se o pull do GHCR falhar, o modo `ghcr` usa build local como contingência.

## Atualização pelo pacote Docker GHCR

```bash
cd deploy/docker
docker compose --env-file .env -f compose.ghcr.yaml pull
docker compose --env-file .env -f compose.ghcr.yaml up -d --no-build --remove-orphans
```

## Atualização pelo Dockge

```bash
cd deploy/dockge
docker compose --env-file .env -f compose.yaml pull
docker compose --env-file .env -f compose.yaml up -d --no-build --remove-orphans
```

## Imagens versionadas

A tag das imagens não usa o prefixo `v`:

```text
ghcr.io/wkarts/argws-git-monitor-api:0.2.2
ghcr.io/wkarts/argws-git-monitor-web:0.2.2
```

Pull manual:

```bash
docker pull ghcr.io/wkarts/argws-git-monitor-api:0.2.2
docker pull ghcr.io/wkarts/argws-git-monitor-web:0.2.2
```

Se os pacotes estiverem privados:

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u wkarts --password-stdin
```

## Build local separado

```bash
cd deploy/docker
bash generate-env.sh
bash deploy-local.sh
```

Ou manualmente:

```bash
docker compose --env-file .env -f compose.local.yaml up -d --build --remove-orphans
```

## CloudPanel

O pacote `deploy/cloudpanel/dockge/` mantém a aplicação em `127.0.0.1:8080`. O reverse proxy está em:

```text
deploy/cloudpanel/nginx/argws-git-monitor.conf
```

Verificação local e pública:

```bash
curl -fsS http://127.0.0.1:8080/api/v1/health/ready
curl -fsS https://git.seu-dominio.com.br/api/v1/health/ready
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
