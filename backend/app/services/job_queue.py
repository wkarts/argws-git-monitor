from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import SyncJob, SyncJobStatus
from app.services.realtime import publish_event

logger = logging.getLogger(__name__)


async def _publish_job(job: SyncJob, event_type: str) -> None:
    try:
        await publish_event(
            job.user_id,
            event_type,
            {
                "job_id": str(job.id),
                "kind": job.kind,
                "label": job.label,
                "status": job.status.value if hasattr(job.status, "value") else str(job.status),
                "progress_current": job.progress_current,
                "progress_total": job.progress_total,
                "message": job.message,
                "error": job.error,
                "result": job.result or {},
            },
            repository_id=job.repository_id,
        )
    except Exception as exc:
        # Realtime é acelerador de UX, nunca dependência transacional do job.
        logger.debug("Falha ao publicar evento realtime do job %s: %s", job.id, exc)


async def create_job(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    kind: str,
    label: str,
    connection_id: uuid.UUID | None = None,
    repository_id: uuid.UUID | None = None,
    progress_total: int = 0,
    message: str | None = None,
) -> SyncJob:
    job = SyncJob(
        user_id=user_id,
        connection_id=connection_id,
        repository_id=repository_id,
        celery_task_id=None,
        kind=kind,
        label=label,
        status=SyncJobStatus.QUEUED,
        progress_current=0,
        progress_total=progress_total,
        message=message or "Aguardando processamento.",
        error=None,
        result={},
        created_at=datetime.now(UTC),
        started_at=None,
        completed_at=None,
    )
    session.add(job)
    await session.flush()
    return job


async def mark_job_running(job_id: str | uuid.UUID, *, message: str | None = None) -> None:
    from app.core.database import session_scope

    snapshot: SyncJob | None = None
    async with session_scope() as session:
        job = await session.get(SyncJob, uuid.UUID(str(job_id)))
        if not job or job.status == SyncJobStatus.CANCELLED:
            return
        job.status = SyncJobStatus.RUNNING
        job.started_at = job.started_at or datetime.now(UTC)
        if message:
            job.message = message
        snapshot = job
    if snapshot:
        await _publish_job(snapshot, "job.running")


async def update_job_progress(
    job_id: str | uuid.UUID,
    *,
    current: int | None = None,
    total: int | None = None,
    message: str | None = None,
) -> None:
    from app.core.database import session_scope

    snapshot: SyncJob | None = None
    async with session_scope() as session:
        job = await session.get(SyncJob, uuid.UUID(str(job_id)))
        if not job or job.status == SyncJobStatus.CANCELLED:
            return
        if current is not None:
            job.progress_current = current
        if total is not None:
            job.progress_total = total
        if message:
            job.message = message
        snapshot = job
    if snapshot:
        await _publish_job(snapshot, "job.progress")


async def mark_job_success(
    job_id: str | uuid.UUID,
    *,
    result: dict[str, Any] | None = None,
    message: str | None = None,
) -> None:
    from app.core.database import session_scope

    snapshot: SyncJob | None = None
    async with session_scope() as session:
        job = await session.get(SyncJob, uuid.UUID(str(job_id)))
        if not job or job.status == SyncJobStatus.CANCELLED:
            return
        job.status = SyncJobStatus.SUCCESS
        job.progress_current = job.progress_total or job.progress_current
        job.message = message or "Processamento concluído."
        job.error = None
        job.result = result or {}
        job.completed_at = datetime.now(UTC)
        snapshot = job
    if snapshot:
        await _publish_job(snapshot, "job.success")


async def mark_job_failed(
    job_id: str | uuid.UUID,
    *,
    error: str,
    message: str | None = None,
) -> None:
    from app.core.database import session_scope

    snapshot: SyncJob | None = None
    async with session_scope() as session:
        job = await session.get(SyncJob, uuid.UUID(str(job_id)))
        if not job or job.status == SyncJobStatus.CANCELLED:
            return
        job.status = SyncJobStatus.FAILED
        job.message = message or "Processamento concluído com erro."
        job.error = error[:4000]
        job.completed_at = datetime.now(UTC)
        snapshot = job
    if snapshot:
        await _publish_job(snapshot, "job.failed")
