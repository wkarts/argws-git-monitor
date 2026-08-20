# Deploy no CloudPanel, Dockge, Portainer e Docker

Os arquivos de implantação deixaram de ficar misturados na raiz. A estrutura oficial agora está em:

```text
deploy/
├── cloudpanel/
├── dockge/
├── portainer/
└── docker/
```

## CloudPanel junto com Dockge

Use:

```text
deploy/cloudpanel/README.md
deploy/cloudpanel/dockge/compose.yaml
deploy/cloudpanel/dockge/.env.example
deploy/cloudpanel/dockge/generate-env.sh
deploy/cloudpanel/dockge/deploy.sh
deploy/cloudpanel/nginx/argws-git-monitor.conf
```

Preparação:

```bash
cd deploy/cloudpanel/dockge
bash generate-env.sh --url https://git.seu-dominio.com.br
bash deploy.sh
```

A stack vincula a aplicação a:

```text
http://127.0.0.1:8080
```

O domínio e o certificado TLS ficam no CloudPanel. Aplique o snippet Nginx disponível em `deploy/cloudpanel/nginx/argws-git-monitor.conf`.

## Dockge independente

Use:

```text
deploy/dockge/compose.yaml
deploy/dockge/.env.example
deploy/dockge/generate-env.sh
deploy/dockge/deploy.sh
```

Execução:

```bash
cd deploy/dockge
bash generate-env.sh
bash deploy.sh
```

## Portainer

Use:

```text
deploy/portainer/compose.yaml
deploy/portainer/stack.env.example
deploy/portainer/generate-stack-env.sh
```

O Compose do Portainer não depende de `env_file`. Gere as variáveis e importe-as na seção **Environment variables**:

```bash
cd deploy/portainer
bash generate-stack-env.sh --url https://git.seu-dominio.com.br --bind 127.0.0.1
```

## Docker Compose

Imagens GHCR:

```bash
cd deploy/docker
bash generate-env.sh
bash deploy-ghcr.sh
```

Build local:

```bash
cd deploy/docker
bash generate-env.sh
bash deploy-local.sh
```

Arquivos:

```text
deploy/docker/compose.ghcr.yaml
deploy/docker/compose.local.yaml
```

## Imagens da versão

```text
ghcr.io/wkarts/argws-git-monitor-api:0.2.2
ghcr.io/wkarts/argws-git-monitor-web:0.2.2
```

## Verificação

```bash
python scripts/validate-deploy-layout.py
```

O validador confirma:

- existência dos quatro diretórios;
- presença dos oito serviços da stack;
- ausência de build nos pacotes GHCR, Dockge, Portainer e CloudPanel;
- contextos corretos no build local;
- bind `127.0.0.1` no pacote CloudPanel;
- reverse proxy Nginx para a porta local;
- independência de `env_file` no Portainer;
- sincronização da versão nos ambientes.
