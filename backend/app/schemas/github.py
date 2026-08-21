from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl, field_validator

from app.models.github import ConnectionStatus
from app.schemas.common import ORMModel


class GitHubConnectionCreate(BaseModel):
    name: str = Field(default="GitHub principal", min_length=2, max_length=120)
    token: str = Field(min_length=20, max_length=1000)
    auto_import: bool = True
    api_url: str = Field(default="https://api.github.com", min_length=10, max_length=500)


class GitHubConnectionRead(ORMModel):
    id: uuid.UUID
    name: str
    github_login: str
    github_user_id: int | None
    token_last_four: str | None
    status: ConnectionStatus
    auto_import: bool
    api_url: str
    last_sync_at: datetime | None
    last_error: str | None
    rate_limit_remaining: int | None
    rate_limit_reset_at: datetime | None
    created_at: datetime
    repository_count: int = 0
    available_repository_count: int = 0
    oauth_scopes: list[str] = Field(default_factory=list)


class GitHubConnectionDiagnostics(BaseModel):
    connected: bool
    github_login: str
    accessible_repositories: int
    private_repositories: int
    writable_repositories: int
    admin_repositories: int
    actions_samples_checked: int
    actions_samples_observed: int
    rate_limit_remaining: int | None
    rate_limit_reset_at: datetime | None
    oauth_scopes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checked_at: datetime


class GitHubRemoteRepository(BaseModel):
    github_id: int
    owner: str
    name: str
    full_name: str
    html_url: HttpUrl
    description: str | None = None
    private: bool
    archived: bool
    default_branch: str
    language: str | None = None
    selected: bool = False
    permissions: dict[str, bool] = Field(default_factory=dict)


class RepositoryImportRequest(BaseModel):
    repository_ids: list[int] = Field(min_length=1, max_length=500)


class RepositoryImportResponse(BaseModel):
    message: str
    imported_count: int
    already_monitored_count: int
    queued_count: int
    repository_ids: list[uuid.UUID]
    job_ids: list[uuid.UUID]


class GitHubRepositoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=350)
    private: bool = True
    auto_init: bool = True

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Nome do repositório é obrigatório.")
        return normalized


class SyncAcceptedResponse(BaseModel):
    message: str
    task_id: str | None = None
    job_id: uuid.UUID | None = None


class WebhookConfigureRequest(BaseModel):
    repository_ids: list[uuid.UUID] | None = None
    webhook_url: str | None = None


class WebhookConfigureResult(BaseModel):
    repository: str
    success: bool
    message: str
    webhook_id: int | None = None
