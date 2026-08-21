# Deploy no CloudPanel, Dockge, Portainer e Docker

A estrutura oficial de implantação fica em:

```text
deploy/
├── cloudpanel/
├── dockge/
├── portainer/
├── docker/
└── migrate-named-volumes.sh
```

## Regra de imagem e versão

Todos os deploys baseados em GHCR usam sempre:

```text
ghcr.io/wkarts/argws-git-monitor-api:latest
ghcr.io/wkarts/argws-git-monitor-web:latest
```

Os modelos não possuem `APP_VERSION` nem `IMAGE_TAG`. A versão exibida no produto vem do próprio artefato:

- backend: metadata do pacote Python;
- frontend: `frontend/package.json`, incorporado pelo Vite no build.

As versões semânticas permanecem apenas no código/release para histórico, CI e rastreabilidade; não são parâmetros do deploy.

## Regra de armazenamento

Todos os Composes de produção utilizam bind mounts relativos ao diretório onde o arquivo Compose está armazenado:

```yaml
- ./data-postgres:/var/lib/postgresql/data
- ./data-redis:/data
- ./data-rabbitmq:/var/lib/rabbitmq
```

Não são permitidos:

- caminhos absolutos do host, como `/opt/...`, `/home/...` ou `/var/lib/...` no lado esquerdo do mapeamento;
- volumes Docker nomeados para PostgreSQL, Redis e RabbitMQ;
- fontes de dados que não comecem com `./`.

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

Copie `deploy/cloudpanel/dockge/` para o diretório físico de stacks do Dockge. Nesse destino serão criadas:

```text
./data-postgres/
./data-redis/
./data-rabbitmq/
```

Preparação:

```bash
cd /diretorio/das/stacks/argws-git-monitor
bash generate-env.sh --url https://git.seu-dominio.com.br
bash deploy.sh
```

A Web fica vinculada a:

```text
http://127.0.0.1:8080
```

O domínio e o certificado TLS ficam no CloudPanel. Os dados permanecem na pasta da stack Dockge.

## Dockge independente

Use:

```text
deploy/dockge/compose.yaml
deploy/dockge/.env.example
deploy/dockge/generate-env.sh
deploy/dockge/deploy.sh
```

Depois de copiar essa pasta ao diretório de stacks:

```bash
cd /diretorio/das/stacks/argws-git-monitor
bash generate-env.sh
bash deploy.sh
```

Os dados serão gravados no mesmo diretório físico, nas pastas `./data-*`.

Atualização manual:

```bash
docker compose --env-file .env -f compose.yaml pull
docker compose --env-file .env -f compose.yaml up -d --no-build --force-recreate --remove-orphans
```

Na interface: **Pull** seguido de **Update/Deploy**.

## Portainer

Use:

```text
deploy/portainer/compose.yaml
deploy/portainer/stack.env.example
deploy/portainer/generate-stack-env.sh
```

O Compose do Portainer não depende de `env_file`. Gere e importe as variáveis:

```bash
cd deploy/portainer
bash generate-stack-env.sh --url https://git.seu-dominio.com.br --bind 127.0.0.1
```

O Portainer resolve `./data-*` dentro do diretório de trabalho da própria stack.

Nas atualizações, habilite o re-pull da imagem e atualize a stack. Nenhum número de versão precisa ser alterado.

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

Nos dois modos, os dados ficam em `deploy/docker/data-*`.

## Migração das instalações anteriores

Quando uma instalação ainda utilizar volumes Docker nomeados:

```bash
docker compose down
bash deploy/migrate-named-volumes.sh --stack-dir /diretorio/fisico/da/stack
```

O script copia os volumes nomeados antigos para as pastas relativas e mantém os volumes originais intactos.

## Verificação

```bash
python scripts/validate-deploy-layout.py
```

O validador confirma:

- existência dos diretórios e arquivos de implantação;
- presença dos oito serviços da stack;
- ausência de build nos pacotes baseados em GHCR;
- uso obrigatório de `:latest` nos deploys;
- ausência de controles externos ativos de versão nos modelos;
- versão interna sincronizada entre `VERSION`, backend e frontend;
- backend resolvendo sua versão pelo próprio pacote;
- frontend resolvendo a versão pelo próprio `package.json`;
- contextos corretos no build local;
- bind `127.0.0.1` no pacote CloudPanel;
- reverse proxy Nginx para a porta local;
- independência de `env_file` no Portainer;
- uso exato de `./data-postgres`, `./data-redis` e `./data-rabbitmq`;
- ausência de volumes nomeados e caminhos absolutos para dados persistentes.
