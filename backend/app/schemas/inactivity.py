from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel

ALLOWED_UNITS = {"hours", "days", "weeks", "months"}
ALLOWED_ACTIONS = {"private", "notify"}
ALLOWED_SOURCES = {
    "push",
    "commit",
    "pull_request",
    "issue",
    "actions",
    "release",
    "repository_event",
    "repository_metadata",
}
DEFAULT_SOURCES = sorted(ALLOWED_SOURCES)


class InactivityPolicyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    timeout_value: int = Field(default=30, ge=1, le=3650)
    timeout_unit: str = Field(default="days")
    action: str = Field(default="private")
    enabled: bool = True
    activity_sources: list[str] = Field(default_factory=lambda: list(DEFAULT_SOURCES))
    repository_ids: list[uuid.UUID] = Field(default_factory=list, max_length=1000)

    @field_validator("timeout_unit")
    @classmethod
    def validate_unit(cls, value: str) -> str:
        if value not in ALLOWED_UNITS:
            raise ValueError("Unidade deve ser hours, days, weeks ou months.")
        return value

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        if value not in ALLOWED_ACTIONS:
            raise ValueError("Ação deve ser private ou notify.")
        return value

    @field_validator("activity_sources")
    @classmethod
    def validate_sources(cls, value: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        invalid = set(normalized) - ALLOWED_SOURCES
        if invalid:
            raise ValueError(f"Fontes inválidas: {', '.join(sorted(invalid))}")
        if not normalized:
            raise ValueError("Selecione ao menos uma fonte de atividade.")
        return normalized


class InactivityPolicyUpdate(InactivityPolicyCreate):
    pass


class InactivityPolicyRead(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    description: str | None
    timeout_value: int
    timeout_unit: str
    action: str
    enabled: bool
    activity_sources: list[str]
    last_evaluated_at: datetime | None
    created_at: datetime
    updated_at: datetime
    repository_ids: list[uuid.UUID] = Field(default_factory=list)
    repository_count: int = 0


class InactivityActionLogRead(ORMModel):
    id: uuid.UUID
    policy_id: uuid.UUID | None
    repository_id: uuid.UUID | None
    repository_full_name: str
    action: str
    status: str
    previous_private: bool | None
    last_activity_at: datetime | None
    threshold_at: datetime | None
    reason: str
    result: dict
    error: str | None
    created_at: datetime


class InactivityEvaluationResult(BaseModel):
    policies: int
    repositories: int
    due: int
    privatized: int
    notified: int
    skipped: int
    failed: int
