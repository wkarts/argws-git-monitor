# Deploy com CloudPanel + Dockge

Este pacote separa claramente as responsabilidades:

```text
Dockge     → executa e administra os containers e os diretórios de dados
CloudPanel → publica domínio, TLS e reverse proxy Nginx
```

## Estrutura

```text
deploy/cloudpanel/
├── README.md
├── nginx/
│   └── argws-git-monitor.conf
└── dockge/
    ├── compose.yaml
    ├── .env.example
    ├── generate-env.sh
    └── deploy.sh
```

## Regra de imagem e versão

CloudPanel + Dockge usa sempre:

```text
ghcr.io/wkarts/argws-git-monitor-api:latest
ghcr.io/wkarts/argws-git-monitor-web:latest
```

Não configure `APP_VERSION` nem `IMAGE_TAG`. A API obtém a versão do próprio pacote Python e o frontend do próprio `package.json` incorporado no build.

## Persistência dentro da pasta da stack

Depois que `dockge/` for copiada para o diretório físico de stacks, os dados serão criados ao lado do `compose.yaml`:

```text
argws-git-monitor/
├── compose.yaml
├── .env
├── data-postgres/
├── data-redis/
├── data-rabbitmq/
├── data-minio/
├── data-backups/
└── data-logs/
```

O host usa somente caminhos relativos:

```yaml
- ./data-postgres:/var/lib/postgresql/data
- ./data-redis:/data
- ./data-rabbitmq:/var/lib/rabbitmq
- ./data-minio:/data
- ./data-backups:/data/backups
```

`./data-backups:/data/backups` é montado simultaneamente na API e no worker. Isso é obrigatório para que o fallback local de backup seja persistente e compartilhado. O CloudPanel não armazena os dados da aplicação e nenhum Compose aponta para um diretório absoluto do Linux.

## 1. Preparar a stack do Dockge

```bash
mkdir -p /caminho/das/stacks/argws-git-monitor
cp -a deploy/cloudpanel/dockge/. /caminho/das/stacks/argws-git-monitor/
cd /caminho/das/stacks/argws-git-monitor
```

Use o diretório real configurado como armazenamento de stacks no Dockge.

## 2. Gerar o ambiente seguro

```bash
bash generate-env.sh \
  --url https://git.seu-dominio.com.br \
  --port 8080
```

O gerador cria `./data-postgres`, `./data-redis`, `./data-rabbitmq`, `./data-minio`, `./data-backups` e `./data-logs`, e fixa:

```dotenv
APP_BIND_ADDRESS=127.0.0.1
MINIO_INTERNAL_ACCESS_KEY=argws-internal
```

O segredo S3 interno usa `APP_SECRET_KEY` por padrão. `GITHUB_WEBHOOK_SECRET` deve ser um segredo HMAC aleatório; não use GitHub PAT nessa variável.

## 3. Subir a stack

```bash
bash deploy.sh
```

Ou pelo Dockge:

1. abra `argws-git-monitor`;
2. valide `compose.yaml`;
3. confirme as fontes `./data-*`;
4. execute **Pull**;
5. execute **Update/Deploy** para recriar os containers;
6. confirme `migrate` concluído;
7. valide os serviços saudáveis, inclusive `minio`.

## 4. Criar o site no CloudPanel

1. crie o site para `git.seu-dominio.com.br`;
2. use reverse proxy;
3. configure o upstream `http://127.0.0.1:8080`;
4. aplique `nginx/argws-git-monitor.conf` no Vhost;
5. emita o certificado Let's Encrypt.

## 5. DNS

```text
Tipo: A
Nome: git
Destino: IP público do servidor
```

## 6. Verificação

```bash
curl -fsS http://127.0.0.1:8080/api/v1/health/ready
curl -fsS https://git.seu-dominio.com.br/api/v1/health/ready
```

No Git Monitor, abra **Backup & Recovery → Testar MinIO/S3**. O diagnóstico deve indicar DNS, TCP, health HTTP e autenticação S3 individualmente.

## 7. Atualização

```bash
cd /caminho/das/stacks/argws-git-monitor
docker compose --env-file .env -f compose.yaml pull
docker compose --env-file .env -f compose.yaml up -d --no-build --force-recreate --remove-orphans
```

O `deploy.sh` já executa esse fluxo e sempre utiliza `:latest`.

### Instalações anteriores ao MinIO interno

Somente executar `docker compose pull` **não adiciona serviços novos ao manifesto existente**. Se o diagnóstico informar que o hostname `minio` não resolve, confira o `compose.yaml` atual. Uma stack compatível precisa conter:

- serviço `minio` conectado à rede `gitmonitor`;
- `MINIO_INTERNAL_ENDPOINT=http://minio:9000` no ambiente da API/worker;
- `./data-minio:/data` no MinIO;
- `./data-backups:/data/backups` no template compartilhado por API/worker;
- inicialização de `data-minio` e `data-backups`.

Para atualizar uma stack antiga sem tocar nos bancos:

```bash
cd /caminho/das/stacks/argws-git-monitor
cp compose.yaml compose.yaml.pre-minio.bak
cp /caminho/do/pacote/deploy/cloudpanel/dockge/compose.yaml ./compose.yaml
mkdir -p data-minio data-backups
# preserve o .env atual; adicione apenas a chave abaixo se ainda não existir
grep -q '^MINIO_INTERNAL_ACCESS_KEY=' .env || printf '\nMINIO_INTERNAL_ACCESS_KEY=argws-internal\n' >> .env
docker compose --env-file .env -f compose.yaml config -q
docker compose --env-file .env -f compose.yaml pull
docker compose --env-file .env -f compose.yaml up -d --no-build --force-recreate --remove-orphans
```

Esse procedimento preserva `data-postgres`, `data-redis`, `data-rabbitmq`, `.env` e os demais dados existentes. Não regenere o `.env` de produção para fazer esse upgrade.

## 8. Migração de volumes nomeados antigos

Para instalações antigas que ainda utilizem volumes nomeados:

```bash
docker compose --env-file .env -f compose.yaml down
bash /caminho/do/pacote/deploy/migrate-named-volumes.sh \
  --stack-dir "$PWD" \
  --project argws-git-monitor
bash deploy.sh
```

Os volumes antigos permanecem disponíveis para rollback.

## Segurança

- mantenha `APP_BIND_ADDRESS=127.0.0.1`;
- não publique PostgreSQL, Redis, AMQP ou MinIO diretamente na internet;
- mantenha o RabbitMQ Management em `127.0.0.1`;
- não versione `.env` nem as pastas `data-*`;
- mantenha TLS ativo no CloudPanel;
- faça backup lógico do PostgreSQL e backup externo da pasta da stack.
