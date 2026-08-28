from __future__ import annotations

import asyncio
import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models.github import GitHubConnection, Repository
from app.models.platform import BackupSnapshot, BackupStatus, StorageProvider
from app.services.internal_storage import (
    default_backup_provider,
    ensure_internal_storage_providers,
    is_managed_internal_provider,
)
from app.services.job_queue import create_job
from app.services.storage_providers import build_storage_adapter
from app.services.worker_status import require_worker
from app.tasks.platform import backup_task
from app.tasks.storage_hub import copy_snapshot_task

router = APIRouter(prefix="/storage-hub", tags=["Storage Hub"])


class ManagedBackupRequest(BaseModel):
    repository_id: uuid.UUID
    provider_id: uuid.UUID | None = None
    backup_type: Literal[
        "full", "default_branch", "selected_branches", "all_branches", "releases_only"
    ] = "full"
    branches: list[str] = Field(default_factory=list)
    permanent: bool = False


class SnapshotCopyRequest(BaseModel):
    provider_id: uuid.UUID


def _allowed(user: CurrentUser, permission: str) -> bool:
    if user.is_superuser:
        return True
    permissions = (user.preferences or {}).get("permissions") or []
    return permission in permissions or "operations.*" in permissions


def _require(user: CurrentUser, permission: str) -> None:
    if not _allowed(user, permission):
        raise HTTPException(status_code=403, detail=f"Permissão necessária: {permission}")


async def _owned_repository(
    db: DbSession,
    *,
    repository_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Repository:
    repository = (
        await db.execute(
            select(Repository)
            .join(GitHubConnection, Repository.connection_id == GitHubConnection.id)
            .where(Repository.id == repository_id, GitHubConnection.user_id == user_id)
        )
    ).scalar_one_or_none()
    if not repository:
        raise HTTPException(status_code=404, detail="Repositório não encontrado.")
    return repository


def _provider_payload(provider: StorageProvider) -> dict[str, Any]:
    config = provider.config or {}
    storage_class = str(config.get("storage_class") or provider.kind)
    return {
        "id": str(provider.id),
        "name": provider.name,
        "kind": provider.kind,
        "storage_class": storage_class,
        "managed": is_managed_internal_provider(provider),
        "role": config.get("role"),
        "bucket": config.get("bucket"),
        "base_path": config.get("base_path") if is_managed_internal_provider(provider) else None,
        "enabled": provider.enabled,
        "secret_hint": provider.secret_hint,
    }


@router.get("/overview")
async def storage_overview(
    current_user: CurrentUser,
    db: DbSession,
) -> dict[str, Any]:
    await ensure_internal_storage_providers(db, user_id=current_user.id)
    await db.commit()

    providers = list(
        (
            await db.execute(
                select(StorageProvider)
                .where(StorageProvider.user_id == current_user.id)
                .order_by(StorageProvider.name)
            )
        ).scalars().all()
    )
    total_snapshots = int(
        await db.scalar(
            select(func.count(BackupSnapshot.id)).where(BackupSnapshot.user_id == current_user.id)
        )
        or 0
    )
    completed = int(
        await db.scalar(
            select(func.count(BackupSnapshot.id)).where(
                BackupSnapshot.user_id == current_user.id,
                BackupSnapshot.status.in_(
                    [BackupStatus.COMPLETED.value, BackupStatus.COMPLETED_WITH_WARNINGS.value]
                ),
            )
        )
        or 0
    )
    failed = int(
        await db.scalar(
            select(func.count(BackupSnapshot.id)).where(
                BackupSnapshot.user_id == current_user.id,
                BackupSnapshot.status == BackupStatus.FAILED.value,
            )
        )
        or 0
    )
    stored_bytes = int(
        await db.scalar(
            select(func.coalesce(func.sum(BackupSnapshot.size_bytes), 0)).where(
                BackupSnapshot.user_id == current_user.id,
                BackupSnapshot.status.in_(
                    [BackupStatus.COMPLETED.value, BackupStatus.COMPLETED_WITH_WARNINGS.value]
                ),
            )
        )
        or 0
    )
    last_snapshot = (
        await db.execute(
            select(BackupSnapshot)
            .where(BackupSnapshot.user_id == current_user.id)
            .order_by(BackupSnapshot.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    return {
        "providers": [_provider_payload(provider) for provider in providers],
        "stats": {
            "snapshots": total_snapshots,
            "completed": completed,
            "failed": failed,
            "stored_bytes": stored_bytes,
            "last_status": last_snapshot.status if last_snapshot else None,
            "last_at": (
                (last_snapshot.completed_at or last_snapshot.created_at).isoformat()
                if last_snapshot
                else None
            ),
        },
        "internal_storage": {
            "object_store": "S3 interno (bucket-style, filesystem-backed)",
            "local_staging": "Armazenamento local persistente",
            "deployment_manifest_required": False,
        },
    }


@router.post("/backups/run")
async def run_managed_backup(
    payload: ManagedBackupRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> dict[str, Any]:
    _require(current_user, "backup.execute")
    repository = await _owned_repository(
        db, repository_id=payload.repository_id, user_id=current_user.id
    )
    await ensure_internal_storage_providers(db, user_id=current_user.id)
    provider = (
        await db.get(StorageProvider, payload.provider_id)
        if payload.provider_id
        else await default_backup_provider(db, user_id=current_user.id)
    )
    if not provider or provider.user_id != current_user.id or not provider.enabled:
        raise HTTPException(status_code=404, detail="Provider de backup não encontrado ou desativado.")

    try:
        await asyncio.to_thread(build_storage_adapter(provider).test)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                f"O destino {provider.name} não passou no teste de gravação/conexão. "
                "Corrija o provider antes de executar o backup."
            ),
        ) from exc

    try:
        await require_worker()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail="Worker indisponível. O backup não foi iniciado.",
        ) from exc

    job = await create_job(
        db,
        user_id=current_user.id,
        repository_id=repository.id,
        connection_id=repository.connection_id,
        kind="repository.backup.managed",
        label=f"Backup · {repository.full_name} · {provider.name}",
        progress_total=5,
        message="Destino validado; backup aguardando worker.",
    )
    await db.commit()
    try:
        task = backup_task.delay(
            str(job.id),
            {
                "user_id": str(current_user.id),
                "repository_id": str(repository.id),
                "provider_id": str(provider.id),
                "backup_type": payload.backup_type,
                "branches": payload.branches,
                "permanent": payload.permanent,
            },
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Não foi possível enviar o backup ao worker.",
        ) from exc
    job.celery_task_id = task.id
    await db.commit()
    return {
        "job_id": str(job.id),
        "task_id": task.id,
        "provider": _provider_payload(provider),
        "status": "queued",
    }


@router.post("/backups/{snapshot_id}/copy")
async def copy_snapshot(
    snapshot_id: uuid.UUID,
    payload: SnapshotCopyRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> dict[str, Any]:
    _require(current_user, "backup.execute")
    source = await db.get(BackupSnapshot, snapshot_id)
    target = await db.get(StorageProvider, payload.provider_id)
    if not source or source.user_id != current_user.id or not source.location:
        raise HTTPException(status_code=404, detail="Snapshot não encontrado ou incompleto.")
    if not target or target.user_id != current_user.id or not target.enabled:
        raise HTTPException(status_code=404, detail="Provider de destino não encontrado.")
    if source.provider_id == target.id:
        raise HTTPException(status_code=409, detail="O snapshot já está neste provider.")

    try:
        await asyncio.to_thread(build_storage_adapter(target).test)
        await require_worker()
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail="O provider de destino ou o worker não está operacional.",
        ) from exc

    repository = await db.get(Repository, source.repository_id)
    job = await create_job(
        db,
        user_id=current_user.id,
        repository_id=source.repository_id,
        connection_id=repository.connection_id if repository else None,
        kind="backup.snapshot.copy",
        label=f"Copiar backup · {target.name}",
        progress_total=4,
        message="Cópia do snapshot aguardando worker.",
    )
    await db.commit()
    task = copy_snapshot_task.delay(
        str(job.id),
        {
            "user_id": str(current_user.id),
            "snapshot_id": str(source.id),
            "provider_id": str(target.id),
        },
    )
    job.celery_task_id = task.id
    await db.commit()
    return {"job_id": str(job.id), "task_id": task.id, "status": "queued"}
