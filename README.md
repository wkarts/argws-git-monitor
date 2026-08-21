# ARGWS Git Monitor

Central operacional **mobile-first** para monitorar e administrar repositórios públicos e privados do GitHub em uma única PWA. A versão 0.3.0 evolui o projeto de um painel de consulta para uma ferramenta operacional com catálogo imediato, fila visível, gestão de repositórios, 2FA e administração de usuários.

## Recursos principais

- Dashboard consolidado de saúde, Actions, Pull Requests, releases, issues e alertas.
- Catálogo de repositórios públicos e privados com descoberta imediata após conexão/sincronização.
- Monitoramento selecionável por projeto ou automático para todos os repositórios acessíveis.
- Fila operacional persistente e visível com estados `queued`, `running`, `success`, `failed` e `cancelled`.
- Sincronização manual, automática e por webhook.
- Criação de repositório diretamente pelo Git Monitor.
- Alteração de visibilidade público/privado pelo backend.
- Remoção somente do monitor sem tocar no GitHub.
- Exclusão definitiva no GitHub mediante confirmação exata do `owner/repo`.
- Reexecução e cancelamento de GitHub Actions conforme as permissões do token.
- Autenticação em duas etapas TOTP com QR Code e códigos de recuperação.
- Gestão de sessões e revogação de acessos.
- Painel administrativo responsivo de usuários, administradores, sessões e 2FA.
- Tema claro de alto contraste como padrão inicial, mantendo tema escuro e automático.
- PWA instalável e responsiva para desktop, tablet e celular.
- Token GitHub criptografado no PostgreSQL e nunca retornado ao navegador.
- JWT, refresh rotativo, Argon2, logs estruturados, health checks e métricas.
- Docker Compose com deploy separado para CloudPanel, Dockge, Portainer, GHCR e build local.

## Fluxo GitHub

A partir da versão 0.3.0, importar/monitorar um repositório não depende mais da conclusão de uma fila invisível:

```text
GitHub token
   │
   ▼
Descoberta imediata do catálogo
   │
   ├── repositório já aparece em Repositórios
   │
   └── sincronização detalhada vai para a Fila
             │
             ├── commits
             ├── branches
             ├── Actions
             ├── Pull Requests
             ├── releases
             └── saúde operacional
```

A fila pode ser acompanhada em **Fila** no menu principal.

## Permissões GitHub

Para monitorar, permissões de leitura são suficientes. Operações administrativas dependem das permissões efetivamente concedidas ao token.

| Recurso | Monitoramento | Operação |
|---|---:|---:|
| Metadata | leitura | leitura |
| Contents | leitura | leitura |
| Actions | leitura | escrita para reexecutar/cancelar |
| Pull requests | leitura | leitura |
| Issues | leitura | leitura |
| Webhooks | nenhuma | escrita |
| Administration | nenhuma | escrita para criar/configurar/alterar repositórios |

Para exclusão definitiva, o token também precisa permitir exclusão de repositório conforme o tipo de credencial e as regras da conta/organização.

## Segurança local

A plataforma oferece:

- senha Argon2;
- JWT de curta duração;
- refresh token rotativo e revogável;
- sessões listáveis e revogáveis;
- TOTP/2FA;
- códigos de recuperação armazenados somente como hash;
- token GitHub criptografado com Fernet;
- trilha de auditoria;
- confirmação reforçada para exclusão de repositório.

As credenciais administrativas iniciais são geradas durante a instalação e a senha deve ser substituída no primeiro acesso.

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

Dados persistentes usam **bind mounts relativos ao diretório físico do Compose**:

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

Estrutura física:

```text
pasta-da-stack/
├── compose.yaml
├── .env
├── data-postgres/
├── data-redis/
└── data-rabbitmq/
```

Os geradores e scripts de deploy criam essas pastas automaticamente. `docker compose down` não remove os diretórios `data-*`.

### Migração de instalações anteriores

Para instalações antigas que ainda usam volumes Docker nomeados:

```bash
docker compose down
bash deploy/migrate-named-volumes.sh --stack-dir /caminho/da/stack
```

O migrador copia os dados para `./data-*`, recusa sobrescrever diretórios não vazios e preserva os volumes antigos para rollback.

## Instalação

### Windows

1. Extraia a GitHub Release.
2. Abra o Docker Desktop.
3. Execute `INSTALAR_WINDOWS.bat`.
4. Acesse `http://localhost:8080`.
5. Troque a senha administrativa no primeiro acesso.

### Linux

```bash
chmod +x INSTALAR_LINUX.sh
./INSTALAR_LINUX.sh
```

### Docker por GHCR

```bash
cd deploy/docker
bash generate-env.sh
bash deploy-ghcr.sh
```

### Docker com build local

```bash
cd deploy/docker
bash generate-env.sh
bash deploy-local.sh
```

### Dockge

```bash
cd deploy/dockge
bash generate-env.sh --url https://git.seu-dominio.com.br --bind 127.0.0.1
bash deploy.sh
```

### CloudPanel + Dockge

```bash
cd deploy/cloudpanel/dockge
bash generate-env.sh --url https://git.seu-dominio.com.br
bash deploy.sh
```

Use o reverse proxy disponível em:

```text
deploy/cloudpanel/nginx/argws-git-monitor.conf
```

### Portainer

```bash
cd deploy/portainer
bash generate-stack-env.sh --url https://git.seu-dominio.com.br --bind 127.0.0.1
```

Importe `stack.env` em **Environment variables**.

## Imagens Docker

```text
ghcr.io/wkarts/argws-git-monitor-api:0.3.0
ghcr.io/wkarts/argws-git-monitor-web:0.3.0
```

Também são publicadas:

```text
latest
sha-<commit>
0.3.0
0.3
```

## Serviços

| Serviço | Papel |
|---|---|
| `web` | Vue 3 PWA e Nginx |
| `api` | FastAPI/OpenAPI |
| `worker` | Celery |
| `beat` | Agendador Celery |
| `migrate` | Alembic e bootstrap |
| `postgres` | Persistência principal |
| `redis` | Cache e resultados |
| `rabbitmq` | Broker da fila |

Portas padrão:

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

## CI/CD

A versão deve coincidir em:

```text
VERSION
backend/pyproject.toml
frontend/package.json
```

O pipeline valida backend, frontend, migrations, deploys e Composes; constrói API/Web para `linux/amd64` e `linux/arm64`; publica no GHCR; inspeciona os manifests; e cria a GitHub Release.

Versão atual: **0.3.0**. Git tag esperada após merge: **v0.3.0**. Tag Docker: **0.3.0**.

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

## Licença

Software de uso autorizado. Consulte `LICENSE`.
