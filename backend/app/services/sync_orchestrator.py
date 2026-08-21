from __future__ import annotations

import asyncio
import uuid
from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import session_scope
from app.models.activity import SyncJob
from app.models.github import Repository
from app.services.github_sync import sync_connection, sync_repository


async def _set_progress(
    job_id: uuid.UUID | None,
    *,
    current: int | None = None,
    total: int | None = None,
    message: str | None = None,
) -> None:
    if job_id is None:
        return
    async with session_scope() as session:
        job = await session.get(SyncJob, job_id)
        if not job:
            return
        if current is not None:
            job.progress_current = current
        if total is not None:
            job.progress_total = total
        if message is not None:
            job.message = message


async def sync_connection_with_progress(
    connection_id: uuid.UUID | str,
    *,
    selected_github_ids: set[int] | None = None,
    job_id: uuid.UUID | str | None = None,
) -> dict[str, Any]:
    """Descobre o catálogo e sincroniza repositórios com progresso observável.

    Um único job representa uma seleção inteira, evitando centenas de mensagens
    pendentes para uma única ação do usuário.
    """

    connection_uuid = uuid.UUID(str(connection_id))
    job_uuid = uuid.UUID(str(job_id)) if job_id else None
    discovery = await sync_connection(
        connection_uuid,
        selected_github_ids=selected_github_ids,
        full_sync=False,
    )

    async with session_scope() as session:
        query = select(Repository.id, Repository.full_name).where(
            Repository.connection_id == connection_uuid,
            Repository.monitoring_enabled.is_(True),
            Repository.archived.is_(False),
            Repository.disabled.is_(False),
        )
        if selected_github_ids is not None:
            query = query.where(Repository.github_id.in_(selected_github_ids))
        rows = (await session.execute(query.order_by(Repository.full_name.asc()))).all()

    total = len(rows)
    await _set_progress(
        job_uuid,
        current=0,
        total=total,
        message=f"0/{total} repositório(s) sincronizado(s).",
    )
    if not rows:
        return {"repositories": discovery["repositories"], "synced": 0, "errors": 0}

    settings = get_settings()
    semaphore = asyncio.Semaphore(max(1, settings.github_concurrency))
    progress_lock = asyncio.Lock()
    progress = 0
    synced = 0
    errors: list[dict[str, str]] = []

    async def process(repository_id: uuid.UUID, full_name: str) -> None:
        nonlocal progress, synced
        async with semaphore:
            try:
                await sync_repository(repository_id)
                synced += 1
            except Exception as exc:  # erro fica registrado também no repositório
                errors.append({"repository": full_name, "error": str(exc)[:500]})
            finally:
                async with progress_lock:
                    progress += 1
                    await _set_progress(
                        job_uuid,
                        current=progress,
                        total=total,
                        message=(
                            f"{progress}/{total} processado(s) · "
                            f"{synced} sucesso · {len(errors)} erro(s)."
                        ),
                    )

    await asyncio.gather(*(process(repository_id, full_name) for repository_id, full_name in rows))
    return {
        "repositories": discovery["repositories"],
        "synced": synced,
        "errors": len(errors),
        "failed_repositories": errors[:100],
    }
