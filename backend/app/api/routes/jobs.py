from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, or_, select

from app.api.deps import CurrentUser, DbSession
from app.models.activity import SyncJob, SyncJobStatus
from app.schemas.common import MessageResponse
from app.schemas.jobs import QueueOverview, SyncJobRead
from app.services.job_queue import create_job
from app.services.worker_status import get_worker_status, require_worker
from app.tasks.celery_app import celery_app
from app.tasks.jobs import sync_connection_task, sync_repository_task

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
    counts = {_status_value(state): int(count) for state, count in result.all()}
    worker = await get_worker_status(timeout=0.75)
    return QueueOverview(
        queued=counts.get(SyncJobStatus.QUEUED.value, 0),
        running=counts.get(SyncJobStatus.RUNNING.value, 0),
        succeeded=counts.get(SyncJobStatus.SUCCESS.value, 0),
        failed=counts.get(SyncJobStatus.FAILED.value, 0),
        cancelled=counts.get(SyncJobStatus.CANCELLED.value, 0),
        total=sum(counts.values()),
        worker_online=worker.online,
        worker_count=len(worker.workers),
        workers=list(worker.workers),
        worker_error=worker.error,
    )


@router.get("", response_model=list[SyncJobRead])
async def list_jobs(
    current_user: CurrentUser,
    db: DbSession,
    status_filter: SyncJobStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
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


@router.post("/reconcile", response_model=MessageResponse)
async def reconcile_stalled_jobs(
    current_user: CurrentUser,
    db: DbSession,
    older_than_minutes: int = Query(default=15, ge=3, le=1440),
) -> MessageResponse:
    threshold = datetime.now(UTC) - timedelta(minutes=older_than_minutes)
    result = await db.execute(
        select(SyncJob).where(
            SyncJob.user_id == current_user.id,
            SyncJob.status.in_([SyncJobStatus.QUEUED.value, SyncJobStatus.RUNNING.value]),
            or_(
                SyncJob.created_at < threshold,
                SyncJob.started_at.is_not(None) & (SyncJob.started_at < threshold),
            ),
        )
    )
    jobs = result.scalars().all()
    now = datetime.now(UTC)
    for job in jobs:
        if job.celery_task_id:
            celery_app.control.revoke(job.celery_task_id, terminate=False)
        job.status = SyncJobStatus.FAILED
        job.error = (
            "Processamento abandonado: nenhum worker confirmou a conclusão dentro do prazo. "
            "Verifique o container worker e use Repetir após corrigir a infraestrutura."
        )
        job.message = "Job reconciliado como falha operacional."
        job.completed_at = now
    await db.commit()
    return MessageResponse(message=f"{len(jobs)} job(s) travado(s) reconciliado(s).")


@router.post("/{job_id}/retry", response_model=SyncJobRead)
async def retry_job(job_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> SyncJobRead:
    result = await db.execute(
        select(SyncJob).where(SyncJob.id == job_id, SyncJob.user_id == current_user.id)
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    if _status_value(source.status) not in {
        SyncJobStatus.FAILED.value,
        SyncJobStatus.CANCELLED.value,
    }:
        raise HTTPException(status_code=400, detail="Somente jobs falhos ou cancelados podem ser repetidos.")
    try:
        await require_worker()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    job = await create_job(
        db,
        user_id=current_user.id,
        connection_id=source.connection_id,
        repository_id=source.repository_id,
        kind=f"{source.kind}.retry",
        label=f"Repetir · {source.label}",
        progress_total=source.progress_total,
        message="Aguardando worker disponível.",
    )
    await db.commit()

    if source.repository_id:
        task = sync_repository_task.delay(str(source.repository_id), str(job.id))
    elif source.connection_id:
        task = sync_connection_task.delay(str(source.connection_id), None, str(job.id))
    else:
        job.status = SyncJobStatus.FAILED
        job.error = "Job original não possui conexão ou repositório associado."
        job.completed_at = datetime.now(UTC)
        await db.commit()
        return SyncJobRead.model_validate(job)

    job.celery_task_id = task.id
    await db.commit()
    await db.refresh(job)
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
        raise HTTPException(
            status_code=400,
            detail="Somente jobs pendentes ou em execução podem ser cancelados.",
        )

    if job.celery_task_id:
        celery_app.control.revoke(job.celery_task_id, terminate=False)
    job.status = SyncJobStatus.CANCELLED
    job.message = "Cancelamento solicitado."
    job.completed_at = datetime.now(UTC)
    await db.commit()
    return MessageResponse(message="Cancelamento solicitado à fila.")
