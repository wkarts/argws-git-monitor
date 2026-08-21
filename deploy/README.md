# Deploys do ARGWS Git Monitor

Este diretório concentra os pacotes de implantação separados por ambiente.

```text
deploy/
├── migrate-named-volumes.sh
├── cloudpanel/
│   ├── README.md
│   ├── nginx/argws-git-monitor.conf
│   └── dockge/
│       ├── compose.yaml
│       ├── .env.example
│       ├── generate-env.sh
│       └── deploy.sh
├── dockge/
│   ├── README.md
│   ├── compose.yaml
│   ├── .env.example
│   ├── generate-env.sh
│   └── deploy.sh
├── portainer/
│   ├── README.md
│   ├── compose.yaml
│   ├── stack.env.example
│   └── generate-stack-env.sh
└── docker/
    ├── README.md
    ├── compose.ghcr.yaml
    ├── compose.local.yaml
    ├── .env.example
    ├── generate-env.sh
    ├── deploy-ghcr.sh
    └── deploy-local.sh
```

## Escolha rápida

| Ambiente | Diretório | Finalidade |
|---|---|---|
| CloudPanel + Dockge | `deploy/cloudpanel/` | containers no Dockge e domínio/HTTPS no CloudPanel |
| Dockge | `deploy/dockge/` | stack pronta para o diretório físico do Dockge |
| Portainer | `deploy/portainer/` | Web Editor ou repositório Git com variáveis do painel |
| Docker Compose | `deploy/docker/` | execução por GHCR ou build local |

## Persistência obrigatoriamente relativa

Todos os pacotes persistem dados ao lado do `compose.yaml`:

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

Resultado:

```text
pasta-da-stack/
├── compose.yaml
├── .env
├── data-postgres/
├── data-redis/
└── data-rabbitmq/
```

Não são usados caminhos absolutos do host nem volumes Docker nomeados para os dados principais.

## Migração de versões antigas

```bash
docker compose down
bash deploy/migrate-named-volumes.sh --stack-dir /caminho/da/stack
```

O migrador copia os dados para `./data-*` e preserva os volumes antigos para rollback.

## Imagens oficiais v0.3.0

```text
ghcr.io/wkarts/argws-git-monitor-api:0.3.0
ghcr.io/wkarts/argws-git-monitor-web:0.3.0
```

Também são publicadas `latest`, `0.3` e `sha-<commit>`.

## Segurança

- não versione `.env`, `stack.env`, tokens, chaves ou senhas;
- mantenha PostgreSQL, Redis e AMQP sem publicação externa;
- use HTTPS para webhooks;
- faça backup externo das pastas persistentes e do PostgreSQL;
- no CloudPanel, mantenha a Web ligada a `127.0.0.1` e publique somente pelo reverse proxy.
