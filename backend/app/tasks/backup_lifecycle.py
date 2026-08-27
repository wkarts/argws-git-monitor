from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.database import dispose_engine, session_scope
from app.core.encryption import EncryptionService
from app.models.github import GitHubConnection, Repository
from app.services.complete_backup_service import create_complete_backup
from app.services.github_client import GitHubClient
from app.services.job_queue import (
    mark_job_failed,
    mark_job_running,
    mark_job_success,
    update_job_progress,
)
from app.services.realtime import publish_event
from app.tasks.celery_app import celery_app


def run_async(coro):
    async def runner():
        try:
            return await coro
        finally:
            await dispose_engine()

    return asyncio.run(runner())


@celery_app.task(name="backup.complete_lifecycle", bind=True, max_retries=1)
def complete_backup_lifecycle_task(self, job_id: str, params: dict[str, Any]):
    async def execute():
        user_id = uuid.UUID(params["user_id"])
        repository_id = uuid.UUID(params["repository_id"])
        provider_id = uuid.UUID(params["provider_id"])
        delete_after = bool(params.get("delete_after_backup", False))

        await mark_job_running(job_id, message="Iniciando backup completo e exportação GitHub.")
        await update_job_progress(
            job_id,
            current=1,
            total=8,
            message="Criando mirror Git, bundle, LFS, submódulos e releases.",
        )
        async with session_scope() as session:
            repository = await session.get(Repository, repository_id)
            if not repository:
                raise RuntimeError("Repositório não encontrado.")
            full_name = repository.full_name
            snapshot = await create_complete_backup(
                session,
                user_id=user_id,
                repository_id=repository_id,
                provider_id=provider_id,
                permanent=True,
                job_id=uuid.UUID(job_id),
            )
            complete_export = (snapshot.manifest or {}).get("github_complete_export") or {}
            if not snapshot.checksum_sha256 or not complete_export.get("checksum_sha256"):
                raise RuntimeError("Backup não possui os dois checksums necessários para validação.")

            await update_job_progress(
                job_id,
                current=6,
                total=8,
                message="Snapshot Git e exportação completa validados por SHA-256.",
            )

            deleted = False
            if delete_after:
                connection = await session.get(GitHubConnection, repository.connection_id)
                if not connection or connection.user_id != user_id or not connection.token_encrypted:
                    raise RuntimeError("Conexão GitHub inválida; exclusão cancelada e backup preservado.")
                token = EncryptionService().decrypt(connection.token_encrypted)
                async with GitHubClient(token, api_url=connection.api_url) as client:
                    await client.delete_repository(repository.full_name)
                now = datetime.now(UTC)
                extra = dict(repository.extra_data or {})
                extra["blacklist"] = {
                    "at": now.isoformat(),
                    "reason": "Repositório removido do GitHub após backup completo validado.",
                    "github_id": repository.github_id,
                    "full_name": repository.full_name,
                }
                extra["remote_deleted"] = {
                    "at": now.isoformat(),
                    "snapshot_id": str(snapshot.id),
                    "primary_checksum_sha256": snapshot.checksum_sha256,
                    "complete_export_checksum_sha256": complete_export.get("checksum_sha256"),
                }
                repository.extra_data = extra
                repository.monitoring_enabled = False
                repository.sync_error = None
                deleted = True

            result = {
                "repository_id": str(repository.id),
                "repository": full_name,
                "snapshot_id": str(snapshot.id),
                "status": snapshot.status,
                "primary_location": snapshot.location,
                "primary_checksum_sha256": snapshot.checksum_sha256,
                "complete_export_location": complete_export.get("location"),
                "complete_export_checksum_sha256": complete_export.get("checksum_sha256"),
                "size_bytes": snapshot.size_bytes,
                "object_count": snapshot.object_count,
                "deleted_from_github": deleted,
                "warnings": (snapshot.manifest or {}).get("warnings") or [],
            }

        await update_job_progress(
            job_id,
            current=8,
            total=8,
            message=(
                "Backup validado e repositório removido com tombstone preservado."
                if delete_after
                else "Backup completo validado e preservado."
            ),
        )
        await mark_job_success(job_id, result=result, message="Ciclo de backup completo concluído.")
        try:
            await publish_event(
                user_id,
                "repository.backup_complete",
                result,
                repository_id=repository_id,
            )
        except Exception:
            pass
        return result

    try:
        return run_async(execute())
    except Exception as exc:
        run_async(mark_job_failed(job_id, error=str(exc), message="Backup completo não foi concluído; exclusão não executada."))
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=60)
        raise
