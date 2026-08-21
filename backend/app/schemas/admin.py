from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, model_validator


class AdminUserRead(BaseModel):
    id: uuid.UUID
    name: str
    email: EmailStr
    is_active: bool
    is_superuser: bool
    must_change_password: bool
    totp_enabled: bool
    last_login_at: datetime | None
    created_at: datetime
    job_title: str | None = None
    timezone: str = "America/Bahia"
    locale: str = "pt-BR"
    avatar_updated_at: datetime | None = None
    avatar_url: str | None = None
    github_connection_count: int = 0
    repository_count: int = 0
    active_session_count: int = 0

    @model_validator(mode="after")
    def build_avatar_url(self) -> AdminUserRead:
        if self.avatar_updated_at:
            self.avatar_url = (
                f"/api/v1/auth/users/{self.id}/avatar?v={int(self.avatar_updated_at.timestamp())}"
            )
        return self


class AdminUserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=12, max_length=512)
    is_active: bool = True
    is_superuser: bool = False
    must_change_password: bool = True
    job_title: str | None = Field(default=None, max_length=160)


class AdminUserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    email: EmailStr | None = None
    is_active: bool | None = None
    is_superuser: bool | None = None
    must_change_password: bool | None = None
    job_title: str | None = Field(default=None, max_length=160)


class AdminPasswordResetResponse(BaseModel):
    message: str
    temporary_password: str


class AdminOverview(BaseModel):
    total_users: int
    active_users: int
    administrators: int
    two_factor_enabled: int
    active_sessions: int
