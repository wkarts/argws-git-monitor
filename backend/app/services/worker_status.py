from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from app.tasks.celery_app import celery_app


@dataclass(slots=True, frozen=True)
class WorkerStatus:
    online: bool
    workers: tuple[str, ...]
    error: str | None = None


def _ping_workers(timeout: float) -> WorkerStatus:
    try:
        replies = celery_app.control.ping(timeout=timeout) or []
        workers: list[str] = []
        for reply in replies:
            if not isinstance(reply, dict):
                continue
            workers.extend(str(name) for name in reply)
        unique = tuple(sorted(set(workers)))
        return WorkerStatus(online=bool(unique), workers=unique)
    except Exception as exc:  # pragma: no cover - depende do broker/runtime
        return WorkerStatus(online=False, workers=(), error=str(exc)[:500])


async def get_worker_status(timeout: float = 1.5) -> WorkerStatus:
    return await asyncio.to_thread(_ping_workers, timeout)


async def require_worker() -> WorkerStatus:
    status = await get_worker_status()
    if not status.online:
        detail = status.error or "nenhum worker respondeu ao ping"
        raise RuntimeError(f"Worker Celery indisponível: {detail}")
    return status


def status_payload(status: WorkerStatus) -> dict[str, Any]:
    return {
        "online": status.online,
        "workers": list(status.workers),
        "worker_count": len(status.workers),
        "error": status.error,
    }
