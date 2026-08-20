# ARGWS Git Monitor

Central operacional **mobile-first** para monitorar repositórios públicos e privados do GitHub em uma única PWA. O pacote inclui API, frontend, workers, banco de dados, filas, migrations, autenticação, Docker, CI/CD, backup e documentação.

## Recursos entregues

- Dashboard operacional no padrão visual aprovado, com quatro indicadores, saúde segmentada, atividades recentes e tabela compacta.
- Navegação própria para Repositórios, Pull Requests, Actions, Releases, Issues, Alertas e Configurações.
- Experiência mobile-first com navegação inferior, painel “Mais” e alerta crítico de build.
- Repositórios públicos e privados por token GitHub granular.
- Último commit, branch principal, branches, issues, pull requests, releases e Actions.
- Histórico de até 30 execuções, 100 PRs e 20 releases por repositório.
- Reexecução completa, reexecução somente de jobs com falha e cancelamento de workflow.
- Sincronização automática a cada 10 minutos e sincronização manual.
- Webhooks opcionais para atualização praticamente imediata.
- Alertas de falha, recuperação e nova release.
- PWA instalável em celular, tablet e desktop.
- Interface responsiva, tema claro/escuro e funcionamento visual offline.
- Token GitHub criptografado no PostgreSQL; nunca devolvido ao navegador.
- JWT de curta duração e refresh token rotativo/revogável.
- Senha Argon2 e troca obrigatória no primeiro acesso.
- Logs estruturados, health checks e métricas Prometheus.
- Dados demonstrativos removidos automaticamente após conectar uma conta real.

## Interface v0.2.0

A versão 0.2.0 transforma o prelúdio visual aprovado em contrato de implementação do frontend.

![Dashboard desktop](docs/previews/argws-git-monitor-dashboard-desktop-v0.2.0.png)

![Dashboard mobile](docs/previews/argws-git-monitor-dashboard-mobile-v0.2.0.png)

Os critérios, rotas, componentes e larguras de aceitação estão documentados em `docs/CONTRATO_VISUAL.md`.

## Instalação direta

### Windows

1. Extraia o ZIP.
2. Abra o Docker Desktop.
3. Dê duplo clique em `INSTALAR_WINDOWS.bat`.
4. Acesse `http://localhost:8080`.
5. Abra `CREDENCIAIS_INICIAIS.txt` para consultar o primeiro acesso.

### Linux

```bash
chmod +x INSTALAR_LINUX.sh
./INSTALAR_LINUX.sh
```

### Docker Compose manual

```bash
docker compose up -d --build
```

A instalação aplica migrations, cria o administrador, inicia workers e valida a prontidão da stack. Quando `.env` não existe, os instaladores geram segredos criptograficamente aleatórios sem exigir Node.js ou dependências Python no host.

## Primeiro acesso e GitHub

1. Entre com as credenciais geradas no pacote.
2. Troque a senha administrativa.
3. Abra **Configurações > Nova conexão**.
4. Cole um token fine-grained do GitHub.
5. Mantenha **Importar automaticamente** habilitado ou escolha os repositórios manualmente.

Permissões recomendadas do token:

| Permissão de repositório | Somente monitorar | Operar Actions/webhooks |
|---|---:|---:|
| Metadata | leitura | leitura |
| Contents | leitura | leitura |
| Actions | leitura | escrita |
| Pull requests | leitura | leitura |
| Issues | leitura | leitura |
| Webhooks | nenhuma | escrita |

Selecione `All repositories` ou apenas os repositórios desejados. Organizações podem exigir aprovação do administrador.

## Serviços Docker

| Serviço | Papel |
|---|---|
| `web` | Vue 3 PWA servida por Nginx e proxy reverso da API |
| `api` | FastAPI e OpenAPI |
| `worker` | Celery para sincronizações e processamento assíncrono |
| `beat` | Agendador periódico do Celery |
| `migrate` | Alembic e bootstrap idempotente |
| `postgres` | Persistência principal |
| `redis` | Resultados/cache operacional |
| `rabbitmq` | Broker das filas |

Portas locais:

- Aplicação: `8080`
- RabbitMQ Management, apenas em localhost: `15672`
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

Equivalentes resumidos:

```bash
docker compose ps
docker compose logs -f --tail=200
docker compose restart api worker beat web
```

## Publicação no GitHub

O pacote não publica `.env`, credenciais, dumps ou caches. Com GitHub CLI autenticado:

```bash
./scripts/publish-github.sh wkarts/argws-git-monitor private
```

No Windows, execute `PUBLICAR_GITHUB.bat`. O script cria o repositório privado quando ele ainda não existe, inicializa o Git, cria o primeiro commit e envia a branch `main`.

## Produção com domínio

```bash
./scripts/configure-domain.sh https://git.seu-dominio.com.br
```

Depois, aponte o proxy HTTPS para `http://127.0.0.1:8080`. Para webhooks automáticos, `PUBLIC_BASE_URL` precisa ser uma URL HTTPS pública; sem isso, a sincronização periódica continua funcionando normalmente.

Consulte:

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

Validação completa do pacote:

```bash
python scripts/validate-package.py
node scripts/validate-frontend.cjs
cd backend && pytest --cov=app --cov-fail-under=40
```

## Versionamento

Versão atual: **0.2.0**. Tags `v*.*.*` acionam build e publicação das imagens no GHCR:

- `ghcr.io/wkarts/argws-git-monitor-api`
- `ghcr.io/wkarts/argws-git-monitor-web`

## Licença

Software de uso autorizado. Consulte `LICENSE`.
