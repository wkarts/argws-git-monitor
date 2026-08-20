# Deploy com CloudPanel + Dockge

Este pacote separa claramente as duas responsabilidades:

```text
Dockge     → executa e administra os containers
CloudPanel → publica o domínio, o certificado TLS e o reverse proxy Nginx
```

## Estrutura

```text
deploy/cloudpanel/
├── README.md
├── nginx/
│   └── argws-git-monitor.conf
└── dockge/
    ├── compose.yaml
    ├── .env.example
    ├── generate-env.sh
    └── deploy.sh
```

## 1. Preparar a stack do Dockge

Copie a pasta `dockge` para o diretório de stacks configurado no servidor:

```bash
mkdir -p /opt/stacks/argws-git-monitor
cp -a deploy/cloudpanel/dockge/. /opt/stacks/argws-git-monitor/
cd /opt/stacks/argws-git-monitor
```

Adapte `/opt/stacks` para o diretório real utilizado pelo seu Dockge.

## 2. Gerar o ambiente seguro

```bash
bash generate-env.sh \
  --url https://git.seu-dominio.com.br \
  --port 8080
```

O gerador fixa:

```dotenv
APP_BIND_ADDRESS=127.0.0.1
```

Assim, a aplicação não fica exposta diretamente na interface pública do servidor. Somente o Nginx do CloudPanel acessa a porta local.

## 3. Subir a stack

Pela linha de comando:

```bash
bash deploy.sh
```

Ou pelo Dockge:

1. abra a stack `argws-git-monitor`;
2. valide o `compose.yaml`;
3. execute **Pull**;
4. execute **Deploy**;
5. confirme que `migrate` terminou com código zero;
6. confirme os serviços `postgres`, `redis`, `rabbitmq`, `api` e `web` saudáveis.

## 4. Criar o site no CloudPanel

No CloudPanel:

1. crie o site para `git.seu-dominio.com.br`;
2. configure o domínio para usar reverse proxy;
3. aponte o upstream para `http://127.0.0.1:8080`;
4. abra o editor do Vhost Nginx;
5. aplique o conteúdo de `nginx/argws-git-monitor.conf` no bloco apropriado;
6. salve e valide a configuração Nginx;
7. emita o certificado Let's Encrypt pelo próprio CloudPanel.

O backend local esperado é:

```text
http://127.0.0.1:8080
```

## 5. DNS

Crie um registro para o domínio utilizado:

```text
Tipo: A
Nome: git
Destino: IP público do servidor
Proxy Cloudflare: conforme sua política de rede
```

Aguarde a propagação antes de solicitar o certificado TLS.

## 6. Verificação

No servidor:

```bash
curl -fsS http://127.0.0.1:8080/api/v1/health/ready
curl -fsS https://git.seu-dominio.com.br/api/v1/health/ready
```

No navegador:

```text
https://git.seu-dominio.com.br
```

## 7. Atualização

```bash
cd /opt/stacks/argws-git-monitor
docker compose --env-file .env -f compose.yaml pull
docker compose --env-file .env -f compose.yaml up -d --no-build --remove-orphans
```

Também é possível alterar `IMAGE_TAG` no `.env` e executar o redeploy pelo Dockge.

## 8. GHCR privado

Quando as imagens estiverem privadas:

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u wkarts --password-stdin
```

O token precisa de `read:packages`.

## Segurança

- mantenha `APP_BIND_ADDRESS=127.0.0.1`;
- não publique PostgreSQL, Redis ou AMQP;
- mantenha o RabbitMQ Management limitado a `127.0.0.1`;
- não versione o `.env`;
- mantenha o TLS ativo no CloudPanel;
- configure os webhooks do GitHub somente depois que o domínio HTTPS estiver respondendo.
