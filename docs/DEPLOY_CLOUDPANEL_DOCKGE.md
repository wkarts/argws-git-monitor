# Deploy no Dockge, Portainer ou CloudPanel

## Arquivos disponíveis

| Arquivo | Uso |
|---|---|
| `compose.yaml` | build local a partir do código-fonte |
| `compose.ghcr.yaml` | override para usar imagens prontas do GHCR |
| `compose.dockge.yaml` | stack autônoma para Dockge/Portainer usando GHCR |

## Preparação

Na raiz do projeto:

```bash
./scripts/generate-env.sh
```

Ajuste no `.env` somente os dados do ambiente, como domínio e porta. Não publique esse arquivo no Git.

Para usar uma versão específica das imagens:

```dotenv
IMAGE_TAG=0.2.1
INSTALL_SOURCE=ghcr
```

A tag Docker é `0.2.1`; a Git tag da release é `v0.2.1`.

## Dockge

1. Crie uma nova stack.
2. Use o conteúdo de `compose.dockge.yaml`.
3. Coloque o arquivo `.env` no diretório da stack.
4. Salve e execute o pull/deploy.
5. Aguarde `migrate` concluir com código zero.
6. Confirme `postgres`, `redis`, `rabbitmq`, `api` e `web` saudáveis.

Linha de comando equivalente:

```bash
docker compose -f compose.dockge.yaml pull
docker compose -f compose.dockge.yaml up -d --no-build --remove-orphans
```

## Portainer

1. Crie uma stack pelo editor Web ou repositório Git.
2. Selecione `compose.dockge.yaml` como arquivo da stack.
3. Cadastre as variáveis a partir do `.env` gerado.
4. Faça o deploy.

## Build local

Quando o host deve construir as imagens:

```dotenv
INSTALL_SOURCE=local
IMAGE_TAG=local
```

Depois:

```bash
docker compose -f compose.yaml up -d --build --remove-orphans
```

## GHCR privado

Quando as imagens estiverem privadas, autentique o host antes do pull:

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u wkarts --password-stdin
```

O token precisa somente de leitura de pacotes. O instalador automático tenta o GHCR e usa build local como contingência quando o pull não estiver disponível.

## CloudPanel/Nginx

Configure primeiro a URL pública:

```bash
./scripts/configure-domain.sh https://git.seu-dominio.com.br
```

Para impedir exposição direta da porta em interfaces públicas:

```dotenv
APP_BIND_ADDRESS=127.0.0.1
```

Aponte o reverse proxy para:

```text
http://127.0.0.1:8080
```

Exemplo Nginx externo:

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 90s;
}
```

O certificado TLS deve ser emitido no proxy externo. Depois do HTTPS ativo, configure os webhooks na aplicação.

## Verificação

```bash
docker compose -f compose.dockge.yaml ps
docker compose -f compose.dockge.yaml logs --tail=200 migrate api web
curl -fsS http://127.0.0.1:8080/api/v1/health/ready
```

A resposta de prontidão deve ser HTTP 200 antes de liberar o domínio ao usuário.
