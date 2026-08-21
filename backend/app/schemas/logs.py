from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LogSourceRead(BaseModel):
    key: str
    label: str
    category: str
    available: bool
    file_count: int
    size_bytes: int
    last_modified_at: datetime | None


class LogLineRead(BaseModel):
    source: str
    file: str
    line_number: int | None = None
    timestamp: datetime | None = None
    level: str | None = None
    logger: str | None = None
    service: str | None = None
    message: str
    raw: str
    extra: dict[str, Any] = Field(default_factory=dict)


class LogTailResponse(BaseModel):
    source: LogSourceRead
    files: list[str]
    lines: list[LogLineRead]
    truncated: bool


class AuditLogRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    user_name: str | None = None
    user_email: str | None = None
    action: str
    entity_type: str | None
    entity_id: str | None
    details: dict[str, Any]
    ip_address: str | None
    created_at: datetime


class LogPurgeRequest(BaseModel):
    older_than_days: int = Field(default=30, ge=1, le=3650)
    confirmation: str = Field(min_length=1, max_length=100)


class LogPurgeResult(BaseModel):
    deleted_files: int
    reclaimed_bytes: int
    sources: dict[str, int]
