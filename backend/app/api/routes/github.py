from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, func, select

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.encryption import EncryptionService
from app.models.github import ConnectionStatus, GitHubConnection, Repository
from app.schemas.common import MessageResponse
from app.schemas.github import (
    GitHubConnectionCreate,
    GitHubConnectionRead,
    GitHubRemoteRepository,
    RepositoryImportRequest,
    SyncAcceptedResponse,
    WebhookConfigureRequest,
    WebhookConfigureResult,
)
from app.services.github_client import GitHubAPIError, GitHubClient
from app.tasks.jobs import sync_connection_task

router = APIRouter(prefix="/github", tags=["GitHub"])


async def _owned_connection(
    db: DbSession, connection_id: uuid.UUID, user_id: uuid.UUID
) -> GitHubConnection:
    result = await db.execute(
        select(GitHubConnection).where(
            GitHubConnection.id == connection_id,
            GitHubConnection.user_id == user_id,
        )
    )
    connection = result.scalar_one_or_none()
    if not connection:
        raise HTTPException(status_code=404, detail="Conexão GitHub não encontrada.")
    return connection


def _connection_schema(connection: GitHubConnection, repository_count: int) -> GitHubConnectionRead:
    data = GitHubConnectionRead.model_validate(connection)
    data.repository_count = repository_count
    return data


@router.get("/connections", response_model=list[GitHubConnectionRead])
async def list_connections(current_user: CurrentUser, db: DbSession):
    result = await db.execute(
        select(GitHubConnection, func.count(Repository.id))
        .outerjoin(Repository)
        .where(GitHubConnection.user_id == current_user.id)
        .group_by(GitHubConnection.id)
        .order_by(GitHubConnection.created_at.desc())
    )
    return [_connection_schema(connection, count) for connection, count in result.all()]


@router.post(
    "/connections",
    response_model=GitHubConnectionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_connection(
    payload: GitHubConnectionCreate,
    current_user: CurrentUser,
    db: DbSession,
):
    try:
        async with GitHubClient(payload.token, api_url=payload.api_url) as client:
            profile = await client.get_authenticated_user()
            rate_remaining = client.rate_limit_remaining
            rate_reset = client.rate_limit_reset_at
    except GitHubAPIError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    connection = GitHubConnection(
        user_id=current_user.id,
        name=payload.name,
        github_login=str(profile.get("login") or "github"),
        github_user_id=int(profile["id"]) if profile.get("id") else None,
        token_encrypted=EncryptionService().encrypt(payload.token),
        token_last_four=payload.token[-4:],
        status=ConnectionStatus.ACTIVE,
        auto_import=payload.auto_import,
        api_url=payload.api_url.rstrip("/"),
        rate_limit_remaining=rate_remaining,
        rate_limit_reset_at=rate_reset,
    )
    db.add(connection)

    # Ao conectar dados reais, remove apenas a conexão demonstrativa do mesmo usuário.
    await db.execute(
        delete(GitHubConnection).where(
            GitHubConnection.user_id == current_user.id,
            GitHubConnection.status == ConnectionStatus.DEMO,
        )
    )
    await db.commit()
    await db.refresh(connection)

    if payload.auto_import:
        sync_connection_task.delay(str(connection.id))
    return _connection_schema(connection, 0)


@router.delete("/connections/{connection_id}", response_model=MessageResponse)
async def remove_connection(
    connection_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> MessageResponse:
    connection = await _owned_connection(db, connection_id, current_user.id)
    await db.delete(connection)
    await db.commit()
    return MessageResponse(message="Conexão e dados monitorados removidos.")


@router.post("/connections/{connection_id}/sync", response_model=SyncAcceptedResponse)
async def sync_connection_now(
    connection_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> SyncAcceptedResponse:
    connection = await _owned_connection(db, connection_id, current_user.id)
    if connection.status == ConnectionStatus.DEMO:
        raise HTTPException(status_code=400, detail="Conexão demonstrativa não sincroniza.")
    task = sync_connection_task.delay(str(connection.id))
    return SyncAcceptedResponse(message="Sincronização adicionada à fila.", task_id=task.id)


@router.get(
    "/connections/{connection_id}/remote-repositories",
    response_model=list[GitHubRemoteRepository],
)
async def list_remote_repositories(
    connection_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
):
    settings = get_settings()
    connection = await _owned_connection(db, connection_id, current_user.id)
    if not connection.token_encrypted:
        return []
    existing_result = await db.execute(
        select(Repository.github_id).where(Repository.connection_id == connection.id)
    )
    existing_ids = set(existing_result.scalars().all())
    token = EncryptionService().decrypt(connection.token_encrypted)
    try:
        async with GitHubClient(token, api_url=connection.api_url) as client:
            remote = await client.list_repositories(limit=settings.github_repository_limit)
    except GitHubAPIError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return [
        GitHubRemoteRepository(
            github_id=int(item["id"]),
            owner=str((item.get("owner") or {}).get("login") or ""),
            name=str(item.get("name") or ""),
            full_name=str(item.get("full_name") or ""),
            html_url=item.get("html_url") or "https://github.com",
            description=item.get("description"),
            private=bool(item.get("private", False)),
            archived=bool(item.get("archived", False)),
            default_branch=str(item.get("default_branch") or "main"),
            language=item.get("language"),
            selected=int(item["id"]) in existing_ids,
        )
        for item in remote
    ]


@router.post(
    "/connections/{connection_id}/import",
    response_model=SyncAcceptedResponse,
)
async def import_repositories(
    connection_id: uuid.UUID,
    payload: RepositoryImportRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> SyncAcceptedResponse:
    connection = await _owned_connection(db, connection_id, current_user.id)
    if connection.status == ConnectionStatus.DEMO:
        raise HTTPException(status_code=400, detail="Conexão demonstrativa não importa dados.")
    task = sync_connection_task.delay(str(connection.id), payload.repository_ids)
    return SyncAcceptedResponse(
        message=f"Importação de {len(payload.repository_ids)} repositório(s) adicionada à fila.",
        task_id=task.id,
    )


@router.post(
    "/connections/{connection_id}/configure-webhooks",
    response_model=list[WebhookConfigureResult],
)
async def configure_webhooks(
    connection_id: uuid.UUID,
    payload: WebhookConfigureRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    settings = get_settings()
    connection = await _owned_connection(db, connection_id, current_user.id)
    if not connection.token_encrypted:
        raise HTTPException(status_code=400, detail="Conexão sem token operacional.")

    query = select(Repository).where(Repository.connection_id == connection.id)
    if payload.repository_ids:
        query = query.where(Repository.id.in_(payload.repository_ids))
    result = await db.execute(query)
    repositories = result.scalars().all()
    webhook_url = payload.webhook_url or (
        f"{settings.public_base_url}{settings.api_v1_prefix}/webhooks/github"
    )
    token = EncryptionService().decrypt(connection.token_encrypted)
    responses: list[WebhookConfigureResult] = []
    async with GitHubClient(token, api_url=connection.api_url) as client:
        for repository in repositories:
            try:
                hook = await client.create_webhook(
                    repository.full_name,
                    webhook_url=webhook_url,
                    secret=settings.github_webhook_secret,
                )
                responses.append(
                    WebhookConfigureResult(
                        repository=repository.full_name,
                        success=True,
                        message="Webhook configurado.",
                        webhook_id=hook.get("id"),
                    )
                )
            except (GitHubAPIError, ValueError) as exc:
                responses.append(
                    WebhookConfigureResult(
                        repository=repository.full_name,
                        success=False,
                        message=str(exc),
                    )
                )
    return responses
