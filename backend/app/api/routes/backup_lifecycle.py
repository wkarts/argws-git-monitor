from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.github import GitHubConnection, Repository
from app.models.platform import StorageProvider
from app.services.job_queue import create_job
from app.services.worker_status import require_worker
from app.tasks.backup_lifecycle import complete_backup_lifecycle_task

router = APIRouter(prefix="/backup-lifecycle", tags=["Backup Lifecycle"])


class CompleteBackupRequest(BaseModel):
    provider_id: uuid.UUID
    delete_after_backup: bool = False
    confirmation: str | None = None


async def _owned_repository(
    db: DbSession,
    repository_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Repository:
    repository = (
        await db.execute(
            select(Repository)
            .join(GitHubConnection, Repository.connection_id == GitHubConnection.id)
            .where(
                Repository.id == repository_id,
                GitHubConnection.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if not repository:
        raise HTTPException(status_code=404, detail="Repositório não encontrado.")
    return repository


@router.post("/{repository_id}/complete")
async def queue_complete_backup(
    repository_id: uuid.UUID,
    payload: CompleteBackupRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> dict[str, Any]:
    repository = await _owned_repository(db, repository_id, current_user.id)
    provider = await db.get(StorageProvider, payload.provider_id)
    if not provider or provider.user_id != current_user.id or not provider.enabled:
        raise HTTPException(status_code=404, detail="Provider de backup não encontrado ou desativado.")

    if payload.delete_after_backup:
        expected = f"BACKUP E EXCLUIR {repository.full_name}"
        if payload.confirmation != expected:
            raise HTTPException(
                status_code=422,
                detail=f"Confirmação inválida. Digite exatamente: {expected}",
            )

    try:
        await require_worker()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail="Worker indisponível; o backup não foi iniciado e nada será excluído.",
        ) from exc

    job = await create_job(
        db,
        user_id=current_user.id,
        connection_id=repository.connection_id,
        repository_id=repository.id,
        kind=(
            "repository.backup.complete_delete"
            if payload.delete_after_backup
            else "repository.backup.complete"
        ),
        label=(
            f"Backup completo + exclusão · {repository.full_name}"
            if payload.delete_after_backup
            else f"Backup completo · {repository.full_name}"
        ),
        progress_total=8,
        message="Backup completo aguardando worker; exclusão só ocorre após validação.",
    )
    await db.commit()
    try:
        task = complete_backup_lifecycle_task.delay(
            str(job.id),
            {
                "user_id": str(current_user.id),
                "repository_id": str(repository.id),
                "provider_id": str(provider.id),
                "delete_after_backup": payload.delete_after_backup,
            },
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Não foi possível enviar o backup ao worker; nada foi excluído.",
        ) from exc
    job.celery_task_id = task.id
    await db.commit()
    return {
        "job_id": str(job.id),
        "task_id": task.id,
        "repository": repository.full_name,
        "provider": provider.name,
        "delete_after_backup": payload.delete_after_backup,
        "status": "queued",
        "safety": "A exclusão remota só acontece após snapshot primário + exportação completa possuírem checksum SHA-256.",
    }
