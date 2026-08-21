# Validação de armazenamento relativo — ARGWS Git Monitor v0.2.3

## Objetivo

Garantir que todos os dados persistentes da aplicação sejam armazenados dentro do diretório físico da própria stack, utilizando fontes de bind mount iniciadas por `./`.

## Contrato obrigatório

Cada Compose de produção deve conter exatamente:

```yaml
postgres:
  volumes:
    - ./data-postgres:/var/lib/postgresql/data

redis:
  volumes:
    - ./data-redis:/data

rabbitmq:
  volumes:
    - ./data-rabbitmq:/var/lib/rabbitmq
```

Não são aceitos para esses serviços:

- volumes Docker nomeados;
- caminhos absolutos do host;
- fontes relativas que não comecem com `./`;
- armazenamento compartilhado fora do diretório da stack.

## Arquivos validados

```text
compose.yaml
compose.dockge.yaml
deploy/docker/compose.ghcr.yaml
deploy/docker/compose.local.yaml
deploy/dockge/compose.yaml
deploy/portainer/compose.yaml
deploy/cloudpanel/dockge/compose.yaml
```

O ambiente de desenvolvimento também não usa volume nomeado para `node_modules`:

```yaml
- ./data-frontend-node-modules:/app/node_modules
```

## Estrutura física esperada

```text
pasta-da-stack/
├── compose.yaml
├── .env
├── data-postgres/
├── data-redis/
└── data-rabbitmq/
```

Os scripts de geração e implantação criam automaticamente essas pastas antes de iniciar os containers.

## Migração das versões anteriores

O arquivo `deploy/migrate-named-volumes.sh` copia os volumes nomeados antigos para as novas pastas relativas.

Proteções implementadas:

- não copia enquanto um container estiver usando o volume antigo;
- não sobrescreve uma pasta de destino que já contenha dados;
- monta o volume antigo como somente leitura;
- preserva os volumes antigos depois da cópia;
- não executa `docker volume rm`.

Comando:

```bash
docker compose down
bash deploy/migrate-named-volumes.sh --stack-dir /caminho/da/stack
```

## Validação automatizada

```bash
python scripts/validate-deploy-layout.py
```

O validador rejeita:

- ausência de qualquer serviço obrigatório;
- ausência dos três bind mounts esperados;
- fonte diferente de `./data-postgres`, `./data-redis` ou `./data-rabbitmq`;
- caminho absoluto;
- bloco superior de volumes nomeados;
- volume nomeado no Compose de desenvolvimento;
- migrador que tente apagar automaticamente os volumes antigos;
- divergência da versão 0.2.3 nos ambientes.

## Critérios de aceite

- [x] PostgreSQL dentro do diretório da stack;
- [x] Redis dentro do diretório da stack;
- [x] RabbitMQ dentro do diretório da stack;
- [x] fontes iniciadas por `./`;
- [x] nenhum caminho absoluto do host;
- [x] nenhum volume nomeado para dados persistentes;
- [x] geradores criam as pastas automaticamente;
- [x] migração segura disponível;
- [x] documentação de backup e remoção corrigida;
- [x] CI apta a bloquear regressões.
