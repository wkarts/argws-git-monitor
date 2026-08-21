# Deploy pelo Dockge

Este diretório é uma stack completa e independente para o Dockge. Ele usa as imagens publicadas no GHCR e não contém blocos de build.

## Conteúdo

```text
compose.yaml
.env.example
generate-env.sh
deploy.sh
```

## Persistência dentro da stack

Quando esta pasta é copiada para o diretório de stacks do Dockge, os dados ficam dentro da própria pasta física da stack:

```text
argws-git-monitor/
├── compose.yaml
├── .env
├── data-postgres/
├── data-redis/
└── data-rabbitmq/
```

O Compose utiliza exclusivamente:

```yaml
- ./data-postgres:/var/lib/postgresql/data
- ./data-redis:/data
- ./data-rabbitmq:/var/lib/rabbitmq
```

Não há volume nomeado nem caminho absoluto do Linux para os dados da aplicação.

## Instalação pelo diretório de stacks

```bash
cd /caminho/das/stacks
mkdir -p argws-git-monitor
cp -a /caminho/do/repositorio/deploy/dockge/. argws-git-monitor/
cd argws-git-monitor
bash generate-env.sh --url https://git.seu-dominio.com.br --bind 127.0.0.1
bash deploy.sh
```

Depois, abra o Dockge e selecione a stack `argws-git-monitor`.

## Instalação pela interface

1. Crie uma stack chamada `argws-git-monitor`.
2. Cole o conteúdo de `compose.yaml`.
3. Coloque o `.env` no diretório físico da stack ou cadastre as variáveis no Dockge.
4. Confirme que as fontes dos volumes começam com `./data-`.
5. Execute **Pull** e **Deploy**.
6. Aguarde `migrate` terminar com código zero.
7. Confirme os serviços saudáveis.

## Atualização de versões anteriores

Antes de atualizar uma stack que ainda usa volumes nomeados:

```bash
docker compose --env-file .env -f compose.yaml down
bash ../migrate-named-volumes.sh --stack-dir "$PWD"
bash deploy.sh
```

Quando o script comum não estiver no diretório pai, execute-o a partir do pacote da release informando `--stack-dir` com o caminho físico desta stack.

## Atualização normal

```bash
docker compose --env-file .env -f compose.yaml pull
docker compose --env-file .env -f compose.yaml up -d --no-build --remove-orphans
```

## Verificação

```bash
docker compose --env-file .env -f compose.yaml ps
docker compose --env-file .env -f compose.yaml logs --tail=200 migrate api web
curl -fsS http://127.0.0.1:8080/api/v1/health/ready
```

## GHCR privado

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u wkarts --password-stdin
```

## Uso com CloudPanel

Para publicar a aplicação por domínio e HTTPS no CloudPanel, utilize `deploy/cloudpanel/`. Nessa modalidade, a porta Web permanece em `127.0.0.1` e o CloudPanel atua como reverse proxy.
