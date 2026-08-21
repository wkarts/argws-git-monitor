#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_SERVICES = ("api", "worker", "beat", "migrate", "web", "postgres", "redis", "rabbitmq")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera segredos locais do ARGWS Git Monitor")
    parser.add_argument("--force", action="store_true", help="sobrescreve .env e credenciais")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    env_path = ROOT / ".env"
    credentials_path = ROOT / "CREDENCIAIS_INICIAIS.txt"
    data_directories = [
        ROOT / "data-postgres",
        ROOT / "data-redis",
        ROOT / "data-rabbitmq",
        *(ROOT / "data-logs" / service for service in LOG_SERVICES),
    ]
    for directory in data_directories:
        directory.mkdir(parents=True, exist_ok=True)

    if env_path.exists() and not args.force:
        print(f"{env_path} já existe; nenhuma alteração realizada.")
        print(f"Diretórios persistentes confirmados em {ROOT / 'data-*'}")
        return

    admin_password = secrets.token_urlsafe(18)
    postgres_password = secrets.token_urlsafe(24)
    rabbit_password = secrets.token_urlsafe(24)
    values = {
        "app_secret": secrets.token_urlsafe(64),
        "encryption_key": base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"),
        "webhook_secret": secrets.token_urlsafe(48),
    }
    url = f"http://localhost:{args.port}"
    env_path.write_text(
        f"""COMPOSE_PROJECT_NAME=argws-git-monitor
APP_NAME="ARGWS Git Monitor"
APP_ENV=production
APP_DEBUG=false
LOG_LEVEL=INFO
LOG_RETENTION_DAYS=30
APP_HTTP_PORT={args.port}
APP_BIND_ADDRESS=0.0.0.0
PUBLIC_BASE_URL={url}
CORS_ORIGINS={url},http://127.0.0.1:{args.port}
APP_SECRET_KEY={values['app_secret']}
ENCRYPTION_KEY={values['encryption_key']}
INITIAL_ADMIN_NAME="Administrador ARGWS"
INITIAL_ADMIN_EMAIL=admin@argws.com.br
INITIAL_ADMIN_PASSWORD={admin_password}
INITIAL_ADMIN_MUST_CHANGE_PASSWORD=true
POSTGRES_DB=gitmonitor
POSTGRES_USER=gitmonitor
POSTGRES_PASSWORD={postgres_password}
RABBITMQ_DEFAULT_USER=gitmonitor
RABBITMQ_DEFAULT_PASS={rabbit_password}
RABBITMQ_MANAGEMENT_PORT=15672
GITHUB_API_URL=https://api.github.com
GITHUB_WEBHOOK_SECRET={values['webhook_secret']}
GITHUB_REPOSITORY_LIMIT=300
GITHUB_REQUEST_TIMEOUT_SECONDS=30
GITHUB_CONCURRENCY=5
SYNC_INTERVAL_SECONDS=3600
DEMO_DATA_ENABLED=true
NOTIFICATION_RETENTION_DAYS=90
API_WORKERS=2
CELERY_CONCURRENCY=2
CELERY_MAX_TASKS_PER_CHILD=100
INSTALL_SOURCE=ghcr
""",
        encoding="utf-8",
    )
    credentials_path.write_text(
        f"""ARGWS GIT MONITOR - CREDENCIAIS INICIAIS
Aplicação: {url}
E-mail: admin@argws.com.br
Senha: {admin_password}
RabbitMQ: http://localhost:15672
Usuário RabbitMQ: gitmonitor
Senha RabbitMQ: {rabbit_password}
Dados persistentes: ./data-postgres, ./data-redis, ./data-rabbitmq e ./data-logs.
As imagens GHCR usam sempre :latest e a versão é lida do próprio aplicativo.
""",
        encoding="utf-8",
    )
    if os.name != "nt":
        os.chmod(env_path, 0o600)
        os.chmod(credentials_path, 0o600)
    print(f"Segredos gerados em {env_path}")
    print(f"Credenciais gravadas em {credentials_path}")
    print("Dados persistentes:")
    print(f"- {ROOT / 'data-postgres'}")
    print(f"- {ROOT / 'data-redis'}")
    print(f"- {ROOT / 'data-rabbitmq'}")
    print(f"- {ROOT / 'data-logs'}")


if __name__ == "__main__":
    main()
