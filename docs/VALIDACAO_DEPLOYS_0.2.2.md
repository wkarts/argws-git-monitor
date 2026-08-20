# Validação dos deploys — ARGWS Git Monitor v0.2.2

## Objetivo

A versão 0.2.2 estabelece `deploy/` como diretório canônico para implantação, mantendo os arquivos da raiz apenas por compatibilidade com instalações anteriores.

## Pacotes entregues

| Ambiente | Compose | Ambiente | Automação |
|---|---|---|---|
| CloudPanel + Dockge | `deploy/cloudpanel/dockge/compose.yaml` | `.env.example` | `generate-env.sh` e `deploy.sh` |
| Dockge | `deploy/dockge/compose.yaml` | `.env.example` | `generate-env.sh` e `deploy.sh` |
| Portainer | `deploy/portainer/compose.yaml` | `stack.env.example` | `generate-stack-env.sh` |
| Docker GHCR | `deploy/docker/compose.ghcr.yaml` | `.env.example` | `deploy-ghcr.sh` |
| Docker local | `deploy/docker/compose.local.yaml` | `.env.example` | `deploy-local.sh` |

## CloudPanel

O pacote CloudPanel mantém a aplicação vinculada a `127.0.0.1`, evitando exposição direta da porta Docker. O arquivo `deploy/cloudpanel/nginx/argws-git-monitor.conf` encaminha o domínio HTTPS para `http://127.0.0.1:8080` e preserva os cabeçalhos de proxy.

## Dockge

A pasta `deploy/dockge/` pode ser copiada diretamente para o diretório de stacks. O arquivo `.env` é gerado dentro da própria pasta, permitindo operação pelo Dockge ou pela linha de comando.

## Portainer

O Compose específico do Portainer não utiliza `env_file`. As variáveis são importadas no painel, evitando dependência de arquivos que podem não existir no contexto de uma stack criada pelo Web Editor ou por repositório Git.

## Docker Compose

Existem dois fluxos independentes:

- `compose.ghcr.yaml`: baixa imagens prontas e não exige o código-fonte;
- `compose.local.yaml`: constrói a API em `../../backend` e a Web em `../../frontend`.

## Validação automatizada

```bash
python scripts/validate-deploy-layout.py
```

O script verifica:

1. presença de todos os diretórios e arquivos obrigatórios;
2. existência dos serviços `postgres`, `redis`, `rabbitmq`, `migrate`, `api`, `worker`, `beat` e `web`;
3. uso de imagens nos pacotes GHCR, Dockge, Portainer e CloudPanel;
4. contextos corretos no build local;
5. bind local e reverse proxy do CloudPanel;
6. ausência de `env_file` no Portainer;
7. sincronização de `APP_VERSION` e `IMAGE_TAG` com o arquivo `VERSION`.

## Versão

```text
Aplicação: 0.2.2
Git tag: v0.2.2
Docker tag: 0.2.2
```
