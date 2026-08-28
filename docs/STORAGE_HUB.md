# Storage Hub — ARGWS Git Monitor

## Objetivo

O Storage Hub garante que o backup básico funcione sem exigir um provider externo previamente configurado.

A aplicação cria, por usuário, dois destinos gerenciados sobre o volume persistente já existente em `/data/backups`:

- **ARGWS · S3 interno**: object store interno em organização `bucket/key`, com bucket lógico `argws-backups`;
- **ARGWS · Local interno**: staging local persistente para recuperação e integração.

Esta implementação não adiciona nem altera manifests de deployment e não expõe um endpoint S3 público. O storage `internal_s3` é filesystem-backed e serve como object store primário interno do Git Monitor.

## Fluxo de backup

1. o usuário escolhe o repositório;
2. o Storage Hub garante os providers internos;
3. quando nenhum destino é informado, o `internal_s3` é selecionado;
4. o destino passa por teste de escrita/conexão antes de criar o job;
5. o worker gera mirror/bundle, manifesto e arquivos suportados;
6. o arquivo final recebe SHA-256;
7. o snapshot é armazenado e registrado no banco.

## Replicação externa

Um snapshot concluído pode ser copiado para:

- S3;
- MinIO/S3-compatible;
- Dropbox;
- Google Drive;
- SFTP.

Antes da cópia, o worker baixa o snapshot da origem e confere seu SHA-256. Somente depois envia o arquivo ao provider de destino e registra um novo snapshot com `replica_of` no manifesto.

## Dropbox e Google Drive

O fluxo recomendado usa credenciais OAuth duráveis:

- `refresh_token`;
- `client_id`;
- `client_secret`.

`access_token` isolado continua aceito para testes e cenários controlados.

A interface não exige mais edição manual de JSON para configurar providers.
