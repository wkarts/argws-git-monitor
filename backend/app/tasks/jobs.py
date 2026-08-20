from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.database import dispose_engine, session_scope
from app.models.activity import Notification
from app.models.github import ConnectionStatus, GitHubConnection
from app.services.github_sync import sync_connection, sync_repository
from app.tasks.celery_app import celery_app


def run_async(coro):
    async def runner():
        try:
            return await coro
        finally:
            await dispose_engine()

    return asyncio.run(runner())


@celery_app.task(name="github.sync_connection", bind=True, max_retries=3)
def sync_connection_task(self, connection_id: str, selected_ids: list[int] | None = None):
    try:
        selected = set(selected_ids) if selected_ids else None
        return run_async(sync_connection(connection_id, selected_github_ids=selected))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=min(30 * (self.request.retries + 1), 180))


@celery_app.task(name="github.sync_repository", bind=True, max_retries=2)
def sync_repository_task(self, repository_id: str):
    try:
        run_async(sync_repository(repository_id))
        return {"repository_id": repository_id, "synced": True}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=min(30 * (self.request.retries + 1), 120))


async def _sync_all_connections() -> dict[str, int]:
    async with session_scope() as session:
        result = await session.execute(
            select(GitHubConnection.id).where(GitHubConnection.status != ConnectionStatus.DEMO)
        )
        connection_ids = [str(item) for item in result.scalars().all()]
    for connection_id in connection_ids:
        sync_connection_task.delay(connection_id)
    return {"queued": len(connection_ids)}


@celery_app.task(name="github.sync_all_connections")
def sync_all_connections_task():
    return run_async(_sync_all_connections())


async def _cleanup_notifications() -> dict[str, int]:
    settings = get_settings()
    threshold = datetime.now(UTC) - timedelta(days=settings.notification_retention_days)
    async with session_scope() as session:
        result = await session.execute(
            delete(Notification).where(
                Notification.created_at < threshold,
                Notification.read_at.is_not(None),
            )
        )
        return {"deleted": result.rowcount or 0}


@celery_app.task(name="notifications.cleanup")
def cleanup_notifications_task():
    return run_async(_cleanup_notifications())
