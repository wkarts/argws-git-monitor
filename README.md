# ARGWS Git Monitor

Central operacional **mobile-first** para monitorar repositórios públicos e privados do GitHub em uma única PWA. O projeto inclui API, frontend, workers, PostgreSQL, Redis, RabbitMQ, migrations, autenticação, Docker, CI/CD, backup, GitHub Release e imagens no GHCR.

## Recursos entregues

- Dashboard operacional no padrão visual aprovado.
- Repositórios, Pull Requests, Actions, Releases, Issues, Alertas e Configurações.
- Experiência mobile-first e PWA instalável.
- Integração com repositórios públicos e privados do GitHub.
- Sincronização automática, manual e por webhook.
- Reexecução e cancelamento de workflows conforme as permissões do token.
- Token GitHub criptografado no PostgreSQL.
- JWT, refresh rotativo, Argon2 e troca obrigatória da senha inicial.
- Logs estruturados, health checks, métricas, backup e restauração.
- Docker Compose com deploy separado para CloudPanel, Dockge, Portainer, GHCR e build local.

## Interface visual

A interface aprovada na versão 0.2.0 permanece como contrato visual da série 0.2.x.

![Dashboard desktop](docs/previews/argws-git-monitor-dashboard-desktop-v0.2.0.png)

![Dashboard mobile](docs/previews/argws-git-monitor-dashboard-mobile-v0.2.0.png)

Os critérios visuais estão em `docs/CONTRATO_VISUAL.md`.

## Deploys separados

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

| Ambiente | Diretório | Uso |
|---|---|---|
| CloudPanel + Dockge | `deploy/cloudpanel/` | Containers no Dockge e domínio/HTTPS no CloudPanel |
| Dockge | `deploy/dockge/` | Stack pronta para o diretório físico do Dockge |
| Portainer | `deploy/portainer/` | Stack preparada para Web Editor ou repositório Git |
| Docker Compose | `deploy/docker/` | Imagens GHCR ou build local |

## Armazenamento relativo à stack

A partir da versão **0.2.3**, os dados persistentes não usam volumes nomeados nem diretórios absolutos do Linux. Todos os arquivos Compose utilizam fontes iniciadas por `./`:

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

A estrutura física de cada stack fica assim:

```text
pasta-da-stack/
├── compose.yaml
├── .env
├── data-postgres/
├── data-redis/
└── data-rabbitmq/
```

Consequências práticas:

- os dados acompanham o diretório da stack;
- o Dockge armazena os dados dentro do diretório físico daquela stack;
- o Portainer resolve os caminhos dentro do diretório de trabalho da stack;
- o CloudPanel continua apenas como reverse proxy e não recebe os dados;
- `docker compose down` não remove as pastas `data-*`;
- backup e auditoria física ficam mais simples.

As pastas são criadas automaticamente pelos geradores e scripts de deploy.

## Migração de volumes nomeados anteriores

Instalações até a versão 0.2.2 devem migrar antes do primeiro deploy 0.2.3:

```bash
docker compose down
bash deploy/migrate-named-volumes.sh --stack-dir /caminho/da/stack
```

O migrador:

- identifica `${COMPOSE_PROJECT_NAME}_postgres_data`;
- identifica `${COMPOSE_PROJECT_NAME}_redis_data`;
- identifica `${COMPOSE_PROJECT_NAME}_rabbitmq_data`;
- copia os arquivos para `./data-postgres`, `./data-redis` e `./data-rabbitmq`;
- recusa sobrescrever diretórios não vazios;
- preserva os volumes antigos para rollback.

Na instalação pela raiz também existe o atalho:

```bash
make migrate-storage
```

## Instalação direta

Os instaladores da raiz continuam disponíveis e criam as pastas relativas automaticamente.

### Windows

1. Extraia a GitHub Release.
2. Abra o Docker Desktop.
3. Execute `INSTALAR_WINDOWS.bat`.
4. Acesse `http://localhost:8080`.
5. Consulte `CREDENCIAIS_INICIAIS.txt`.

### Linux

```bash
chmod +x INSTALAR_LINUX.sh
./INSTALAR_LINUX.sh
```

## Docker Compose separado

### Imagens GHCR

```bash
cd deploy/docker
bash generate-env.sh
bash deploy-ghcr.sh
```

### Build local

```bash
cd deploy/docker
bash generate-env.sh
bash deploy-local.sh
```

## Dockge

```bash
cd deploy/dockge
bash generate-env.sh --url https://git.seu-dominio.com.br --bind 127.0.0.1
bash deploy.sh
```

Copie o conteúdo completo dessa pasta para o diretório de armazenamento de stacks do Dockge. Os diretórios `data-*` serão criados no mesmo local.

## CloudPanel junto com Dockge

```bash
cd deploy/cloudpanel/dockge
bash generate-env.sh --url https://git.seu-dominio.com.br
bash deploy.sh
```

Depois, aplique:

```text
deploy/cloudpanel/nginx/argws-git-monitor.conf
```

A Web fica em `127.0.0.1:8080`, enquanto domínio e TLS são administrados pelo CloudPanel.

## Portainer

Use:

```text
deploy/portainer/compose.yaml
deploy/portainer/stack.env.example
```

Para gerar as variáveis:

```bash
cd deploy/portainer
bash generate-stack-env.sh --url https://git.seu-dominio.com.br --bind 127.0.0.1
```

Importe `stack.env` em **Environment variables**.

## Imagens Docker

```text
ghcr.io/wkarts/argws-git-monitor-api:0.2.3
ghcr.io/wkarts/argws-git-monitor-web:0.2.3
```

Tags publicadas:

```text
latest
sha-<commit>
0.2.3
0.2
```

Pull versionado:

```bash
docker pull ghcr.io/wkarts/argws-git-monitor-api:0.2.3
docker pull ghcr.io/wkarts/argws-git-monitor-web:0.2.3
```

Pacotes privados:

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u wkarts --password-stdin
```

## Primeiro acesso e GitHub

1. Entre com as credenciais geradas.
2. Troque a senha administrativa.
3. Abra **Configurações > Nova conexão**.
4. Cadastre um token fine-grained.
5. Importe os repositórios autorizados.

Permissões recomendadas:

| Permissão | Monitoramento | Operação |
|---|---:|---:|
| Metadata | leitura | leitura |
| Contents | leitura | leitura |
| Actions | leitura | escrita |
| Pull requests | leitura | leitura |
| Issues | leitura | leitura |
| Webhooks | nenhuma | escrita |

## Serviços Docker

| Serviço | Papel |
|---|---|
| `web` | Vue 3 PWA e proxy Nginx da API |
| `api` | FastAPI e OpenAPI |
| `worker` | Celery |
| `beat` | Agendador Celery |
| `migrate` | Alembic e bootstrap |
| `postgres` | Persistência principal |
| `redis` | Cache e resultados |
| `rabbitmq` | Broker das filas |

Portas:

- aplicação: `8080`;
- RabbitMQ Management: `127.0.0.1:15672`;
- PostgreSQL, Redis e AMQP não são publicados no host.

## Operação

```bash
./scripts/start.sh
./scripts/stop.sh
./scripts/status.sh
./scripts/logs.sh
./scripts/backup.sh
./scripts/restore.sh backups/arquivo.dump
./scripts/update.sh
```

Atalhos:

```bash
make validate
make validate-deploys
make deploy-ghcr
make deploy-local
make deploy-dockge
make migrate-storage
```

## CI/CD

A versão deve coincidir em:

```text
VERSION
backend/pyproject.toml
frontend/package.json
```

O pipeline:

1. valida backend, frontend, pacote e deploys;
2. exige bind mounts relativos em todos os Compose de produção;
3. rejeita volumes nomeados para PostgreSQL, Redis e RabbitMQ;
4. constrói API e Web para `linux/amd64` e `linux/arm64`;
5. publica e inspeciona os manifests no GHCR;
6. cria a tag e a GitHub Release;
7. publica o pacote completo e o pacote separado de deploys.

Versão atual: **0.2.3**. Git tag: **v0.2.3**. Tag Docker: **0.2.3**.

## Documentação

- `deploy/README.md`
- `deploy/cloudpanel/README.md`
- `deploy/dockge/README.md`
- `deploy/portainer/README.md`
- `deploy/docker/README.md`
- `docs/ARQUITETURA.md`
- `docs/GITHUB.md`
- `docs/OPERACAO.md`
- `docs/SEGURANCA.md`
- `docs/CONTRATO_VISUAL.md`
- `docs/DEPLOY_CLOUDPANEL_DOCKGE.md`

## Desenvolvimento

```bash
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
```

O volume `frontend_node_modules` do ambiente de desenvolvimento permanece efêmero e não contém dados de produção. A regra de armazenamento relativo é aplicada aos dados persistentes de PostgreSQL, Redis e RabbitMQ.

## Licença

Software de uso autorizado. Consulte `LICENSE`.
