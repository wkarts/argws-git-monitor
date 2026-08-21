# Deploy com Docker Compose

Este diretório oferece dois modos independentes de implantação.

## Arquivos

```text
compose.ghcr.yaml   # usa imagens :latest prontas do GHCR
compose.local.yaml  # constrói API e Web :latest a partir de ../../backend e ../../frontend
.env.example        # modelo de variáveis sem versão/tag
 generate-env.sh    # gera .env e cria as pastas persistentes
deploy-ghcr.sh      # pull, recriação e deploy pelas imagens publicadas
deploy-local.sh     # build e deploy pelo código-fonte
```

## Regra de versão

O deploy não recebe `APP_VERSION` nem `IMAGE_TAG`.

```text
ghcr.io/wkarts/argws-git-monitor-api:latest
ghcr.io/wkarts/argws-git-monitor-web:latest
```

A versão exibida é interna ao artefato:

- API: metadata de `argws-git-monitor-api`;
- frontend: `frontend/package.json`, incorporado no build pelo Vite.

Assim, atualizar a aplicação significa baixar/reconstruir `latest` e recriar os containers; não é necessário editar número de versão no `.env`.

## Persistência no próprio diretório

Os três dados persistentes são bind mounts relativos ao diretório `deploy/docker`:

```text
deploy/docker/
├── data-postgres/
├── data-redis/
└── data-rabbitmq/
```

Mapeamentos:

```yaml
- ./data-postgres:/var/lib/postgresql/data
- ./data-redis:/data
- ./data-rabbitmq:/var/lib/rabbitmq
```

Não são utilizados volumes Docker nomeados nem caminhos absolutos como `/opt`, `/var/lib` ou `/home` no lado do host.

## Opção recomendada: GHCR

```bash
cd deploy/docker
bash generate-env.sh
bash deploy-ghcr.sh
```

O `deploy-ghcr.sh` executa `pull` e `up --force-recreate`, garantindo que o container em execução use o digest atual de `latest`.

Quando os pacotes estiverem privados:

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u wkarts --password-stdin
bash deploy-ghcr.sh
```

## Build local

O build local exige o repositório completo, porque os contextos são `../../backend` e `../../frontend`.

```bash
cd deploy/docker
bash generate-env.sh
bash deploy-local.sh
```

Execução manual equivalente:

```bash
docker compose --env-file .env -f compose.local.yaml up -d --build --force-recreate --remove-orphans
```

## URL pública ou porta diferente

```bash
bash generate-env.sh \
  --url https://git.seu-dominio.com.br \
  --bind 127.0.0.1 \
  --port 8080
```

## Migração de instalações com volumes nomeados

```bash
cd deploy/docker
docker compose --env-file .env -f compose.ghcr.yaml down
bash ../migrate-named-volumes.sh --stack-dir "$PWD"
bash deploy-ghcr.sh
```

O migrador não exclui os volumes antigos.

## Operação

GHCR:

```bash
docker compose --env-file .env -f compose.ghcr.yaml ps
docker compose --env-file .env -f compose.ghcr.yaml logs -f --tail=200
docker compose --env-file .env -f compose.ghcr.yaml pull
docker compose --env-file .env -f compose.ghcr.yaml up -d --no-build --force-recreate --remove-orphans
```

Build local:

```bash
docker compose --env-file .env -f compose.local.yaml ps
docker compose --env-file .env -f compose.local.yaml logs -f --tail=200
docker compose --env-file .env -f compose.local.yaml up -d --build --force-recreate --remove-orphans
```

## Backup

Como os dados ficam ao lado do Compose, o backup físico pode incluir:

```text
.env
compose.*.yaml
data-postgres/
data-redis/
data-rabbitmq/
```

Para consistência do PostgreSQL, prefira também o backup lógico fornecido pelo projeto antes de copiar os diretórios em produção.

## Remoção

`docker compose down` não apaga as pastas `./data-*`. A exclusão dos dados só ocorre quando esses diretórios forem removidos fisicamente.
