from __future__ import annotations

import asyncio
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.database import dispose_engine, session_scope
from app.models.platform import BackupSnapshot, BackupStatus, StorageProvider
from app.services.backup_service import sha256_file
from app.services.job_queue import (
    mark_job_failed,
    mark_job_running,
    mark_job_success,
    update_job_progress,
)
from app.services.storage_providers import build_storage_adapter
from app.tasks.celery_app import celery_app


def run_async(coro):
    async def runner():
        try:
            return await coro
        finally:
            await dispose_engine()

    return asyncio.run(runner())


@celery_app.task(name="storage.copy_snapshot", bind=True, max_retries=2)
def copy_snapshot_task(self, job_id: str, params: dict[str, Any]):
    async def execute() -> dict[str, Any]:
        await mark_job_running(job_id, message="Preparando cópia do snapshot para o provider externo.")
        await update_job_progress(job_id, current=1, total=4, message="Validando snapshot e providers.")
        user_id = uuid.UUID(params["user_id"])
        snapshot_id = uuid.UUID(params["snapshot_id"])
        provider_id = uuid.UUID(params["provider_id"])

        async with session_scope() as session:
            source = await session.get(BackupSnapshot, snapshot_id)
            target_provider = await session.get(StorageProvider, provider_id)
            if not source or source.user_id != user_id or not source.location:
                raise RuntimeError("Snapshot de origem não encontrado ou incompleto.")
            if not target_provider or target_provider.user_id != user_id or not target_provider.enabled:
                raise RuntimeError("Provider de destino não encontrado ou desativado.")
            source_provider = await session.get(StorageProvider, source.provider_id)
            if not source_provider or source_provider.user_id != user_id:
                raise RuntimeError("Provider de origem indisponível.")
            if source_provider.id == target_provider.id:
                raise RuntimeError("Origem e destino são o mesmo provider.")

            await update_job_progress(job_id, current=2, total=4, message="Baixando e validando SHA-256 da origem.")
            with tempfile.TemporaryDirectory(prefix="argws-storage-copy-") as temp:
                local_file = Path(temp) / "snapshot.tar.gz"
                build_storage_adapter(source_provider).download(source.location, local_file)
                checksum = sha256_file(local_file)
                if source.checksum_sha256 and checksum != source.checksum_sha256:
                    raise RuntimeError("Checksum do snapshot de origem não confere; cópia abortada.")

                await update_job_progress(job_id, current=3, total=4, message="Enviando snapshot ao provider de destino.")
                repository = source.repository
                remote_key = (
                    f"replicas/{repository.owner}/{repository.name}/"
                    f"{datetime.now(UTC).strftime('%Y/%m/%d')}/"
                    f"{source.id}-{local_file.name}"
                )
                location = build_storage_adapter(target_provider).upload(local_file, remote_key)

            manifest = dict(source.manifest or {})
            manifest["replica_of"] = str(source.id)
            manifest["replicated_at"] = datetime.now(UTC).isoformat()
            manifest["source_provider_id"] = str(source.provider_id)
            manifest["provider"] = {
                "id": str(target_provider.id),
                "name": target_provider.name,
                "kind": target_provider.kind,
            }
            replica = BackupSnapshot(
                user_id=user_id,
                policy_id=None,
                repository_id=source.repository_id,
                provider_id=target_provider.id,
                job_id=uuid.UUID(job_id),
                backup_type=source.backup_type,
                status=BackupStatus.COMPLETED.value,
                location=location,
                manifest=manifest,
                checksum_sha256=checksum,
                size_bytes=source.size_bytes,
                object_count=source.object_count,
                permanent=source.permanent,
                error=None,
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                created_at=datetime.now(UTC),
            )
            session.add(replica)
            await session.flush()
            result = {
                "snapshot_id": str(replica.id),
                "replica_of": str(source.id),
                "provider_id": str(target_provider.id),
                "provider": target_provider.name,
                "location": location,
                "checksum_sha256": checksum,
            }

        await update_job_progress(job_id, current=4, total=4, message="Cópia validada e concluída.")
        await mark_job_success(job_id, result=result, message="Snapshot copiado com integridade validada.")
        return result

    try:
        return run_async(execute())
    except Exception as exc:
        run_async(mark_job_failed(job_id, error=str(exc)))
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=min(60 * (self.request.retries + 1), 180))
        raise
