# Storage Hub — ARGWS Git Monitor

## Objetivo

O Storage Hub garante que o backup básico funcione sem exigir Dropbox, Google Drive ou outro provider externo previamente configurado.

A partir da correção da série 0.7.x, o Git Monitor mantém dois recursos internos distintos:

- **MinIO interno**: object storage S3 real, privado dentro da rede da stack e persistido em `./data-minio`;
- **ARGWS · Local interno**: staging/recovery local persistido em `./data-backups`.

O MinIO não é exposto publicamente pelo Compose. A aplicação acessa `http://minio:9000` pela rede interna e administra buckets através do próprio Storage Hub.

## Buckets internos

Cada usuário possui namespace próprio. Um bucket informado como `projetos` é materializado com prefixo interno derivado do UUID do usuário, por exemplo:

`argws-a1b2c3d4e5f6-projetos`

Isso evita colisão entre usuários sem expor credenciais do MinIO na interface.

O Storage Hub:

1. garante automaticamente um bucket principal `backups`;
2. permite criar buckets adicionais pela própria aplicação;
3. permite testar disponibilidade de cada bucket;
4. permite excluir apenas buckets adicionais vazios e sem snapshots/políticas vinculados;
5. protege o bucket principal contra exclusão acidental.

## Correção do schema de storage

Instalações anteriores podiam possuir `storage_providers.created_at` e `updated_at` como `NOT NULL` sem `server_default`. Isso fazia a criação automática do storage interno falhar com `created_at = NULL` e derrubava `/storage-hub/overview`.

A migration `0007_runtime_storage_repair` repara os defaults de timestamp das tabelas operacionais que usam `TimestampMixin`. Além disso, a criação dos providers internos fornece os timestamps explicitamente, de modo que o fluxo continue seguro durante a atualização.

## Carregamento resiliente da interface

A tela de Backup & Recovery não trata mais o Storage Hub como pré-condição para listar repositórios. Repositórios, conexões, políticas, snapshots e estado do storage são carregados independentemente.

Consequência: se o MinIO estiver temporariamente offline, a interface mostra **MinIO OFFLINE** e o erro específico, mas os repositórios continuam visíveis. Apenas operações que realmente dependem do object storage são bloqueadas.

## Fluxo de backup

1. o usuário escolhe o repositório;
2. a aplicação resolve ou cria o provider interno do bucket selecionado;
3. o bucket MinIO é validado/criado antes do job;
4. o worker é validado antes do enqueue;
5. o worker gera mirror/bundle, manifesto e arquivos suportados;
6. o arquivo final recebe SHA-256;
7. o snapshot é enviado ao MinIO ou ao provider escolhido;
8. localização, checksum, tamanho e manifesto ficam registrados no banco.

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

A interface usa formulários específicos por provider; JSON manual não faz parte do fluxo normal.

## Persistência e atualização

Os perfis Compose mantidos pelo projeto incluem:

- `./data-minio:/data` no serviço MinIO;
- `./data-backups:/data/backups` em API/worker para staging e recovery local.

A credencial interna usa `MINIO_INTERNAL_ACCESS_KEY` (default `argws-internal`) e, por compatibilidade com instalações existentes, o segredo do MinIO usa `APP_SECRET_KEY` quando não há configuração dedicada no backend.

Não existe console MinIO publicada para a Internet por padrão. O gerenciamento funcional de buckets deve ser feito pela própria aplicação.
