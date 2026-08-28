from __future__ import annotations

import asyncio
import re
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.api.deps import CurrentUser, DbSession
from app.models.github import Repository
from app.models.platform import BackupSnapshot, BackupStatus, StorageProvider
from app.services.backup_service import sha256_file
from app.services.storage_providers import build_storage_adapter

router = APIRouter(prefix="/storage-hub", tags=["Storage Hub"])

_DOWNLOADABLE_STATUSES = {
    BackupStatus.COMPLETED.value,
    BackupStatus.COMPLETED_WITH_WARNINGS.value,
}


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    cleaned = re.sub(r"\.{2,}", "-", cleaned)
    return cleaned.strip("-._") or "repository"


def backup_download_filename(repository: Repository | None, snapshot: BackupSnapshot) -> str:
    if repository:
        owner = _safe_segment(repository.owner)
        name = _safe_segment(repository.name)
        return f"{owner}-{name}-{snapshot.id}.tar.gz"
    return f"argws-backup-{snapshot.id}.tar.gz"


def _cleanup_download(path: Path) -> None:
    path.unlink(missing_ok=True)


@router.get("/backups/{snapshot_id}/download")
async def download_backup_snapshot(
    snapshot_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> FileResponse:
    snapshot = await db.get(BackupSnapshot, snapshot_id)
    if not snapshot or snapshot.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Snapshot não encontrado.")
    if snapshot.status not in _DOWNLOADABLE_STATUSES or not snapshot.location:
        raise HTTPException(
            status_code=409,
            detail="O snapshot ainda não está concluído e disponível para download.",
        )

    provider = await db.get(StorageProvider, snapshot.provider_id)
    if not provider or provider.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Provider do snapshot não encontrado.")
    repository = await db.get(Repository, snapshot.repository_id)

    temp = tempfile.NamedTemporaryFile(prefix="argws-backup-download-", suffix=".tar.gz", delete=False)
    temp_path = Path(temp.name)
    temp.close()

    try:
        adapter = build_storage_adapter(provider)
        await asyncio.to_thread(adapter.download, snapshot.location, temp_path)
        if not temp_path.is_file() or temp_path.stat().st_size <= 0:
            raise RuntimeError("O provider retornou um arquivo vazio.")
        checksum = await asyncio.to_thread(sha256_file, temp_path)
        if snapshot.checksum_sha256 and checksum != snapshot.checksum_sha256:
            raise HTTPException(
                status_code=409,
                detail="O SHA-256 do arquivo recuperado não confere com o snapshot. Download bloqueado.",
            )
    except HTTPException:
        _cleanup_download(temp_path)
        raise
    except Exception as exc:
        _cleanup_download(temp_path)
        raise HTTPException(
            status_code=503,
            detail=(
                "Não foi possível recuperar o arquivo do provider de backup. "
                "Teste o storage e tente novamente."
            ),
        ) from exc

    filename = backup_download_filename(repository, snapshot)
    return FileResponse(
        path=temp_path,
        filename=filename,
        media_type="application/gzip",
        headers={
            "X-ARGWS-Backup-SHA256": checksum,
            "Cache-Control": "private, no-store",
        },
        background=BackgroundTask(_cleanup_download, temp_path),
    )
