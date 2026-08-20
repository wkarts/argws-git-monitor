# Política de segurança

## Dados sensíveis

- Nunca faça commit de `.env`, `CREDENCIAIS_INICIAIS.txt`, tokens, chaves privadas ou backups.
- O token GitHub é criptografado antes de persistir.
- A chave `ENCRYPTION_KEY` deve permanecer estável; sua perda impede descriptografar tokens existentes.
- Troque a senha inicial no primeiro acesso.
- Use HTTPS e proxy confiável em produção.

## Comunicação de vulnerabilidade

Não publique segredos ou vulnerabilidades exploráveis em issues públicas. Comunique ao responsável técnico do ambiente e revogue imediatamente qualquer token exposto.

## Rotação

Para trocar o token GitHub, remova a conexão na interface e crie uma nova. Para trocar segredos da aplicação, faça backup, atualize `.env` e reinicie os serviços. Não altere `ENCRYPTION_KEY` enquanto existirem conexões que precisem ser preservadas.
