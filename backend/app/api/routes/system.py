from __future__ import annotations

from datetime import UTC, datetime

import redis.asyncio as redis
from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.database import ping_database

router = APIRouter(tags=["Sistema"])


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    environment: str
    timestamp: datetime
    dependencies: dict[str, str] | None = None


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
    dependencies: dict[str, str] = {}
    dependencies["database"] = "ok" if await ping_database() else "error"

    redis_client = redis.from_url(settings.redis_url, socket_timeout=2, decode_responses=True)
    try:
        await redis_client.ping()
        dependencies["redis"] = "ok"
    except Exception:
        dependencies["redis"] = "error"
    finally:
        await redis_client.aclose()

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
