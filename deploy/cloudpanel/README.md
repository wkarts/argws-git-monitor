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

## Persistência dentro da pasta da stack

Depois que `dockge/` for copiada para o diretório físico de stacks, os dados serão criados ao lado do `compose.yaml`:

```text
argws-git-monitor/
├── compose.yaml
├── .env
├── data-postgres/
├── data-redis/
└── data-rabbitmq/
```

O host usa somente caminhos relativos:

```yaml
- ./data-postgres:/var/lib/postgresql/data
- ./data-redis:/data
- ./data-rabbitmq:/var/lib/rabbitmq
```

O CloudPanel não armazena os dados da aplicação e nenhum Compose aponta para um diretório absoluto do Linux.

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

O gerador cria `./data-postgres`, `./data-redis` e `./data-rabbitmq` e fixa:

```dotenv
APP_BIND_ADDRESS=127.0.0.1
```

## 3. Subir a stack

```bash
bash deploy.sh
```

Ou pelo Dockge:

1. abra `argws-git-monitor`;
2. valide `compose.yaml`;
3. confirme as fontes `./data-*`;
4. execute **Pull** e **Deploy**;
5. confirme `migrate` concluído;
6. valide os serviços saudáveis.

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

## 7. Atualização

```bash
cd /caminho/das/stacks/argws-git-monitor
docker compose --env-file .env -f compose.yaml pull
docker compose --env-file .env -f compose.yaml up -d --no-build --remove-orphans
```

## 8. Migração de volumes nomeados antigos

Antes do primeiro deploy da versão 0.2.3 em uma instalação existente:

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
- não publique PostgreSQL, Redis ou AMQP;
- mantenha o RabbitMQ Management em `127.0.0.1`;
- não versione `.env` nem as pastas `data-*`;
- mantenha TLS ativo no CloudPanel;
- faça backup lógico do PostgreSQL e backup externo da pasta da stack.
