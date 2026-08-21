# Deploys do ARGWS Git Monitor

Este diretório concentra os arquivos de implantação separados por ambiente. Cada pasta contém o `compose.yaml`, o modelo de variáveis e as instruções específicas da plataforma.

## Estrutura

```text
deploy/
├── migrate-named-volumes.sh
├── cloudpanel/
│   ├── README.md
│   ├── nginx/
│   │   └── argws-git-monitor.conf
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
| CloudPanel + Dockge | `deploy/cloudpanel/` | Containers no Dockge e domínio/HTTPS por reverse proxy no CloudPanel |
| Dockge | `deploy/dockge/` | Stack pronta para copiar ao diretório físico de stacks |
| Portainer | `deploy/portainer/` | Stack compatível com Web Editor ou repositório Git |
| Docker Compose | `deploy/docker/` | Execução por GHCR ou build local |

## Persistência obrigatoriamente relativa

Os bancos e filas não usam volumes nomeados nem caminhos absolutos do Linux. Cada `compose.yaml` grava dentro do próprio diretório da stack:

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

A estrutura criada ao lado do Compose é:

```text
./data-postgres/
./data-redis/
./data-rabbitmq/
```

Assim, ao copiar, mover ou fazer backup do diretório da stack, os dados persistentes permanecem agrupados com ela. Os geradores e scripts de deploy criam essas pastas automaticamente.

## Migração da versão anterior

As versões anteriores usavam volumes Docker nomeados. Antes de atualizar uma instalação que já possui dados:

```bash
docker compose down
bash deploy/migrate-named-volumes.sh --stack-dir /caminho/da/stack
```

O script copia os dados para `./data-*` e preserva os volumes antigos para rollback. Ele não sobrescreve diretórios que já contenham arquivos.

## Imagens oficiais

```text
ghcr.io/wkarts/argws-git-monitor-api:0.2.3
ghcr.io/wkarts/argws-git-monitor-web:0.2.3
```

Também são publicadas as tags `latest`, `0.2` e `sha-<commit>`.

## Requisitos comuns

- Docker Engine ou Docker Desktop com Docker Compose v2;
- acesso ao GHCR ou código-fonte para build local;
- uma porta livre, por padrão `8080`;
- domínio e HTTPS para acesso público e webhooks;
- segredos gerados antes do primeiro deploy;
- backup externo periódico de todo o diretório da stack.

Nenhum `.env`, senha, token, credencial ou conteúdo das pastas `data-*` deve ser enviado ao GitHub.
