# ARGWS Git Monitor — healthcheck leve e espelhos GHCR

## Diagnóstico e intervenção

Na VPS com vários brokers, healthchecks do RabbitMQ executavam `rabbitmq-diagnostics -q ping` a cada 10 s. Uma chamada CLI inicia contexto Erlang e, repetida em vários containers, amplifica picos de CPU. O Git Monitor executava **6 consultas por minuto** mesmo ocioso. O novo teste realiza **1 abertura de porta TCP por minuto**, sem iniciar a CLI Erlang.

### Healthcheck aplicado em todos os sete Compose completos

```yaml
healthcheck:
  test: ["CMD", "bash", "-ec", "exec 3<>/dev/tcp/127.0.0.1/5672"]
  interval: 60s
  timeout: 3s
  retries: 5
  start_period: 90s
```

A imagem oficial `rabbitmq:4-management-alpine` contém Bash no entrypoint, portanto a checagem não pressupõe `nc`. A pipeline CI inicia um RabbitMQ descartável e executa o teste de porta dentro da imagem. Essa sondagem é apenas **readiness do listener AMQP**, não garante credenciais válidas, ausência de alarmes nem consumidores em funcionamento. Mantenha diagnóstico profundo e métricas de fila em monitoramento separado.

## Imagens sob a organização GHCR

O catálogo versionado `infra/images.json` é a fonte única da lista de dependências. O workflow reutilizável `.github/workflows/mirror-dependencies.yml` espelha as imagens multi-arquitetura usando Skopeo, com permissão `packages:write` e verificação posterior. **Não publica automaticamente nenhuma stack/serviço numa VPS**.

| Serviço/finalidade | Imagem GHCR |
|---|---|
| Inicialização de diretórios | `ghcr.io/wkarts/argws-git-monitor-alpine:3.21` |
| PostgreSQL | `ghcr.io/wkarts/argws-git-monitor-postgres:17-alpine` |
| Redis | `ghcr.io/wkarts/argws-git-monitor-redis:7.4-alpine` |
| RabbitMQ | `ghcr.io/wkarts/argws-git-monitor-rabbitmq:4-management-alpine` |
| MinIO | `ghcr.io/wkarts/argws-git-monitor-minio:RELEASE.2025-09-07T16-13-09Z` |
| Build backend Python | `ghcr.io/wkarts/argws-git-monitor-python:3.13-slim` |
| Build frontend Node | `ghcr.io/wkarts/argws-git-monitor-node:24-alpine` |
| Runtime frontend Nginx | `ghcr.io/wkarts/argws-git-monitor-nginx:1.27-alpine` |

As imagens `argws-git-monitor-api` e `argws-git-monitor-web` já são construídas pelo pipeline de release e continuam publicadas no GHCR. `migrate`, `worker` e `beat` reutilizam a imagem API; não exigem imagem de infraestrutura adicional.

**MinIO:** o Compose antigo utilizava `minio/minio:latest`, mutável. O espelho passa a usar um tag conhecido e identificável. Antes de substituir um MinIO que já está executando, confira sua versão e a compatibilidade dos dados: **não faça downgrade** de dados MinIO sem um procedimento explícito. Em caso de incompatibilidade, não recrie o container; escolha e valide um tag compatível e atualize o catálogo e os Compose numa nova revisão. Se a origem da imagem MinIO estiver indisponível, o mirror deve falhar em vez de substituir silenciosamente a tecnologia. Garanta permissão de download dos pacotes GHCR no servidor que realizará o futuro deploy.

O projeto conserva os mesmos volumes persistentes, banco, filas, URLs de conexão, redes e estratégias de execução. As únicas alterações nos serviços de infraestrutura são suas referências de imagem GHCR e o healthcheck do RabbitMQ. Os Dockerfiles da aplicação apenas aceitam argumentos para usar GHCR na release; builds locais ainda têm origem padrão anterior.

## Sequência de CI e GHCR (sem deploy)

1. `CI` valida YAML, combinações Compose, contratos das imagens e healthchecks.
2. `amqp_smoke` inicia RabbitMQ descartável e exercita publicação/ACK/requeue por Kombu.
3. Após merge autorizado na main, o pipeline de release efetua versionamento e validações.
4. A etapa `dependencies` chama o espelhamento e comprova os manifests das oito imagens GHCR.
5. Apenas depois da etapa de dependências, o pipeline publica API e frontend, construídos com bases GHCR.
6. A Release GitHub continua bloqueada até a verificação das imagens da aplicação.

Para executar **manualmente** a atualização dos espelhos, utilize a ação `Espelhar dependencias no GHCR` no GitHub Actions e o parâmetro `refresh_existing`. Por padrão imagens já existentes são preservadas, impedindo a substituição invisível de uma versão upstream sob o mesmo tag. Toda atualização forçada exige revisão prévia.

## Antes do rollout em uma VPS (procedimento manual)

Não rode `down -v`, não exclua dados, não mude `COMPOSE_PROJECT_NAME` e não troque imagens de banco/MinIO sem validar compatibilidade.

```bash
# Exemplo na pasta da variante de deploy escolhida:
docker compose --env-file .env -f compose.yaml config --quiet
docker compose --env-file .env -f compose.yaml config --format json > /root/gitmonitor-compose-renderizado.json
docker compose --env-file .env -f compose.yaml ps
docker compose --env-file .env -f compose.yaml logs --tail=100 rabbitmq worker beat
```

O JSON renderizado pode conter credenciais: **não compartilhe sem sanitização**. Capture a versão efetiva de Postgres, RabbitMQ, Redis e MinIO antes da recriação de serviços.

Na janela de manutenção: confirme backups restauráveis, verifique o backlog, drene trabalhos longos, atualize **apenas o serviço necessário** e acompanhe health e consumidores. Não use `docker compose down` ou `up --force-recreate` de toda a stack como forma de aplicar apenas um healthcheck.

## Testes e métricas de aceite

O smoke do CI cobre um broker isolado, a conexão AMQP, três mensagens enviadas e confirmadas, rejeição com requeue e confirmação posterior. Os testes em `backend/tests/test_celery_rabbitmq_compat.py` verificam a configuração de queues de controle/eventos do Celery.

Após implantação controlada, testar com tráfego e jobs identificáveis:

- Broker `healthy`, listener AMQP local ativo e nenhum loop de healthcheck `rabbitmq-diagnostics`.
- Celery worker conectado e consumindo jobs; conferir `inspect ping`, fila, ACK, retries e registros de tarefas.
- Beat publicando agendamentos conforme periodicidade e sem entradas repetidas não intencionais.
- Contadores de erros, dead-letter e backlog sem crescimento inesperado; verificar idempotência da aplicação.
- Snapshot antes/depois de CPU total do broker, CPU de processos `beam.smp` temporários, PSI CPU, load average e reinícios, com janelas de carga equivalentes.

**Expectativa configuracional:** de 6 para 1 healthcheck por minuto por broker (redução de 83,3% das invocações). Isso **não** é uma alegação de 83,3% de queda do consumo de CPU da VPS. O impacto real só pode ser medido depois da aplicação. Testes de integração do CI **não comprovam** ausência absoluta de perdas ou duplicidades em produção.

## Rollback

Antes do merge, reverter o commit da PR na branch de revisão. Após eventual aplicação manual, restaurar o Compose anterior e referências de imagem validadas, sem excluir dados, e reimplantar **somente** os serviços que exigirem mudança. O RabbitMQ pode precisar de recriação para receber o novo healthcheck. Preserve volumes e confirme backlog e integridade após cada passo.
