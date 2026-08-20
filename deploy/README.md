# Deploys do ARGWS Git Monitor

Este diretório concentra os arquivos de implantação separados por ambiente. Cada pasta contém o `compose.yaml`, o modelo de variáveis e as instruções específicas da plataforma.

## Estrutura

```text
deploy/
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
| CloudPanel + Dockge | `deploy/cloudpanel/` | Aplicação em containers administrados pelo Dockge e publicada por reverse proxy HTTPS no CloudPanel |
| Dockge | `deploy/dockge/` | Stack pronta para colar ou importar diretamente no Dockge |
| Portainer | `deploy/portainer/` | Stack compatível com Portainer, usando variáveis do próprio painel |
| Docker Compose | `deploy/docker/` | Execução por linha de comando, tanto por imagens GHCR quanto por build local |

## Imagens oficiais

```text
ghcr.io/wkarts/argws-git-monitor-api:0.2.2
ghcr.io/wkarts/argws-git-monitor-web:0.2.2
```

Também são publicadas as tags `latest`, `0.2` e `sha-<commit>`.

## Requisitos comuns

- Docker Engine ou Docker Desktop com Docker Compose v2;
- acesso ao GHCR ou código-fonte disponível para build local;
- uma porta livre para a aplicação, por padrão `8080`;
- domínio e HTTPS para uso público e webhooks do GitHub;
- credenciais e segredos gerados antes do primeiro deploy.

Nenhum arquivo `.env` real, senha, token ou credencial deve ser enviado ao GitHub.
