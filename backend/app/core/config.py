from __future__ import annotations

from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from typing import Literal

from pydantic import EmailStr, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def resolve_app_version() -> str:
    """Retorna a versão embarcada no próprio artefato, nunca do ambiente de deploy."""
    try:
        return package_version("argws-git-monitor-api")
    except PackageNotFoundError:
        version_file = Path(__file__).resolve().parents[3] / "VERSION"
        if version_file.is_file():
            value = version_file.read_text(encoding="utf-8").strip()
            if value:
                return value
        return "0.0.0+unknown"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "ARGWS Git Monitor"
    app_env: Literal["development", "test", "production"] = "production"
    app_debug: bool = False
    log_level: str = "INFO"
    service_role: str = "api"
    log_file: str | None = None
    log_stack_root: str = "/var/log/argws-stack"
    log_retention_days: int = 30
    log_default_tail_lines: int = 500
    log_max_tail_lines: int = 10000
    log_download_max_mb: int = 100

    api_v1_prefix: str = "/api/v1"
    public_base_url: str = "http://localhost:8080"
    cors_origins: str = "http://localhost:8080,http://127.0.0.1:8080"

    app_secret_key: str = Field(min_length=32)
    encryption_key: str = Field(min_length=32)
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    database_url: str = "postgresql+asyncpg://gitmonitor:gitmonitor@postgres:5432/gitmonitor"
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "amqp://gitmonitor:gitmonitor@rabbitmq:5672//"
    celery_result_backend: str = "redis://redis:6379/1"

    # Object storage interno real. A stack injeta uma credencial dedicada quando
    # configurada; instalações existentes continuam válidas usando APP_SECRET_KEY.
    minio_internal_endpoint: str = "http://minio:9000"
    minio_internal_access_key: str = "argws-internal"
    minio_internal_secret_key: str | None = None
    minio_internal_region: str = "us-east-1"

    initial_admin_name: str = "Administrador ARGWS"
    initial_admin_email: EmailStr = "admin@argws.com.br"
    initial_admin_password: str = Field(min_length=12)
    initial_admin_must_change_password: bool = True

    github_api_url: str = "https://api.github.com"
    github_api_version: str = "2022-11-28"
    github_webhook_secret: str = Field(min_length=16)
    github_repository_limit: int = 300
    github_request_timeout_seconds: float = 30.0
    github_concurrency: int = 5
    # Full sync é reconciliação; atualizações imediatas devem vir por webhook.
    # 1h mantém 300 repositórios confortavelmente abaixo do rate limit REST.
    sync_interval_seconds: int = 3600

    demo_data_enabled: bool = True
    notification_retention_days: int = 90

    @field_validator("public_base_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def app_version(self) -> str:
        return resolve_app_version()

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def internal_minio_secret(self) -> str:
        return self.minio_internal_secret_key or self.app_secret_key

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
