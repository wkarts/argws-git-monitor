# Deploy com Docker Compose

Este diretório oferece dois modos independentes de implantação.

## Arquivos

```text
compose.ghcr.yaml   # usa as imagens prontas do GitHub Container Registry
compose.local.yaml  # constrói API e Web a partir de ../../backend e ../../frontend
.env.example        # modelo de variáveis
 generate-env.sh    # gera .env com segredos aleatórios
deploy-ghcr.sh      # pull e deploy pelas imagens publicadas
deploy-local.sh     # build e deploy pelo código-fonte
```

## Opção recomendada: GHCR

```bash
cd deploy/docker
bash generate-env.sh
bash deploy-ghcr.sh
```

Imagens utilizadas:

```text
ghcr.io/wkarts/argws-git-monitor-api:0.2.2
ghcr.io/wkarts/argws-git-monitor-web:0.2.2
```

Quando os pacotes estiverem privados:

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u wkarts --password-stdin
bash deploy-ghcr.sh
```

## Build local

O build local exige o repositório completo, porque os contextos ficam em `../../backend` e `../../frontend`.

```bash
cd deploy/docker
bash generate-env.sh
bash deploy-local.sh
```

Execução manual equivalente:

```bash
docker compose --env-file .env -f compose.local.yaml up -d --build --remove-orphans
```

## URL pública ou porta diferente

```bash
bash generate-env.sh \
  --url https://git.seu-dominio.com.br \
  --bind 127.0.0.1 \
  --port 8080
```

## Operação

GHCR:

```bash
docker compose --env-file .env -f compose.ghcr.yaml ps
docker compose --env-file .env -f compose.ghcr.yaml logs -f --tail=200
docker compose --env-file .env -f compose.ghcr.yaml pull
docker compose --env-file .env -f compose.ghcr.yaml up -d --no-build --remove-orphans
```

Build local:

```bash
docker compose --env-file .env -f compose.local.yaml ps
docker compose --env-file .env -f compose.local.yaml logs -f --tail=200
docker compose --env-file .env -f compose.local.yaml up -d --build --remove-orphans
```

## Remoção

Sem apagar os dados:

```bash
docker compose --env-file .env -f compose.ghcr.yaml down
```

Apagando também PostgreSQL, Redis e RabbitMQ:

```bash
docker compose --env-file .env -f compose.ghcr.yaml down -v
```

O segundo comando é irreversível.
