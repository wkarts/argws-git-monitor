from __future__ import annotations

from datetime import UTC, datetime

import redis.asyncio as redis
from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.database import ping_database
from app.models.activity import SyncJob, SyncJobStatus
from app.services.worker_status import get_worker_status

router = APIRouter(tags=["Sistema"])


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    environment: str
    timestamp: datetime
    dependencies: dict[str, str] | None = None


class RuntimeStatusResponse(BaseModel):
    status: str
    version: str
    database: str
    redis: str
    worker_online: bool
    worker_count: int
    workers: list[str] = Field(default_factory=list)
    queued_jobs: int = 0
    running_jobs: int = 0
    failed_jobs: int = 0
    worker_error: str | None = None
    timestamp: datetime


async def _redis_status() -> str:
    settings = get_settings()
    client = redis.from_url(settings.redis_url, socket_timeout=2, decode_responses=True)
    try:
        await client.ping()
        return "ok"
    except Exception:
        return "error"
    finally:
        await client.aclose()


@router.get("/health/live", response_model=HealthResponse)
async def live() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        timestamp=datetime.now(UTC),
    )


@router.get("/health/ready", response_model=HealthResponse)
async def ready(response: Response) -> HealthResponse:
    settings = get_settings()
    dependencies = {
        "database": "ok" if await ping_database() else "error",
        "redis": await _redis_status(),
    }
    healthy = all(value == "ok" for value in dependencies.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="ok" if healthy else "degraded",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        timestamp=datetime.now(UTC),
        dependencies=dependencies,
    )


@router.get("/system/runtime", response_model=RuntimeStatusResponse)
async def runtime_status(current_user: CurrentUser, db: DbSession) -> RuntimeStatusResponse:
    settings = get_settings()
    database = "ok" if await ping_database() else "error"
    redis_status = await _redis_status()
    worker = await get_worker_status()

    result = await db.execute(
        select(SyncJob.status, func.count(SyncJob.id))
        .where(SyncJob.user_id == current_user.id)
        .group_by(SyncJob.status)
    )
    counts = {
        (state.value if isinstance(state, SyncJobStatus) else str(state)): int(count)
        for state, count in result.all()
    }
    healthy = database == "ok" and redis_status == "ok" and worker.online
    return RuntimeStatusResponse(
        status="ok" if healthy else "degraded",
        version=settings.app_version,
        database=database,
        redis=redis_status,
        worker_online=worker.online,
        worker_count=len(worker.workers),
        workers=list(worker.workers),
        queued_jobs=counts.get(SyncJobStatus.QUEUED.value, 0),
        running_jobs=counts.get(SyncJobStatus.RUNNING.value, 0),
        failed_jobs=counts.get(SyncJobStatus.FAILED.value, 0),
        worker_error=worker.error,
        timestamp=datetime.now(UTC),
    )
