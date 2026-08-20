# Deploy pelo Dockge

Este diretório é uma stack completa e independente para o Dockge. Ele usa as imagens publicadas no GHCR e não contém blocos de build.

## Conteúdo

```text
compose.yaml
.env.example
generate-env.sh
deploy.sh
```

## Instalação pelo diretório de stacks

No servidor onde o Dockge está instalado:

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

1. Crie uma nova stack com o nome `argws-git-monitor`.
2. Cole o conteúdo de `compose.yaml` no editor.
3. Gere o arquivo `.env` no diretório físico da stack usando `generate-env.sh`, ou cadastre as variáveis no editor do Dockge.
4. Execute **Pull** e depois **Deploy**.
5. Aguarde o serviço `migrate` terminar com código zero.
6. Confirme que `postgres`, `redis`, `rabbitmq`, `api` e `web` estão saudáveis.

## Atualização

```bash
cd deploy/dockge
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

Quando o pacote estiver privado, autentique o host antes do deploy:

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u wkarts --password-stdin
```

## Uso com CloudPanel

Para publicar a aplicação por domínio e HTTPS no CloudPanel, utilize o pacote específico em:

```text
deploy/cloudpanel/
```

Nessa modalidade, a porta da aplicação fica vinculada a `127.0.0.1` e o CloudPanel atua como reverse proxy.
