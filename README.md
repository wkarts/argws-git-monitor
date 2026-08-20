# ARGWS Git Monitor

Central operacional **mobile-first** para monitorar repositórios públicos e privados do GitHub em uma única PWA. O projeto inclui API, frontend, workers, PostgreSQL, Redis, RabbitMQ, migrations, autenticação, Docker, CI/CD, backup, GitHub Release e imagens no GHCR.

## Recursos entregues

- Dashboard operacional no padrão visual aprovado, com quatro indicadores, saúde segmentada, atividades recentes e tabela compacta.
- Navegação própria para Repositórios, Pull Requests, Actions, Releases, Issues, Alertas e Configurações.
- Experiência mobile-first com navegação inferior, painel “Mais” e alerta crítico de build.
- Repositórios públicos e privados por token GitHub granular.
- Último commit, branch principal, branches, issues, pull requests, releases e Actions.
- Histórico de execuções, PRs e releases por repositório.
- Reexecução completa, reexecução somente de jobs com falha e cancelamento de workflow.
- Sincronização automática, manual e por webhook.
- PWA instalável em celular, tablet e desktop.
- Interface responsiva, tema claro/escuro e comportamento offline.
- Token GitHub criptografado no PostgreSQL e nunca devolvido ao navegador.
- JWT de curta duração, refresh token rotativo/revogável, Argon2 e troca obrigatória da senha inicial.
- Logs estruturados, health checks, métricas Prometheus, backup e restauração.

## Interface visual

A interface aprovada na versão 0.2.0 permanece como contrato visual da série 0.2.x.

![Dashboard desktop](docs/previews/argws-git-monitor-dashboard-desktop-v0.2.0.png)

![Dashboard mobile](docs/previews/argws-git-monitor-dashboard-mobile-v0.2.0.png)

Os critérios, rotas, componentes e larguras de aceitação estão documentados em `docs/CONTRATO_VISUAL.md`.

## Deploys separados

Os pacotes oficiais de implantação ficam em `deploy/`, separados por ambiente:

```text
deploy/
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
| Dockge | `deploy/dockge/` | Stack pronta para o diretório ou editor do Dockge |
| Portainer | `deploy/portainer/` | Stack sem `env_file`, preparada para variáveis do painel |
| Docker Compose | `deploy/docker/` | Imagens GHCR ou build local por linha de comando |

O índice completo está em `deploy/README.md`.

## Instalação direta

Os instaladores da raiz continuam disponíveis por compatibilidade e usam as imagens prontas do GHCR por padrão. Caso o pull não esteja disponível, realizam automaticamente o build local com o código-fonte.

### Windows

1. Extraia o pacote da GitHub Release.
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

O build local usa os contextos `../../backend` e `../../frontend`; portanto, deve ser executado dentro do repositório completo.

## Dockge separado

```bash
cd deploy/dockge
bash generate-env.sh --url https://git.seu-dominio.com.br --bind 127.0.0.1
bash deploy.sh
```

O mesmo `compose.yaml` pode ser colado diretamente no editor do Dockge.

## CloudPanel junto com Dockge

```bash
cd deploy/cloudpanel/dockge
bash generate-env.sh --url https://git.seu-dominio.com.br
bash deploy.sh
```

Depois, aplique o reverse proxy disponível em:

```text
deploy/cloudpanel/nginx/argws-git-monitor.conf
```

A stack CloudPanel mantém a aplicação vinculada a `127.0.0.1:8080`; o domínio e o TLS ficam sob responsabilidade do Nginx administrado pelo CloudPanel.

## Portainer separado

Use:

```text
deploy/portainer/compose.yaml
deploy/portainer/stack.env.example
```

Para gerar variáveis seguras:

```bash
cd deploy/portainer
bash generate-stack-env.sh --url https://git.seu-dominio.com.br --bind 127.0.0.1
```

Importe o conteúdo de `stack.env` na seção **Environment variables** do Portainer.

## Imagens Docker

Imagens publicadas pelo workflow `Release e GHCR`:

```text
ghcr.io/wkarts/argws-git-monitor-api
ghcr.io/wkarts/argws-git-monitor-web
```

Tags produzidas para esta versão:

```text
latest
sha-<commit>
0.2.2
0.2
```

Exemplo de pull versionado:

```bash
docker pull ghcr.io/wkarts/argws-git-monitor-api:0.2.2
docker pull ghcr.io/wkarts/argws-git-monitor-web:0.2.2
```

Pacotes GHCR privados exigem autenticação antes do pull:

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u wkarts --password-stdin
```

## Primeiro acesso e GitHub

1. Entre com as credenciais geradas no pacote.
2. Troque a senha administrativa.
3. Abra **Configurações > Nova conexão**.
4. Cadastre um token fine-grained do GitHub.
5. Importe todos os repositórios autorizados ou selecione-os manualmente.

Permissões recomendadas:

| Permissão de repositório | Somente monitorar | Operar Actions/webhooks |
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
| `web` | Vue 3 PWA servida por Nginx e proxy reverso da API |
| `api` | FastAPI e OpenAPI |
| `worker` | Celery para sincronizações e processamento assíncrono |
| `beat` | Agendador periódico do Celery |
| `migrate` | Alembic e bootstrap idempotente |
| `postgres` | Persistência principal |
| `redis` | Resultados e cache operacional |
| `rabbitmq` | Broker das filas |

Portas locais:

- Aplicação: `8080`.
- RabbitMQ Management: `127.0.0.1:15672`.
- PostgreSQL, Redis e AMQP não são publicados no host.

## Comandos operacionais

```bash
./scripts/start.sh
./scripts/stop.sh
./scripts/status.sh
./scripts/logs.sh
./scripts/backup.sh
./scripts/restore.sh backups/arquivo.dump
./scripts/update.sh
```

Atalhos adicionais:

```bash
make validate
make validate-deploys
make deploy-ghcr
make deploy-local
make deploy-dockge
```

## CI/CD e versionamento

A versão deve permanecer idêntica em:

```text
VERSION
backend/pyproject.toml
frontend/package.json
```

Ao receber um push na `main`, o workflow:

1. valida backend, frontend, pacote e todos os diretórios de deploy;
2. valida os arquivos Compose de Docker, Dockge, Portainer e CloudPanel;
3. constrói as imagens API e Web para `linux/amd64` e `linux/arm64`;
4. publica e inspeciona os manifests no GHCR;
5. atualiza as tags `latest` e `sha-*`;
6. quando a tag Git da versão ainda não existe, cria `v<versão>`;
7. publica a GitHub Release com ZIP, TAR.GZ e `SHA256SUMS.txt`.

Versão atual: **0.2.2**. Git tag da release: **v0.2.2**. A tag da imagem Docker é **0.2.2**, sem o prefixo `v`.

Atualizações automáticas de versão do Dependabot permanecem desativadas para impedir a abertura massiva de PRs.

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
- `RELATORIO_VALIDACAO.md`

## Desenvolvimento

```bash
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
```

Backend:

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
```

Frontend:

```bash
cd frontend
npm install
npm run dev
npm run build
```

Validação completa:

```bash
python scripts/validate-package.py
python scripts/validate-deploy-layout.py
node scripts/validate-frontend.cjs
cd backend && pytest --cov=app --cov-fail-under=40
```

## Licença

Software de uso autorizado. Consulte `LICENSE`.
