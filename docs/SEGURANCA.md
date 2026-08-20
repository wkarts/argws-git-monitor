# Segurança

## Controles implementados

- Hash de senha Argon2.
- JWT de 30 minutos.
- Refresh token aleatório, armazenado somente como SHA-256, rotacionado a cada uso.
- Revogação de todas as sessões ao trocar senha.
- Token GitHub cifrado com Fernet.
- Comparação constante da assinatura de webhook.
- Entregas de webhook idempotentes.
- Segregação por usuário em todas as consultas de conexão/repositório.
- CORS configurável.
- Headers `nosniff`, `Referrer-Policy` e `Permissions-Policy`.
- Serviços de dados não publicados no host.
- RabbitMQ Management limitado a `127.0.0.1`.
- Containers com `no-new-privileges`.
- Imagens executadas com usuário não-root na API.
- Segredos excluídos do Git.

## Produção

1. Use HTTPS.
2. Restrinja a porta 8080 ao proxy reverso quando estiver no mesmo servidor (`APP_BIND_ADDRESS=127.0.0.1`).
3. Proteja e faça backup do `.env` separadamente.
4. Faça rotação do token GitHub antes de expirar.
5. Não publique a interface RabbitMQ na Internet.
6. Monitore `/api/v1/health/ready` e espaço do volume PostgreSQL.
7. Mantenha imagens e dependências atualizadas pelo Dependabot.

## Perda da chave de criptografia

Sem a mesma `ENCRYPTION_KEY`, tokens existentes não podem ser recuperados. A aplicação continua com os demais dados, mas as conexões GitHub devem ser removidas e recriadas.
