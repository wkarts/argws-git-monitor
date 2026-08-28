from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models.github import GitHubConnection, Repository
from app.models.platform import BackupPolicy, BackupSnapshot, BackupStatus, StorageProvider
from app.services.internal_object_store import (
    InternalObjectStoreError,
    bucket_status,
    delete_empty_bucket,
    ensure_bucket,
    probe,
)
from app.services.internal_storage import (
    create_internal_bucket_provider,
    default_backup_provider,
    ensure_internal_storage_providers,
    is_managed_internal_provider,
    is_system_internal_provider,
)
from app.services.job_queue import create_job
from app.services.storage_providers import build_storage_adapter
from app.services.worker_status import require_worker
from app.tasks.platform import backup_task
from app.tasks.storage_hub import copy_snapshot_task

logger = logging.getLogger(__name__)
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


class InternalBucketCreate(BaseModel):
    name: str = Field(min_length=3, max_length=32)


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


def _provider_payload(
    provider: StorageProvider,
    *,
    storage_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = provider.config or {}
    storage_class = str(config.get("storage_class") or provider.kind)
    state = storage_state or {}
    return {
        "id": str(provider.id),
        "name": provider.name,
        "kind": provider.kind,
        "storage_class": storage_class,
        "managed": is_managed_internal_provider(provider),
        "system_default": is_system_internal_provider(provider),
        "role": config.get("role"),
        "bucket": config.get("bucket"),
        "bucket_alias": config.get("bucket_alias"),
        "base_path": config.get("base_path") if is_managed_internal_provider(provider) else None,
        "enabled": provider.enabled,
        "secret_hint": provider.secret_hint,
        "available": state.get("available"),
        "has_objects": state.get("has_objects"),
        "engine": state.get("engine"),
        "degraded": bool(state.get("degraded")),
        "minio_available": state.get("minio_available"),
        "fallback_available": state.get("fallback_available"),
        "storage_error": state.get("error"),
    }


async def _ensure_internal_bucket(provider: StorageProvider) -> dict[str, Any]:
    config = provider.config or {}
    if not (
        is_managed_internal_provider(provider)
        and config.get("storage_class") == "internal_s3"
        and config.get("bucket")
    ):
        return {}
    try:
        await asyncio.to_thread(ensure_bucket, str(config["bucket"]))
        return await asyncio.to_thread(bucket_status, str(config["bucket"]))
    except Exception as exc:
        logger.warning(
            "Storage interno indisponível: provider=%s error_type=%s",
            provider.id,
            type(exc).__name__,
        )
        return {
            "available": False,
            "has_objects": None,
            "engine": "unavailable",
            "degraded": True,
            "minio_available": False,
            "fallback_available": False,
            "error": "Storage interno indisponível: MinIO e contingência local falharam.",
        }


async def _providers_with_state(
    providers: list[StorageProvider],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for provider in providers:
        state: dict[str, Any] = {}
        if (provider.config or {}).get("storage_class") == "internal_s3":
            state = await _ensure_internal_bucket(provider)
        elif (provider.config or {}).get("storage_class") == "internal_local":
            try:
                details = await asyncio.to_thread(build_storage_adapter(provider).test)
                state = {
                    "available": bool(details.get("writable", True)),
                    "has_objects": None,
                    "engine": "local",
                    "degraded": False,
                    "fallback_available": True,
                }
            except Exception:
                state = {
                    "available": False,
                    "has_objects": None,
                    "engine": "unavailable",
                    "degraded": True,
                    "fallback_available": False,
                    "error": "Staging local indisponível.",
                }
        result.append(_provider_payload(provider, storage_state=state))
    return result


@router.get("/overview")
async def storage_overview(
    current_user: CurrentUser,
    db: DbSession,
) -> dict[str, Any]:
    # Os providers são garantidos mesmo quando o MinIO ainda não faz parte da
    # topologia instalada. O adapter interno usa /data/backups como contingência.
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
    provider_payloads = await _providers_with_state(providers)

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
    repository_count = int(
        await db.scalar(
            select(func.count(Repository.id))
            .join(GitHubConnection, Repository.connection_id == GitHubConnection.id)
            .where(
                GitHubConnection.user_id == current_user.id,
                Repository.monitoring_enabled.is_(True),
            )
        )
        or 0
    )

    try:
        storage_state = await asyncio.to_thread(probe)
    except Exception as exc:
        logger.warning("Object storage interno não respondeu: %s", type(exc).__name__)
        storage_state = {
            "available": False,
            "engine": "unavailable",
            "degraded": True,
            "minio_available": False,
            "fallback_available": False,
            "error": "Storage interno indisponível.",
        }

    return {
        "providers": provider_payloads,
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
            "repositories": repository_count,
        },
        "internal_storage": {
            "object_store": "ARGWS Object Storage",
            "engine": storage_state.get("engine") or "unavailable",
            "available": bool(storage_state.get("available")),
            "degraded": bool(storage_state.get("degraded")),
            "minio_available": bool(storage_state.get("minio_available")),
            "fallback_available": bool(storage_state.get("fallback_available")),
            "error": storage_state.get("error"),
            "endpoint": storage_state.get("endpoint"),
            "fallback_path": storage_state.get("fallback_path"),
            "local_staging": "Armazenamento local persistente",
            "deployment_manifest_required": False,
        },
    }


@router.post("/internal-buckets", status_code=status.HTTP_201_CREATED)
async def create_internal_bucket(
    payload: InternalBucketCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> dict[str, Any]:
    _require(current_user, "backup.providers.manage")
    try:
        provider = await create_internal_bucket_provider(
            db,
            user_id=current_user.id,
            alias=payload.name,
        )
        config = provider.config or {}
        await asyncio.to_thread(ensure_bucket, str(config["bucket"]))
        state = await asyncio.to_thread(bucket_status, str(config["bucket"]))
        await db.commit()
        await db.refresh(provider)
        return _provider_payload(provider, storage_state=state)
    except InternalObjectStoreError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        logger.warning("Falha ao criar bucket interno: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Storage interno indisponível; MinIO e contingência local não aceitaram o bucket.",
        ) from exc


@router.post("/internal-buckets/{provider_id}/test")
async def test_internal_bucket(
    provider_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> dict[str, Any]:
    provider = await db.get(StorageProvider, provider_id)
    if (
        not provider
        or provider.user_id != current_user.id
        or not is_managed_internal_provider(provider)
        or (provider.config or {}).get("storage_class") != "internal_s3"
    ):
        raise HTTPException(status_code=404, detail="Bucket interno não encontrado.")
    state = await _ensure_internal_bucket(provider)
    if state.get("available") is False:
        raise HTTPException(status_code=503, detail=str(state.get("error") or "Bucket indisponível."))
    return {"ok": True, **state}


@router.delete("/internal-buckets/{provider_id}", status_code=204)
async def remove_internal_bucket(
    provider_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> Response:
    _require(current_user, "backup.providers.manage")
    provider = await db.get(StorageProvider, provider_id)
    if (
        not provider
        or provider.user_id != current_user.id
        or not is_managed_internal_provider(provider)
        or (provider.config or {}).get("storage_class") != "internal_s3"
    ):
        raise HTTPException(status_code=404, detail="Bucket interno não encontrado.")
    if is_system_internal_provider(provider):
        raise HTTPException(
            status_code=409,
            detail="O bucket principal do sistema não pode ser excluído. Crie e remova buckets adicionais livremente.",
        )

    snapshots = int(
        await db.scalar(
            select(func.count(BackupSnapshot.id)).where(BackupSnapshot.provider_id == provider.id)
        )
        or 0
    )
    policies = int(
        await db.scalar(select(func.count(BackupPolicy.id)).where(BackupPolicy.provider_id == provider.id))
        or 0
    )
    if snapshots or policies:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Bucket em uso por {snapshots} snapshot(s) e {policies} política(s). "
                "Remova ou mova essas referências antes da exclusão."
            ),
        )

    bucket = str((provider.config or {}).get("bucket") or "")
    try:
        await asyncio.to_thread(delete_empty_bucket, bucket)
    except InternalObjectStoreError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.warning("Falha ao excluir bucket interno: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Storage interno indisponível.") from exc

    await db.delete(provider)
    await db.commit()
    return Response(status_code=204)


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

    if (provider.config or {}).get("storage_class") == "internal_s3":
        state = await _ensure_internal_bucket(provider)
        if state.get("available") is False:
            raise HTTPException(status_code=503, detail=str(state.get("error")))
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

    if (target.config or {}).get("storage_class") == "internal_s3":
        state = await _ensure_internal_bucket(target)
        if state.get("available") is False:
            raise HTTPException(status_code=503, detail=str(state.get("error")))
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
