from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import ORJSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from app.api.routes import (
    admin,
    admin_permissions,
    auth,
    backup_lifecycle,
    compliance_local,
    dashboard,
    github,
    github_diagnostics,
    github_tools,
    github_tools_v2,
    inactivity,
    jobs,
    logs,
    monitoring_api,
    notifications,
    operations,
    platform,
    realtime,
    repositories,
    repository_controls,
    storage_hub,
    system,
    webhooks,
)
from app.core.config import get_settings
from app.core.database import dispose_engine
from app.core.logging import configure_logging
from app.core.request_context import reset_request_id, set_request_id

configure_logging()
logger = logging.getLogger(__name__)
settings = get_settings()

REQUEST_COUNT = Counter(
    "argws_git_monitor_http_requests_total",
    "Quantidade de requisições HTTP",
    ["method", "route", "status"],
)
REQUEST_LATENCY = Histogram(
    "argws_git_monitor_http_request_duration_seconds",
    "Duração das requisições HTTP",
    ["method", "route"],
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info(
        "%s %s iniciado no ambiente %s",
        settings.app_name,
        settings.app_version,
        settings.app_env,
    )
    yield
    await dispose_engine()
    logger.info("Aplicação encerrada")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Central operacional de monitoramento, proteção, backup, release, "
        "manutenção e deployment de repositórios GitHub."
    ),
    default_response_class=ORJSONResponse,
    docs_url=f"{settings.api_v1_prefix}/docs",
    redoc_url=f"{settings.api_v1_prefix}/redoc",
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", "X-Request-ID", "X-API-Key"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id
    context_token = set_request_id(request_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
        route = getattr(request.scope.get("route"), "path", request.url.path)
        elapsed = time.perf_counter() - started
        REQUEST_COUNT.labels(request.method, route, str(response.status_code)).inc()
        REQUEST_LATENCY.labels(request.method, route).observe(elapsed)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response
    finally:
        reset_request_id(context_token)


@app.get("/api", include_in_schema=False)
async def api_root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "operational",
        "docs": f"{settings.api_v1_prefix}/docs",
    }


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


app.include_router(system.router, prefix=settings.api_v1_prefix)
app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(admin.router, prefix=settings.api_v1_prefix)
app.include_router(admin_permissions.router, prefix=settings.api_v1_prefix)
app.include_router(logs.router, prefix=settings.api_v1_prefix)
app.include_router(dashboard.router, prefix=settings.api_v1_prefix)
app.include_router(github.router, prefix=settings.api_v1_prefix)
app.include_router(github_diagnostics.router, prefix=settings.api_v1_prefix)
app.include_router(github_tools.router, prefix=settings.api_v1_prefix)
app.include_router(github_tools_v2.router, prefix=settings.api_v1_prefix)
app.include_router(compliance_local.router, prefix=settings.api_v1_prefix)
app.include_router(inactivity.router, prefix=settings.api_v1_prefix)
app.include_router(jobs.router, prefix=settings.api_v1_prefix)
app.include_router(repositories.router, prefix=settings.api_v1_prefix)
app.include_router(repository_controls.router, prefix=settings.api_v1_prefix)
app.include_router(operations.router, prefix=settings.api_v1_prefix)
app.include_router(platform.router, prefix=settings.api_v1_prefix)
app.include_router(storage_hub.router, prefix=settings.api_v1_prefix)
app.include_router(backup_lifecycle.router, prefix=settings.api_v1_prefix)
app.include_router(realtime.router, prefix=settings.api_v1_prefix)
app.websocket(
    f"{settings.api_v1_prefix}/realtime/ws",
    name="realtime-websocket",
)(realtime.websocket_events)
app.include_router(monitoring_api.router, prefix=settings.api_v1_prefix)
app.include_router(notifications.router, prefix=settings.api_v1_prefix)
app.include_router(webhooks.router, prefix=settings.api_v1_prefix)
