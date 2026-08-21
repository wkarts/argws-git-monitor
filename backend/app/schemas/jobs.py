from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.activity import SyncJobStatus
from app.schemas.common import ORMModel


class SyncJobRead(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID
    connection_id: uuid.UUID | None
    repository_id: uuid.UUID | None
    celery_task_id: str | None
    kind: str
    label: str
    status: SyncJobStatus
    progress_current: int
    progress_total: int
    message: str | None
    error: str | None
    result: dict[str, Any]
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class QueueOverview(BaseModel):
    queued: int
    running: int
    succeeded: int
    failed: int
    cancelled: int
    total: int
    worker_online: bool
    worker_count: int
    workers: list[str]
    worker_error: str | None = None
