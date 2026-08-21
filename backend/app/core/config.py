from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import EmailStr, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "ARGWS Git Monitor"
    app_version: str = "0.3.0"
    app_env: Literal["development", "test", "production"] = "production"
    app_debug: bool = False
    log_level: str = "INFO"

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
    sync_interval_seconds: int = 300

    demo_data_enabled: bool = True
    notification_retention_days: int = 90

    @field_validator("public_base_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
