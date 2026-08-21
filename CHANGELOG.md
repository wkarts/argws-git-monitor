# Changelog

## 0.3.0 — 2026-08-21

- reformula o tema claro com contraste, tipografia, bordas, campos e estados visuais mais legíveis e passa a utilizá-lo como padrão inicial;
- corrige o fluxo de conexão GitHub para descobrir e persistir imediatamente o catálogo de repositórios;
- redefine “importar” como “monitorar”: o repositório aparece no monitor imediatamente e apenas o enriquecimento detalhado continua assíncrono;
- adiciona Fila operacional visível com histórico persistente, progresso, erros, estados e cancelamento;
- adiciona criação de repositórios diretamente pelo Git Monitor;
- adiciona alteração de visibilidade público/privado;
- separa “parar monitoramento” de “excluir definitivamente no GitHub”, com confirmação forte para exclusões;
- mantém reexecução/cancelamento de Actions e configuração de webhooks conforme as permissões do token;
- adiciona autenticação em duas etapas TOTP com QR Code e códigos de recuperação;
- adiciona gestão e revogação de sessões;
- adiciona painel administrativo responsivo de usuários, privilégios, sessões, 2FA, redefinição de senha e exclusão;
- adiciona menu Fila e menu Usuários para administradores;
- remove da interface de login a orientação textual referente ao arquivo de credenciais iniciais;
- adiciona migration idempotente para instalações existentes e bancos novos;
- inclui testes do mecanismo TOTP e mantém validação completa do backend, frontend, Docker e deploys;
- atualiza a série de imagens e pacotes de release para 0.3.0 preservando os bind mounts relativos `./data-*`.

## 0.2.3 — 2026-08-20

- substitui volumes Docker nomeados por bind mounts relativos em todas as stacks de produção;
- persiste PostgreSQL em `./data-postgres:/var/lib/postgresql/data`;
- persiste Redis em `./data-redis:/data`;
- persiste RabbitMQ em `./data-rabbitmq:/var/lib/rabbitmq`;
- remove os blocos superiores de volumes nomeados dos arquivos Compose;
- garante que CloudPanel + Dockge, Dockge, Portainer, Docker GHCR, Docker local e os Composes de compatibilidade da raiz usem armazenamento dentro do diretório da própria stack;
- atualiza geradores, instaladores e scripts de deploy para criar automaticamente as pastas `data-*`;
- adiciona validação que rejeita caminhos absolutos, volumes nomeados e fontes sem o prefixo `./`;
- adiciona migração segura dos volumes nomeados das versões anteriores, preservando os volumes originais para rollback;
- interrompe atualizações automáticas quando encontra volumes antigos ainda não migrados, evitando iniciar uma base vazia;
- adiciona as pastas persistentes ao `.gitignore` e atualiza a documentação operacional;
- sincroniza a versão 0.2.3 no backend, frontend, imagens, ambientes e stacks.

## 0.2.2 — 2026-08-20

- cria o diretório canônico `deploy/` com pacotes separados para CloudPanel, Dockge, Portainer e Docker Compose;
- inclui integração completa CloudPanel + Dockge, com stack vinculada a `127.0.0.1` e snippet Nginx para reverse proxy HTTPS;
- inclui stack autônoma para Dockge, com `compose.yaml`, ambiente, gerador de segredos e script de deploy;
- inclui stack específica para Portainer, sem dependência de `env_file`, com modelo e gerador de variáveis do painel;
- inclui implantação Docker por imagens GHCR e por build local, em arquivos independentes;
- adiciona validação automatizada da estrutura, serviços, imagens, builds, bind local do CloudPanel e configuração do Portainer;
- sincroniza a versão 0.2.2 no backend, frontend, Dockerfiles, ambientes, composes e documentação;
- mantém os arquivos da raiz por compatibilidade, passando a considerar `deploy/` como local oficial dos pacotes de implantação.

## 0.2.1 — 2026-08-20

- corrige o fluxo pós-merge para gerar automaticamente a GitHub Release quando a versão declarada ainda não possui tag;
- publica imagens Docker separadas para API e Web no GHCR, com tags `latest`, `sha-*`, `0.2.1` e `0.2`;
- adiciona build multi-arquitetura para `linux/amd64` e `linux/arm64`;
- adiciona inspeção obrigatória dos manifests GHCR antes da publicação da release;
- inclui ZIP, TAR.GZ e `SHA256SUMS.txt` como artefatos permanentes da GitHub Release;
- inclui `compose.dockge.yaml` autônomo para Dockge e Portainer, sem necessidade de build local;
- torna os instaladores Windows e Linux orientados ao GHCR, com fallback automático para build local;
- corrige a documentação das tags Docker, que não utilizam o prefixo `v`;
- moderniza o CodeQL e as GitHub Actions para versões compatíveis com Node.js 24;
- encerra os Pull Requests automáticos abertos pelo Dependabot e desativa novos PRs automáticos de atualização de versão;
- preserva atualização de dependências como manutenção controlada e validada pela CI.

## 0.2.0 — 2026-08-20

- dashboard reconstruído para reproduzir o contrato visual aprovado, com métricas, saúde segmentada, atividades recentes e tabela compacta de repositórios;
- navegação desktop completa para Dashboard, Repositórios, Pull Requests, Actions, Releases, Issues, Alertas e Configurações;
- experiência mobile-first com navegação inferior, painel “Mais”, lista de projetos e alerta crítico de build;
- cabeçalho com usuário, contador de notificações e acesso ao GitHub;
- páginas operacionais agregadas para Actions, PRs, Releases e Issues;
- endpoints protegidos `/api/v1/operations/*` com escopo por usuário, filtros e paginação;
- ações reais para cancelar e reexecutar workflows preservadas na nova interface;
- nova identidade visual, componentes de métricas, donut de saúde e paginação reutilizável;
- documentação, prévias visuais e validações atualizadas.

## 0.1.0 — 2026-08-20

### Entregue

- API FastAPI com autenticação, refresh rotativo e senha Argon2.
- Integração GitHub REST para repositórios, commits, branches, Actions, PRs e releases.
- Token GitHub criptografado com Fernet.
- Sincronização assíncrona e periódica via Celery, RabbitMQ e Redis.
- Webhooks assinados e idempotentes.
- Dashboard, saúde, alertas, filtros e operação de Actions.
- PWA Vue 3/TypeScript mobile-first.
- Docker Compose completo, migrations e bootstrap idempotente.
- Scripts Windows/Linux, backup, restauração e publicação no GitHub.
- CI, release GHCR, CodeQL e Dependabot.
