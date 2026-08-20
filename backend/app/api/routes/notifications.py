from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select, update

from app.api.deps import CurrentUser, DbSession
from app.models.activity import Notification
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.notification import NotificationRead

router = APIRouter(prefix="/notifications", tags=["Notificações"])


@router.get("", response_model=PaginatedResponse[NotificationRead])
async def list_notifications(
    current_user: CurrentUser,
    db: DbSession,
    unread_only: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
):
    filters = [Notification.user_id == current_user.id]
    if unread_only:
        filters.append(Notification.read_at.is_(None))
    total = int(
        (
            await db.execute(select(func.count(Notification.id)).where(*filters))
        ).scalar_one()
    )
    result = await db.execute(
        select(Notification)
        .where(*filters)
        .order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = result.scalars().all()
    return PaginatedResponse[NotificationRead](
        items=[NotificationRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=max(math.ceil(total / page_size), 1),
    )


@router.post("/{notification_id}/read", response_model=NotificationRead)
async def mark_as_read(
    notification_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=404, detail="Notificação não encontrada.")
    notification.read_at = notification.read_at or datetime.now(UTC)
    await db.commit()
    await db.refresh(notification)
    return NotificationRead.model_validate(notification)


@router.post("/read-all", response_model=MessageResponse)
async def mark_all_as_read(current_user: CurrentUser, db: DbSession) -> MessageResponse:
    await db.execute(
        update(Notification)
        .where(Notification.user_id == current_user.id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    await db.commit()
    return MessageResponse(message="Todas as notificações foram marcadas como lidas.")
