from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.core.encryption import EncryptionService
from app.models.activity import Notification, SyncJob, SyncJobStatus
from app.models.api_access import ApiAccessKey
from app.models.github import GitHubConnection, Repository
from app.services.api_access import (
    API_SCOPES,
    ApiAccessError,
    authenticate_api_token,
    generate_api_token,
    normalize_scopes,
    require_scope,
    revoke_user_api_key,
)
from app.services.github_client import GitHubAPIError, GitHubClient
from app.services.worker_status import get_worker_status, status_payload

router = APIRouter(tags=["Monitoring API"])


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    scopes: list[str]
    expires_at: datetime | None = None


class ExternalActionsUpdate(BaseModel):
    enabled: bool
    cancel_in_progress: bool = True


def _api_key_read(key: ApiAccessKey) -> dict[str, object]:
    return {
        "id": str(key.id),
        "name": key.name,
        "prefix": key.prefix,
        "scopes": list(key.scopes or []),
        "enabled": key.enabled,
        "expires_at": key.expires_at.isoformat() if key.expires_at else None,
        "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
        "created_at": key.created_at.isoformat(),
    }


async def external_api_key(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> ApiAccessKey:
    token = (x_api_key or "").strip()
    if not token and authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer":
            token = value.strip()
    if not token:
        raise HTTPException(status_code=401, detail="Chave de API necessária.")
    try:
        key = await authenticate_api_token(db, token)
    except ApiAccessError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    await db.commit()
    return key


ExternalApiKey = Annotated[ApiAccessKey, Depends(external_api_key)]


def _scope(key: ApiAccessKey, scope: str) -> None:
    try:
        require_scope(key, scope)
    except ApiAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


async def _overview(db: DbSession, user_id: uuid.UUID) -> dict[str, object]:
    monitored = int(
        (
            await db.execute(
                select(func.count(Repository.id))
                .join(GitHubConnection)
                .where(
                    GitHubConnection.user_id == user_id,
                    Repository.monitoring_enabled.is_(True),
                )
            )
        ).scalar_one()
    )
    ignored = int(
        (
            await db.execute(
                select(func.count(Repository.id))
                .join(GitHubConnection)
                .where(
                    GitHubConnection.user_id == user_id,
                    Repository.monitoring_enabled.is_(False),
                )
            )
        ).scalar_one()
    )
    active_jobs = int(
        (
            await db.execute(
                select(func.count(SyncJob.id)).where(
                    SyncJob.user_id == user_id,
                    SyncJob.status.in_([SyncJobStatus.QUEUED, SyncJobStatus.RUNNING]),
                )
            )
        ).scalar_one()
    )
    unread = int(
        (
            await db.execute(
                select(func.count(Notification.id)).where(
                    Notification.user_id == user_id,
                    Notification.read_at.is_(None),
                )
            )
        ).scalar_one()
    )
    health_rows = (
        await db.execute(
            select(Repository.health_status, func.count(Repository.id))
            .join(GitHubConnection)
            .where(
                GitHubConnection.user_id == user_id,
                Repository.monitoring_enabled.is_(True),
            )
            .group_by(Repository.health_status)
        )
    ).all()
    health = {
        (item.value if hasattr(item, "value") else str(item)): int(count)
        for item, count in health_rows
    }
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "repositories": {"monitored": monitored, "ignored": ignored, "health": health},
        "jobs": {"active": active_jobs},
        "notifications": {"unread": unread},
        "realtime": {"transport": "websocket", "bus": "redis-pubsub"},
    }


@router.get("/monitoring/overview")
async def internal_overview(current_user: CurrentUser, db: DbSession) -> dict[str, object]:
    return await _overview(db, current_user.id)


@router.get("/monitoring/runtime")
async def internal_runtime(current_user: CurrentUser, db: DbSession) -> dict[str, object]:
    del current_user, db
    worker = await get_worker_status(timeout=1.0)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "api": {"online": True},
        "worker": status_payload(worker),
        "realtime": {"online": True, "transport": "websocket", "bus": "redis-pubsub"},
    }


@router.get("/api-access/scopes")
async def api_scope_catalog(current_user: CurrentUser) -> list[dict[str, str]]:
    del current_user
    return [{"scope": scope, "description": description} for scope, description in API_SCOPES.items()]


@router.get("/api-access/keys")
async def list_api_keys(current_user: CurrentUser, db: DbSession) -> list[dict[str, object]]:
    keys = (
        await db.execute(
            select(ApiAccessKey)
            .where(ApiAccessKey.user_id == current_user.id)
            .order_by(ApiAccessKey.created_at.desc())
        )
    ).scalars().all()
    return [_api_key_read(key) for key in keys]


@router.post("/api-access/keys", status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: ApiKeyCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> dict[str, object]:
    try:
        scopes = normalize_scopes(payload.scopes)
    except ApiAccessError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    token, prefix, digest = generate_api_token()
    key = ApiAccessKey(
        user_id=current_user.id,
        name=payload.name.strip(),
        prefix=prefix,
        token_digest=digest,
        scopes=scopes,
        enabled=True,
        expires_at=payload.expires_at,
    )
    db.add(key)
    await db.commit()
    await db.refresh(key)
    return {
        **_api_key_read(key),
        "token": token,
        "warning": "Copie a chave agora. O segredo completo não será exibido novamente.",
    }


@router.delete("/api-access/keys/{key_id}")
async def revoke_api_key(
    key_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> dict[str, object]:
    try:
        key = await revoke_user_api_key(db, user_id=current_user.id, key_id=key_id)
    except ApiAccessError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await db.commit()
    return {"message": f"Chave {key.name} revogada.", "id": str(key.id), "enabled": False}


@router.get("/external/v1/status")
async def external_status(key: ExternalApiKey, db: DbSession) -> dict[str, object]:
    _scope(key, "monitoring:read")
    return await _overview(db, key.user_id)


@router.get("/external/v1/repositories")
async def external_repositories(
    key: ExternalApiKey,
    db: DbSession,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, object]]:
    _scope(key, "repositories:read")
    repositories = (
        await db.execute(
            select(Repository)
            .join(GitHubConnection)
            .where(
                GitHubConnection.user_id == key.user_id,
                Repository.monitoring_enabled.is_(True),
            )
            .order_by(Repository.full_name.asc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "id": str(repo.id),
            "github_id": repo.github_id,
            "full_name": repo.full_name,
            "private": repo.private,
            "archived": repo.archived,
            "disabled": repo.disabled,
            "default_branch": repo.default_branch,
            "health_status": repo.health_status.value if hasattr(repo.health_status, "value") else str(repo.health_status),
            "health_score": repo.health_score,
            "last_activity_at": repo.last_activity_at.isoformat() if repo.last_activity_at else None,
            "last_activity_type": repo.last_activity_type,
            "latest_workflow_status": repo.latest_workflow_status,
            "latest_workflow_conclusion": repo.latest_workflow_conclusion,
            "last_synced_at": repo.last_synced_at.isoformat() if repo.last_synced_at else None,
        }
        for repo in repositories
    ]


@router.put("/external/v1/repositories/{repository_id}/actions")
async def external_actions(
    repository_id: uuid.UUID,
    payload: ExternalActionsUpdate,
    key: ExternalApiKey,
    db: DbSession,
) -> dict[str, object]:
    _scope(key, "actions:write")
    row = (
        await db.execute(
            select(Repository, GitHubConnection)
            .join(GitHubConnection, Repository.connection_id == GitHubConnection.id)
            .where(
                Repository.id == repository_id,
                GitHubConnection.user_id == key.user_id,
                Repository.monitoring_enabled.is_(True),
            )
        )
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Repositório monitorado não encontrado.")
    repository, connection = row
    if not connection.token_encrypted:
        raise HTTPException(status_code=400, detail="Conexão GitHub sem token operacional.")

    client = GitHubClient(
        EncryptionService().decrypt(connection.token_encrypted),
        api_url=connection.api_url,
    )
    cancelled: list[int] = []
    try:
        if not payload.enabled and payload.cancel_in_progress:
            runs = await client.list_workflow_runs(repository.full_name, limit=100)
            for run in runs:
                if str(run.get("status") or "").lower() not in {
                    "queued", "in_progress", "waiting", "pending", "requested"
                }:
                    continue
                try:
                    run_id = int(run["id"])
                    await client.cancel_workflow(repository.full_name, run_id)
                    cancelled.append(run_id)
                except (GitHubAPIError, KeyError, TypeError, ValueError):
                    continue
        await client.request(
            "PUT",
            f"/repos/{repository.full_name}/actions/permissions",
            json={"enabled": payload.enabled},
        )
    except GitHubAPIError as exc:
        code = exc.status_code if exc.status_code in {401, 403, 404, 422} else 502
        raise HTTPException(status_code=code, detail="O GitHub recusou a alteração de Actions.") from exc
    finally:
        await client.close()

    return {
        "repository_id": str(repository.id),
        "full_name": repository.full_name,
        "enabled": payload.enabled,
        "cancelled_runs": cancelled,
    }
