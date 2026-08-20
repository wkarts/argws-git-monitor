# Integração GitHub

## Token fine-grained

Crie o token em `Settings > Developer settings > Personal access tokens > Fine-grained tokens`.

Configuração recomendada:

- Resource owner: sua conta ou organização.
- Repository access: todos ou repositórios selecionados.
- Expiration: período compatível com sua política de segurança.
- Metadata: read-only.
- Contents: read-only.
- Actions: read-only para monitorar; read/write para reexecutar e cancelar.
- Pull requests: read-only.
- Issues: read-only.
- Webhooks: read/write apenas quando usar atualização por webhook.

O monitor valida o token antes de persistir. Tokens expirados ou revogados deixam a conexão no estado `error` e exibem a mensagem retornada pelo GitHub.

## Sincronização

A sincronização periódica ocorre pelo Celery Beat. Também pode ser iniciada por conexão ou repositório na interface.

Para conservar limite de API:

- a lista de repositórios é paginada;
- a sincronização para quando o saldo fica abaixo do limite de segurança;
- cada projeto mantém somente janelas operacionais recentes;
- o saldo e horário de redefinição ficam visíveis nas configurações.

## Webhooks

Endpoint:

```text
POST /api/v1/webhooks/github
```

Eventos registrados:

- `push`
- `pull_request`
- `workflow_run`
- `release`
- `issues`

A API valida `X-Hub-Signature-256`, usa `X-GitHub-Delivery` para idempotência e enfileira apenas repositórios monitorados.

A URL pública precisa usar HTTPS válido. Em localhost, mantenha a sincronização periódica; não pressione **Configurar webhooks** até publicar um domínio acessível pelo GitHub.

## GitHub Enterprise

A tela permite alterar `api_url`. Informe a raiz REST da sua instalação, por exemplo `https://github.empresa.com/api/v3`, e garanta conectividade e certificado confiável no container da API.
