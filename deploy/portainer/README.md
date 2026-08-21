# Deploy pelo Portainer

Este diretório contém uma stack específica para o Portainer. O arquivo não usa `env_file` nem caminhos de build: as variáveis são administradas pelo painel e as imagens vêm do GHCR.

## Conteúdo

```text
compose.yaml
stack.env.example
generate-stack-env.sh
```

## Persistência relativa ao diretório da stack

Os serviços persistentes utilizam:

```yaml
- ./data-postgres:/var/lib/postgresql/data
- ./data-redis:/data
- ./data-rabbitmq:/var/lib/rabbitmq
```

No Portainer, os caminhos relativos são resolvidos no diretório de trabalho criado para a stack. Portanto, os dados ficam agrupados com a stack gerenciada pelo Portainer, sem apontar para `/opt`, `/home`, `/var/lib` ou outro diretório absoluto do host.

## Deploy pelo Web Editor

1. Abra **Stacks > Add stack**.
2. Informe `argws-git-monitor`.
3. Selecione **Web editor**.
4. Cole `compose.yaml`.
5. Gere as variáveis:

```bash
cd deploy/portainer
bash generate-stack-env.sh --url https://git.seu-dominio.com.br --bind 127.0.0.1
```

6. Em **Environment variables**, carregue ou copie `stack.env`.
7. Confirme no editor os três caminhos `./data-*`.
8. Clique em **Deploy the stack**.
9. Aguarde `migrate` terminar e valide os containers.

## Deploy por repositório Git

```text
Repository URL: https://github.com/wkarts/argws-git-monitor.git
Repository reference: refs/heads/main
Compose path: deploy/portainer/compose.yaml
```

As variáveis continuam sendo cadastradas em **Environment variables**.

## Registro GHCR privado

1. Abra **Registries > Add registry**.
2. Selecione registro personalizado.
3. Use `ghcr.io`.
4. Use `wkarts` como usuário.
5. Informe um PAT com `read:packages`.
6. Salve antes de implantar.

## Atualização

1. abra a stack;
2. confirme `IMAGE_TAG=0.2.3`;
3. habilite o repull das imagens;
4. clique em **Update the stack**.

Uma instalação anterior baseada em volumes nomeados deve ser migrada pelo shell do host antes do redeploy:

```bash
bash deploy/migrate-named-volumes.sh \
  --stack-dir /diretorio/de-trabalho-da-stack \
  --project argws-git-monitor
```

O script mantém os volumes antigos intactos.

## Diagnóstico

```bash
docker ps --filter label=com.docker.compose.project=argws-git-monitor
curl -fsS http://127.0.0.1:8080/api/v1/health/ready
```

## CloudPanel

Para usar o Portainer atrás do CloudPanel, configure `APP_BIND_ADDRESS=127.0.0.1` e utilize `deploy/cloudpanel/nginx/argws-git-monitor.conf`.
