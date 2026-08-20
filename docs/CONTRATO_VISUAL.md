# Contrato visual — ARGWS Git Monitor v0.2.0

## Objetivo

A interface da versão 0.2.0 deve reproduzir, dentro das limitações naturais de cada largura de tela, a composição aprovada para o ARGWS Git Monitor. Este documento transforma a referência visual em critérios verificáveis de implementação e evita que o dashboard volte ao formato reduzido da versão 0.1.0.

## Evidências de referência

### Desktop — 1440 × 900

![Dashboard desktop](previews/argws-git-monitor-dashboard-desktop-v0.2.0.png)

### Mobile — 390 × 844

![Dashboard mobile](previews/argws-git-monitor-dashboard-mobile-v0.2.0.png)

O arquivo `previews/dashboard-visual-contract.html` é um fixture determinístico, sem recursos externos, usado para validar o comportamento responsivo e gerar as evidências acima.

## Composição obrigatória no desktop

- sidebar com identidade ARGWS Git Monitor e oito destinos: Dashboard, Repositórios, Pull Requests, Actions, Releases, Issues, Alertas e Configurações;
- item ativo com destaque azul/roxo;
- cartão inferior de monitoramento 24/7;
- topbar com contexto da página, acesso ao GitHub, contador de alertas e usuário autenticado;
- quatro indicadores: total monitorado, saudável, executando e falhando;
- painel de saúde com donut segmentado e percentuais por estado;
- painel de atividades recentes;
- tabela compacta de repositórios, busca, status, CI, última atividade, branch e acesso ao GitHub.

## Composição obrigatória no mobile

- cabeçalho compacto com menu, título e contador de alertas;
- cartão de saúde geral;
- lista compacta de repositórios com estado;
- cartão crítico para a falha mais recente;
- navegação inferior com Início, Repos, Actions, Alertas e Mais;
- painel “Mais” contendo Pull Requests, Releases, Issues, Configurações e saída;
- nenhum iframe ou simples redução da tela desktop.

## Rotas funcionais

| Destino | Rota Vue | Endpoint principal |
|---|---|---|
| Dashboard | `/` | `GET /api/v1/dashboard` |
| Repositórios | `/repositories` | `GET /api/v1/repositories` |
| Pull Requests | `/pull-requests` | `GET /api/v1/operations/pull-requests` |
| Actions | `/actions` | `GET /api/v1/operations/actions` |
| Releases | `/releases` | `GET /api/v1/operations/releases` |
| Issues | `/issues` | `GET /api/v1/operations/issues` |
| Alertas | `/notifications` | `GET /api/v1/notifications` |
| Configurações | `/settings` | `GET /api/v1/github/connections` |

As operações de workflow continuam usando endpoints reais para cancelar, reexecutar tudo ou reexecutar apenas jobs que falharam.

## Componentes de implementação

- `frontend/src/layouts/AppShell.vue`: sidebar, topbar, navegação móvel e painéis de usuário;
- `frontend/src/views/DashboardView.vue`: dashboard desktop/mobile;
- `frontend/src/views/ActionsView.vue`: consulta e operação de workflows;
- `frontend/src/views/PullRequestsView.vue`: consulta agregada de PRs;
- `frontend/src/views/ReleasesView.vue`: consulta agregada de releases;
- `frontend/src/views/IssuesView.vue`: resumo de issues por repositório;
- `frontend/src/components/OverviewMetricCard.vue`: indicadores superiores;
- `frontend/src/components/HealthDonut.vue`: gráfico segmentado;
- `frontend/src/assets/operations.css`: padrão compartilhado das páginas operacionais;
- `backend/app/api/routes/operations.py`: endpoints agregados com escopo por usuário.

## Larguras de aceitação

| Largura | Comportamento esperado |
|---:|---|
| 360 px | dashboard móvel sem rolagem horizontal e navegação inferior disponível |
| 390 px | composição móvel equivalente à evidência oficial |
| 768 px | transição para layout compacto, mantendo comandos acessíveis |
| 1366 px | dashboard desktop completo, tabela sem perda de colunas essenciais |
| 1920 px | conteúdo centralizado e expansível, sem esticar excessivamente tipografia ou cards |

## Critérios de não regressão

A validação do pacote falha quando qualquer rota operacional, item principal do menu, componente visual central ou evidência de referência é removido. O CI também executa análise TypeScript/Vue e build do frontend antes de publicar imagens Docker ou release.
