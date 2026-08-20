# Deploy no Dockge, Portainer ou CloudPanel

## Dockge/Portainer

1. Copie a pasta completa para o servidor.
2. Preserve `.env` fora do Git.
3. Importe `compose.yaml` como stack.
4. Inicie os serviços.
5. Verifique `migrate` como concluído e os demais como saudáveis.

## CloudPanel/Nginx

Configure o domínio como reverse proxy para:

```text
http://127.0.0.1:8080
```

Antes de iniciar:

```bash
./scripts/configure-domain.sh https://git.seu-dominio.com.br
```

Para limitar o acesso direto no host, ajuste:

```dotenv
APP_BIND_ADDRESS=127.0.0.1
```

Exemplo Nginx externo:

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 90s;
}
```

O certificado TLS deve ser emitido no proxy externo. Depois do HTTPS ativo, use **Configurações > Configurar webhooks**.
