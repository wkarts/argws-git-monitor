# Relatório de Validação — ARGWS Git Monitor v0.2.0

**Data da validação:** 20 de agosto de 2026  
**Modalidade:** aplicação Docker completa, PWA mobile-first, contrato visual v0.2.0 e código-fonte publicável no GitHub

## Resultado executivo

A versão **0.2.0** substitui o dashboard simplificado da versão anterior pela composição visual aprovada para o ARGWS Git Monitor. O contrato visual deixou de ser apenas uma arte conceitual e passou a estar implementado nos componentes Vue, rotas, páginas operacionais e estilos responsivos da aplicação.

A entrega contém backend FastAPI, frontend Vue 3/TypeScript, PWA, PostgreSQL, Redis, RabbitMQ, Celery Worker, Celery Beat, migrations Alembic, Nginx, Docker Compose, scripts de instalação/operação, CI/CD, segurança, documentação e dados demonstrativos iniciais.

Nenhum ajuste de código é necessário para iniciar a aplicação. Permanecem apenas configurações externas inevitáveis:

1. Informar, pela própria interface, uma credencial autorizada da conta GitHub para consultar repositórios privados e executar operações permitidas.
2. Configurar domínio e HTTPS quando forem necessários acesso externo e recebimento público de webhooks.

## Contrato visual implementado

A interface v0.2.0 passou a incluir:

- menu desktop completo com Dashboard, Repositórios, Pull Requests, Actions, Releases, Issues, Alertas e Configurações;
- cabeçalho com acesso ao GitHub, indicador de notificações, avatar e menu do usuário;
- cartão lateral de monitoramento 24/7 com indicador de conexão e sparkline;
- quatro indicadores de repositórios monitorados, saudáveis, em execução e com falha;
- painel segmentado de saúde geral;
- atividades recentes de CI/CD, notificações e releases;
- tabela compacta de repositórios no desktop;
- lista otimizada de repositórios no mobile;
- cartão crítico de falha de build no mobile;
- navegação inferior mobile com cinco posições;
- páginas operacionais próprias para Actions, Pull Requests, Releases e Issues;
- tema escuro premium e responsividade específica para desktop, tablet e celular.

O detalhamento de componentes, rotas, breakpoints e critérios de não regressão está em `docs/CONTRATO_VISUAL.md`.

## Evidências visuais

Foram produzidas evidências determinísticas do contrato visual nas dimensões-alvo:

| Evidência | Dimensão | Resultado |
|---|---:|---:|
| Dashboard desktop | **1440 × 900 px** | **Aprovado** |
| Dashboard mobile | **390 × 844 px** | **Aprovado** |

Arquivos incluídos no projeto:

```text
docs/previews/argws-git-monitor-dashboard-desktop-v0.2.0.png
docs/previews/argws-git-monitor-dashboard-mobile-v0.2.0.png
docs/previews/dashboard-visual-contract.html
```

As imagens são renderizações reproduzíveis da especificação visual usada como contrato de interface. Elas não são apresentadas como capturas do bundle Vue compilado neste ambiente, pois o acesso ao registro npm esteve indisponível durante a produção do pacote.

## Validações executadas

| Área | Resultado |
|---|---:|
| Testes automatizados do backend | **22 aprovados** |
| Cobertura automatizada do backend | **45,37%** |
| Limite mínimo de cobertura | **40% atingido** |
| Compilação sintática Python | **Aprovada** |
| Scripts Vue/TypeScript analisados | **35 aprovados** |
| Arquivos Vue encontrados | **24** |
| Módulos TypeScript encontrados | **12** |
| Imports utilizados nos componentes Vue | **Aprovado** |
| Arquivos estruturais obrigatórios | **28 encontrados** |
| YAML de Compose e GitHub Actions | **7 aprovados** |
| JSON/configurações | **3 aprovados** |
| Estrutura Docker esperada | **8 serviços encontrados** |
| Segredos gerados | **Formato e comprimento aprovados** |
| Chave Fernet | **32 bytes/base64 URL-safe aprovada** |
| Dimensões dos ícones PWA | **Aprovadas** |
| Scripts Bash | **14 aprovados** |
| Proteção do Git | **Segredos, backups e dependências ignorados** |
| Busca por token GitHub embutido | **Nenhum encontrado** |
| Correspondência `.env`/credenciais | **Aprovada** |
| Contrato visual v0.2.0 | **Rotas, menu, dashboard e evidências aprovados** |
| Documentos operacionais | **8 presentes** |
| Validação integral do pacote completo | **15 grupos aprovados, 0 avisos, 0 erros** |

## Serviços entregues

- `web`: Vue 3, TypeScript, Vite PWA e Nginx.
- `api`: FastAPI, OpenAPI e autenticação.
- `worker`: processamento assíncrono Celery.
- `beat`: sincronização periódica e limpeza de notificações.
- `migrate`: migrations e bootstrap idempotente.
- `postgres`: persistência principal.
- `redis`: backend de resultados e coordenação operacional.
- `rabbitmq`: broker das filas.

PostgreSQL, Redis e AMQP permanecem isolados da rede do host. A publicação padrão expõe somente a aplicação web e restringe o painel de administração do RabbitMQ a `127.0.0.1`.

## Funcionalidades verificadas por código e testes

- senhas com Argon2;
- JWT de acesso com expiração;
- refresh token aleatório, armazenado somente como SHA-256, rotativo e revogável;
- criptografia Fernet das credenciais GitHub;
- assinatura HMAC SHA-256 de webhook;
- persistência de usuários, conexões, repositórios, workflows, pull requests, releases, issues resumidas, notificações, auditoria e entregas de webhook;
- mapeamento defensivo das respostas do GitHub;
- paginação e captura de rate limit;
- cálculo de saúde para sucesso, execução, falha, inatividade, ausência de CI, sincronização com erro e repositório arquivado;
- dados demonstrativos idempotentes, removidos após a conexão de uma conta real;
- sincronização concorrente com limite configurável;
- reexecução de workflow, reexecução somente das falhas e cancelamento;
- consultas agregadas para Actions, Pull Requests, Releases e Issues;
- PWA instalável, atualização automática, tema claro/escuro e layout mobile-first;
- backup com checksum SHA-256 e restauração com reinicialização segura dos serviços.

## Instalação

### Windows

Execute:

```text
INSTALAR_WINDOWS.bat
```

O script valida Docker Desktop/Compose, gera segredos quando necessário, constrói os containers, aplica migrations, cria o administrador e consulta o endpoint de prontidão.

### Linux

```bash
chmod +x INSTALAR_LINUX.sh
./INSTALAR_LINUX.sh
```

### Docker Compose

```bash
docker compose up -d --build
```

As credenciais exclusivas do pacote completo ficam em `CREDENCIAIS_INICIAIS.txt`. Esse arquivo e o `.env` são excluídos do pacote destinado ao GitHub.

## Publicação segura no GitHub

A proteção do repositório exclui `.env`, `CREDENCIAIS_INICIAIS.txt`, dumps, backups, ambientes virtuais, caches, dependências e artefatos locais. O pacote-fonte pode ser publicado por:

```bash
./scripts/publish-github.sh wkarts/argws-git-monitor private
```

No Windows:

```text
PUBLICAR_GITHUB.bat
```

## Limite objetivo do ambiente de validação

O ambiente desta entrega não disponibilizou Docker Engine e não conseguiu acessar o registro npm. Portanto, nesta sessão não foi possível executar `docker compose up`, instalar as dependências externas do frontend nem produzir o bundle Vite real.

Foram executados e aprovados os testes Python, a cobertura, a compilação sintática do backend, a análise de 35 scripts Vue/TypeScript, os contratos de API, a estrutura Docker/Compose, as regras de segurança, os assets, os scripts operacionais, as evidências determinísticas do contrato visual e a integridade dos pacotes.

O workflow de CI incluído executa, em runner com rede, a instalação completa das dependências, `vue-tsc`, build Vite, testes e builds Docker. Na máquina de destino, a exigência operacional é Docker Desktop/Engine com Docker Compose e acesso HTTPS ao GitHub e aos registries de imagens/pacotes.
