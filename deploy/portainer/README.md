# Deploy pelo Portainer

Este diretório contém uma stack específica para o Portainer. O arquivo não usa `env_file` nem caminhos de build, porque as variáveis são administradas pelo próprio painel e as imagens são obtidas do GHCR.

## Conteúdo

```text
compose.yaml
stack.env.example
generate-stack-env.sh
```

## Deploy pelo Web Editor

1. Abra **Stacks > Add stack**.
2. Informe o nome `argws-git-monitor`.
3. Selecione **Web editor**.
4. Cole o conteúdo de `compose.yaml`.
5. Gere as variáveis em uma máquina Linux:

```bash
cd deploy/portainer
bash generate-stack-env.sh --url https://git.seu-dominio.com.br --bind 127.0.0.1
```

6. Em **Environment variables**, carregue ou copie as variáveis de `stack.env`.
7. Clique em **Deploy the stack**.
8. Aguarde `migrate` terminar e valide os demais containers.

## Deploy por repositório Git

Configure:

```text
Repository URL: https://github.com/wkarts/argws-git-monitor.git
Repository reference: refs/heads/main
Compose path: deploy/portainer/compose.yaml
```

As variáveis continuam sendo cadastradas na seção **Environment variables** do Portainer.

## Registro GHCR privado

Quando as imagens estiverem privadas:

1. Abra **Registries > Add registry**.
2. Selecione registro personalizado.
3. Use `ghcr.io` como URL.
4. Use `wkarts` como usuário.
5. Informe um Personal Access Token com `read:packages`.
6. Salve antes de implantar a stack.

## Atualização

Na stack:

1. abra **Editor**;
2. confirme `IMAGE_TAG=0.2.2` ou altere para a versão desejada;
3. habilite a opção para repuxar as imagens;
4. clique em **Update the stack**.

## Diagnóstico

No console do host:

```bash
docker ps --filter label=com.docker.compose.project=argws-git-monitor
docker logs argws-git-monitor-api-1 --tail=200
curl -fsS http://127.0.0.1:8080/api/v1/health/ready
```

Os nomes exatos dos containers podem variar conforme o nome escolhido para a stack.

## CloudPanel

Para usar o Portainer atrás do CloudPanel, configure `APP_BIND_ADDRESS=127.0.0.1` e utilize o snippet Nginx disponível em:

```text
deploy/cloudpanel/nginx/argws-git-monitor.conf
```
