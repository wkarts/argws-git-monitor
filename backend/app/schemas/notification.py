from __future__ import annotations

import uuid
from datetime import datetime

from app.schemas.common import ORMModel


class NotificationRead(ORMModel):
    id: uuid.UUID
    repository_id: uuid.UUID | None
    event_type: str
    severity: str
    title: str
    message: str
    url: str | None
    payload: dict
    read_at: datetime | None
    created_at: datetime
