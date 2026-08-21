from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models.activity import SyncJob, SyncJobStatus
from app.schemas.common import MessageResponse
from app.schemas.jobs import QueueOverview, SyncJobRead
from app.tasks.celery_app import celery_app

router = APIRouter(prefix="/jobs", tags=["Fila operacional"])


def _status_value(value: str | SyncJobStatus) -> str:
    return value.value if isinstance(value, SyncJobStatus) else str(value)


@router.get("/overview", response_model=QueueOverview)
async def queue_overview(current_user: CurrentUser, db: DbSession) -> QueueOverview:
    result = await db.execute(
        select(SyncJob.status, func.count(SyncJob.id))
        .where(SyncJob.user_id == current_user.id)
        .group_by(SyncJob.status)
    )
    counts = {_status_value(status): int(count) for status, count in result.all()}
    queued = counts.get(SyncJobStatus.QUEUED.value, 0)
    running = counts.get(SyncJobStatus.RUNNING.value, 0)
    succeeded = counts.get(SyncJobStatus.SUCCESS.value, 0)
    failed = counts.get(SyncJobStatus.FAILED.value, 0)
    return QueueOverview(
        queued=queued,
        running=running,
        succeeded=succeeded,
        failed=failed,
        total=sum(counts.values()),
    )


@router.get("", response_model=list[SyncJobRead])
async def list_jobs(
    current_user: CurrentUser,
    db: DbSession,
    status_filter: SyncJobStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=250),
) -> list[SyncJobRead]:
    query = select(SyncJob).where(SyncJob.user_id == current_user.id)
    if status_filter:
        query = query.where(SyncJob.status == status_filter.value)
    result = await db.execute(query.order_by(SyncJob.created_at.desc()).limit(limit))
    return [SyncJobRead.model_validate(item) for item in result.scalars().all()]


@router.get("/{job_id}", response_model=SyncJobRead)
async def get_job(job_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> SyncJobRead:
    result = await db.execute(
        select(SyncJob).where(SyncJob.id == job_id, SyncJob.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    return SyncJobRead.model_validate(job)


@router.post("/{job_id}/cancel", response_model=MessageResponse)
async def cancel_job(job_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> MessageResponse:
    result = await db.execute(
        select(SyncJob).where(SyncJob.id == job_id, SyncJob.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    current_status = _status_value(job.status)
    if current_status not in {SyncJobStatus.QUEUED.value, SyncJobStatus.RUNNING.value}:
        raise HTTPException(status_code=400, detail="Somente jobs pendentes ou em execução podem ser cancelados.")

    if job.celery_task_id:
        celery_app.control.revoke(job.celery_task_id, terminate=False)
    job.status = SyncJobStatus.CANCELLED
    job.message = "Cancelamento solicitado."
    job.completed_at = datetime.now(UTC)
    await db.commit()
    return MessageResponse(message="Cancelamento solicitado à fila.")
