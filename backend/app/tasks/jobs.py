from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.database import dispose_engine, session_scope
from app.models.activity import Notification, SyncJob, SyncJobStatus
from app.models.github import ConnectionStatus, GitHubConnection
from app.services.activity_observer import sync_repository_with_activity
from app.services.job_queue import (
    create_job,
    mark_job_failed,
    mark_job_running,
    mark_job_success,
)
from app.services.sync_orchestrator import sync_connection_with_progress
from app.tasks.celery_app import celery_app


def run_async(coro):
    async def runner():
        try:
            return await coro
        finally:
            await dispose_engine()

    return asyncio.run(runner())


async def _mark_retry(job_id: str, retries: int) -> None:
    async with session_scope() as session:
        job = await session.get(SyncJob, uuid.UUID(job_id))
        if not job or job.status == SyncJobStatus.CANCELLED:
            return
        job.status = SyncJobStatus.QUEUED
        job.message = f"Falha temporária. Nova tentativa {retries + 2} agendada."


def _retry_or_fail(self, exc: Exception, job_id: str | None, *, max_countdown: int) -> None:
    if job_id:
        if self.request.retries >= self.max_retries:
            run_async(mark_job_failed(job_id, error=str(exc)))
        else:
            run_async(_mark_retry(job_id, self.request.retries))
    raise self.retry(exc=exc, countdown=min(30 * (self.request.retries + 1), max_countdown))


@celery_app.task(name="github.sync_connection", bind=True, max_retries=3)
def sync_connection_task(
    self,
    connection_id: str,
    selected_ids: list[int] | None = None,
    job_id: str | None = None,
):
    if job_id:
        run_async(mark_job_running(job_id, message="Sincronizando catálogo, dados e atividade do GitHub."))
    try:
        selected = set(selected_ids) if selected_ids else None
        result = run_async(
            sync_connection_with_progress(
                connection_id,
                selected_github_ids=selected,
                job_id=job_id,
            )
        )
        if job_id:
            run_async(
                mark_job_success(
                    job_id,
                    result=result,
                    message=(
                        f"Sincronização concluída: {result['synced']} sucesso, "
                        f"{result['errors']} erro(s)."
                    ),
                )
            )
        return result
    except Exception as exc:
        _retry_or_fail(self, exc, job_id, max_countdown=180)


@celery_app.task(name="github.sync_repository", bind=True, max_retries=2)
def sync_repository_task(self, repository_id: str, job_id: str | None = None):
    if job_id:
        run_async(mark_job_running(job_id, message="Atualizando commits, Actions, PRs, issues, releases e atividade."))
    try:
        activity = run_async(sync_repository_with_activity(repository_id))
        result = {"repository_id": repository_id, "synced": True, "activity": activity}
        if job_id:
            run_async(mark_job_success(job_id, result=result, message="Repositório e atividade atualizados."))
        return result
    except Exception as exc:
        _retry_or_fail(self, exc, job_id, max_countdown=120)


async def _sync_all_connections() -> dict[str, int]:
    jobs: list[tuple[str, str]] = []
    async with session_scope() as session:
        result = await session.execute(
            select(GitHubConnection).where(GitHubConnection.status != ConnectionStatus.DEMO)
        )
        connections = result.scalars().all()
        for connection in connections:
            job = await create_job(
                session,
                user_id=connection.user_id,
                connection_id=connection.id,
                kind="connection.sync.auto",
                label=f"Sincronização automática · {connection.name}",
                message="Aguardando worker periódico.",
            )
            jobs.append((str(connection.id), str(job.id)))

    for connection_id, job_id in jobs:
        task = sync_connection_task.delay(connection_id, None, job_id)
        async with session_scope() as session:
            job = await session.get(SyncJob, uuid.UUID(job_id))
            if job:
                job.celery_task_id = task.id
    return {"queued": len(jobs)}


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
