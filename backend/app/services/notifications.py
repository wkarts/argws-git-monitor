from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Notification, NotificationSeverity


async def create_notification(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    event_type: str,
    severity: NotificationSeverity | str,
    title: str,
    message: str,
    repository_id: uuid.UUID | None = None,
    url: str | None = None,
    payload: dict[str, Any] | None = None,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        repository_id=repository_id,
        event_type=event_type,
        severity=severity.value if isinstance(severity, NotificationSeverity) else severity,
        title=title,
        message=message,
        url=url,
        payload=payload or {},
        created_at=datetime.now(UTC),
    )
    session.add(notification)
    await session.flush()
    return notification
