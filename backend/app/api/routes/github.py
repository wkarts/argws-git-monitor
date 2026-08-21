from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, func, select

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.encryption import EncryptionService
from app.models.activity import SyncJob
from app.models.github import ConnectionStatus, GitHubConnection, Repository
from app.schemas.common import MessageResponse
from app.schemas.github import (
    GitHubConnectionCreate,
    GitHubConnectionRead,
    GitHubRemoteRepository,
    GitHubRepositoryCreate,
    RepositoryImportRequest,
    RepositoryImportResponse,
    SyncAcceptedResponse,
    WebhookConfigureRequest,
    WebhookConfigureResult,
)
from app.schemas.repository import RepositoryRead
from app.services.github_client import GitHubAPIError, GitHubClient
from app.services.github_mapping import apply_repository_base
from app.services.github_sync import sync_connection
from app.services.job_queue import create_job
from app.tasks.jobs import sync_connection_task, sync_repository_task

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


def _connection_schema(
    connection: GitHubConnection,
    repository_count: int,
    *,
    available_repository_count: int | None = None,
    oauth_scopes: list[str] | None = None,
) -> GitHubConnectionRead:
    data = GitHubConnectionRead.model_validate(connection)
    data.repository_count = repository_count
    data.available_repository_count = (
        repository_count if available_repository_count is None else available_repository_count
    )
    data.oauth_scopes = oauth_scopes or []
    return data


async def _queue_connection_sync(
    db: DbSession,
    connection: GitHubConnection,
    *,
    user_id: uuid.UUID,
    kind: str,
    label: str,
) -> tuple[SyncJob, str]:
    job = await create_job(
        db,
        user_id=user_id,
        connection_id=connection.id,
        kind=kind,
        label=label,
        message="Catálogo descoberto. Aguardando sincronização detalhada.",
    )
    await db.commit()
    task = sync_connection_task.delay(str(connection.id), None, str(job.id))
    job.celery_task_id = task.id
    await db.commit()
    return job, task.id


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
            remote_preview = await client.list_repositories(limit=get_settings().github_repository_limit)
            rate_remaining = client.rate_limit_remaining
            rate_reset = client.rate_limit_reset_at
            oauth_scopes = list(client.oauth_scopes)
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

    await db.execute(
        delete(GitHubConnection).where(
            GitHubConnection.user_id == current_user.id,
            GitHubConnection.status == ConnectionStatus.DEMO,
        )
    )
    await db.commit()
    await db.refresh(connection)

    repository_count = 0
    if payload.auto_import:
        try:
            discovery = await sync_connection(connection.id, full_sync=False)
            repository_count = discovery["repositories"]
            connection = await _owned_connection(db, connection.id, current_user.id)
            await _queue_connection_sync(
                db,
                connection,
                user_id=current_user.id,
                kind="connection.initial_sync",
                label=f"Sincronização inicial · {connection.name}",
            )
        except Exception as exc:
            connection = await _owned_connection(db, connection.id, current_user.id)
            connection.status = ConnectionStatus.ERROR
            connection.last_error = str(exc)[:4000]
            await db.commit()

    return _connection_schema(
        connection,
        repository_count,
        available_repository_count=len(remote_preview),
        oauth_scopes=oauth_scopes,
    )


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

    try:
        discovery = await sync_connection(connection.id, full_sync=False)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Falha ao descobrir repositórios: {exc}") from exc

    connection = await _owned_connection(db, connection_id, current_user.id)
    job, task_id = await _queue_connection_sync(
        db,
        connection,
        user_id=current_user.id,
        kind="connection.sync.manual",
        label=f"Sincronização manual · {connection.name}",
    )
    return SyncAcceptedResponse(
        message=(
            f"{discovery['repositories']} repositório(s) descoberto(s) imediatamente; "
            "detalhes adicionados à fila."
        ),
        task_id=task_id,
        job_id=job.id,
    )


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
            connection.rate_limit_remaining = client.rate_limit_remaining
            connection.rate_limit_reset_at = client.rate_limit_reset_at
            await db.commit()
    except GitHubAPIError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    repositories = [
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
            permissions={
                str(key): bool(value) for key, value in (item.get("permissions") or {}).items()
            },
        )
        for item in remote
    ]
    return sorted(repositories, key=lambda item: (not item.selected, item.full_name.lower()))


@router.post(
    "/connections/{connection_id}/import",
    response_model=RepositoryImportResponse,
)
async def import_repositories(
    connection_id: uuid.UUID,
    payload: RepositoryImportRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> RepositoryImportResponse:
    connection = await _owned_connection(db, connection_id, current_user.id)
    if connection.status == ConnectionStatus.DEMO:
        raise HTTPException(status_code=400, detail="Conexão demonstrativa não importa dados.")

    before = set(
        (
            await db.execute(
                select(Repository.github_id).where(Repository.connection_id == connection.id)
            )
        ).scalars().all()
    )
    selected_ids = set(payload.repository_ids)
    try:
        await sync_connection(
            connection.id,
            selected_github_ids=selected_ids,
            full_sync=False,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Falha ao importar catálogo: {exc}") from exc

    result = await db.execute(
        select(Repository).where(
            Repository.connection_id == connection.id,
            Repository.github_id.in_(selected_ids),
        )
    )
    repositories = result.scalars().all()
    jobs: list[SyncJob] = []
    for repository in repositories:
        job = await create_job(
            db,
            user_id=current_user.id,
            connection_id=connection.id,
            repository_id=repository.id,
            kind="repository.import",
            label=f"Monitorar · {repository.full_name}",
            message="Repositório adicionado ao monitor; aguardando sincronização detalhada.",
        )
        jobs.append(job)
    await db.commit()

    for repository, job in zip(repositories, jobs, strict=False):
        task = sync_repository_task.delay(str(repository.id), str(job.id))
        job.celery_task_id = task.id
    await db.commit()

    imported_count = sum(1 for repository in repositories if repository.github_id not in before)
    already_monitored = len(repositories) - imported_count
    return RepositoryImportResponse(
        message=(
            f"{len(repositories)} repositório(s) já aparecem no monitor. "
            "A sincronização detalhada pode ser acompanhada em Fila."
        ),
        imported_count=imported_count,
        already_monitored_count=already_monitored,
        queued_count=len(jobs),
        repository_ids=[repository.id for repository in repositories],
        job_ids=[job.id for job in jobs],
    )


@router.post(
    "/connections/{connection_id}/repositories",
    response_model=RepositoryRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_remote_repository(
    connection_id: uuid.UUID,
    payload: GitHubRepositoryCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> RepositoryRead:
    connection = await _owned_connection(db, connection_id, current_user.id)
    if not connection.token_encrypted:
        raise HTTPException(status_code=400, detail="Conexão sem token operacional.")
    token = EncryptionService().decrypt(connection.token_encrypted)
    try:
        async with GitHubClient(token, api_url=connection.api_url) as client:
            remote = await client.create_repository(
                name=payload.name,
                description=payload.description,
                private=payload.private,
                auto_init=payload.auto_init,
            )
            connection.rate_limit_remaining = client.rate_limit_remaining
            connection.rate_limit_reset_at = client.rate_limit_reset_at
    except GitHubAPIError as exc:
        status_code = 403 if exc.status_code == 403 else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    repository = Repository(connection_id=connection.id, github_id=int(remote["id"]))
    apply_repository_base(repository, remote)
    repository.monitoring_enabled = True
    repository.last_synced_at = datetime.now(UTC)
    db.add(repository)
    await db.flush()
    job = await create_job(
        db,
        user_id=current_user.id,
        connection_id=connection.id,
        repository_id=repository.id,
        kind="repository.created",
        label=f"Novo repositório · {repository.full_name}",
    )
    await db.commit()
    await db.refresh(repository)
    task = sync_repository_task.delay(str(repository.id), str(job.id))
    job.celery_task_id = task.id
    await db.commit()
    return RepositoryRead.model_validate(repository)


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
