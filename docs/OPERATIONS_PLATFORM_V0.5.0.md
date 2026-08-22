# ARGWS Git Monitor v0.5.0 — Operations Platform

A v0.5.0 evolui o Git Monitor de observabilidade para operações de ciclo de vida de software sem substituir os módulos existentes.

## Princípios

- GitHub API centralizada; nenhuma regra operacional depende de scripts PowerShell.
- Múltiplas conexões GitHub por usuário.
- Secrets criptografados com a chave Fernet da instalação e nunca devolvidos integralmente pela API.
- Operações demoradas executadas pelo Celery com progresso por etapas reais.
- `:latest` continua sendo a tag utilizada pelos modelos de deploy da própria plataforma; a versão da aplicação é obtida do pacote.
- Backups locais persistem em `./data-backups` na pasta da stack.
- Nenhum Docker Socket é montado na API.
- Ações destrutivas exigem confirmação textual, auditoria e, no Deep Clean, Dry Run e backup quando aplicável.

## Backup & Recovery

Providers: Local, S3, MinIO, Google Drive, Dropbox e SFTP. O backup completo usa clone mirror + Git bundle, coleta tags, branches, releases/assets, Git LFS e submodules quando habilitados, gera manifesto e SHA-256 e só então envia o arquivo ao provider.

Políticas podem ser manuais, por intervalo, diárias, semanais, mensais ou por evento (`push`, `release`, `workflow_success`). Padrões como `release/*` são resolvidos contra branches existentes antes de gerar o bundle. A retenção respeita snapshots permanentes, quantidade e idade configuradas.

O Restore Center valida checksum e oferece simulação antes da execução. Operações destrutivas exigem confirmação explícita.

## Release, Publishing e Replicação

O Release Manager usa jobs reais para criar tag/release e publicar em canais configurados. A replicação possui proteção contra ciclos e suporta estratégias mirror, branch e distribuição de release/artefatos conforme o destino configurado.

## Deployments

Deployment Targets representam desenvolvimento, homologação, staging, produção ou servidores customizados. O acesso é por SSH com host key controlada. As estratégias atuais são Git, Release e Docker Compose. CloudPanel não recebe endpoints fictícios: quando não há API oficial adequada, a automação usa comandos remotos configurados pelo administrador.

Todo deployment registra estado anterior, pipeline, saída relevante, healthcheck e dados necessários ao rollback. Rollback Docker/Release é recusado se o target não possuir comando explícito seguro.

## Repository Clinic e Deep Clean

A Clinic gera score explicável e findings com severidade, evidência, risco e recomendação. Clinic e Cleanup compartilham o mesmo domínio de análise.

O Deep Clean segue obrigatoriamente:

`Analyze → Build Plan → Dry Run → Review → Backup → Confirm → Execute → Validate → Audit`

Candidatos são classificados em `SAFE`, `REVIEW` e `DESTRUCTIVE`. Checkpoints, default/protected branches, releases preservadas e referências de deployments são analisados antes do plano. O Dry Run revalida recursos e faz zero chamadas DELETE.

## GitHub Tools

O item lateral permanece único e internamente possui as guias:

- Repositórios
- Branches & Arquivos
- Releases & Actions
- GHCR
- Cleanup

O contexto de conexão/repositório é compartilhado entre as guias. Criação de repositório e bootstrap são online; o bootstrap apresenta preview/diff e nunca substitui arquivo silenciosamente.

## Auditoria

Ações administrativas e destrutivas entram no Audit Log. O `X-Request-ID` é propagado automaticamente como `correlation_id` para facilitar rastreamento entre API, logs e auditoria.
