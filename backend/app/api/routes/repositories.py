from __future__ import annotations

import math
import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models.github import (
    GitHubConnection,
    HealthStatus,
    PullRequest,
    Release,
    Repository,
    WorkflowRun,
)
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.github import SyncAcceptedResponse
from app.schemas.repository import (
    PullRequestRead,
    ReleaseRead,
    RepositoryDeleteRequest,
    RepositoryDetail,
    RepositoryRead,
    RepositoryRemoteUpdate,
    RepositoryUpdate,
    WorkflowActionResponse,
    WorkflowRunRead,
)
from app.services.github_client import GitHubAPIError
from app.services.github_mapping import apply_repository_base
from app.services.github_sync import get_repository_client
from app.services.job_queue import create_job
from app.services.worker_status import require_worker
from app.tasks.jobs import sync_repository_task

router = APIRouter(prefix="/repositories", tags=["Repositórios"])


async def _owned_repository(
    db: DbSession, repository_id: uuid.UUID, user_id: uuid.UUID
) -> Repository:
    result = await db.execute(
        select(Repository)
        .join(GitHubConnection)
        .where(Repository.id == repository_id, GitHubConnection.user_id == user_id)
    )
    repository = result.scalar_one_or_none()
    if not repository:
        raise HTTPException(status_code=404, detail="Repositório não encontrado.")
    return repository


@router.get("", response_model=PaginatedResponse[RepositoryRead])
async def list_repositories(
    current_user: CurrentUser,
    db: DbSession,
    q: str | None = Query(default=None, max_length=200),
    health: HealthStatus | None = None,
    private: bool | None = None,
    monitoring_enabled: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
):
    query = (
        select(Repository)
        .join(GitHubConnection)
        .where(GitHubConnection.user_id == current_user.id)
    )
    if q:
        search = f"%{q.strip()}%"
        query = query.where(
            Repository.full_name.ilike(search) | Repository.description.ilike(search)
        )
    if health:
        query = query.where(Repository.health_status == health)
    if private is not None:
        query = query.where(Repository.private == private)
    if monitoring_enabled is not None:
        query = query.where(Repository.monitoring_enabled == monitoring_enabled)

    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total = int((await db.execute(count_query)).scalar_one())
    query = query.order_by(
        Repository.health_score.asc(),
        Repository.github_updated_at.desc().nullslast(),
        Repository.full_name.asc(),
    ).offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(query)).scalars().all()
    return PaginatedResponse[RepositoryRead](
        items=[RepositoryRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=max(math.ceil(total / page_size), 1),
    )


@router.get("/{repository_id}", response_model=RepositoryDetail)
async def repository_detail(
    repository_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> RepositoryDetail:
    repository = await _owned_repository(db, repository_id, current_user.id)
    workflows = (
        await db.execute(
            select(WorkflowRun)
            .where(WorkflowRun.repository_id == repository.id)
            .order_by(WorkflowRun.github_created_at.desc().nullslast())
            .limit(30)
        )
    ).scalars().all()
    pull_requests = (
        await db.execute(
            select(PullRequest)
            .where(PullRequest.repository_id == repository.id)
            .order_by(PullRequest.github_updated_at.desc().nullslast())
            .limit(100)
        )
    ).scalars().all()
    releases = (
        await db.execute(
            select(Release)
            .where(Release.repository_id == repository.id)
            .order_by(Release.published_at.desc().nullslast())
            .limit(20)
        )
    ).scalars().all()
    base = RepositoryRead.model_validate(repository).model_dump()
    return RepositoryDetail(
        **base,
        workflow_runs=[WorkflowRunRead.model_validate(item) for item in workflows],
        pull_requests=[PullRequestRead.model_validate(item) for item in pull_requests],
        releases=[ReleaseRead.model_validate(item) for item in releases],
    )


@router.patch("/{repository_id}", response_model=RepositoryRead)
async def update_repository(
    repository_id: uuid.UUID,
    payload: RepositoryUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> RepositoryRead:
    repository = await _owned_repository(db, repository_id, current_user.id)
    repository.monitoring_enabled = payload.monitoring_enabled
    await db.commit()
    await db.refresh(repository)
    return RepositoryRead.model_validate(repository)


@router.patch("/{repository_id}/github", response_model=RepositoryRead)
async def update_remote_repository(
    repository_id: uuid.UUID,
    payload: RepositoryRemoteUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> RepositoryRead:
    repository = await _owned_repository(db, repository_id, current_user.id)
    try:
        _, client = await get_repository_client(repository.id, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        remote = await client.update_repository(
            repository.full_name,
            private=payload.private,
            archived=payload.archived,
            description=payload.description,
        )
    except GitHubAPIError as exc:
        code = 403 if exc.status_code in {401, 403} else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    finally:
        await client.close()

    apply_repository_base(repository, remote)
    repository.sync_error = None
    await db.commit()
    await db.refresh(repository)
    return RepositoryRead.model_validate(repository)


@router.delete("/{repository_id}/monitoring", response_model=MessageResponse)
async def remove_from_monitor(
    repository_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> MessageResponse:
    repository = await _owned_repository(db, repository_id, current_user.id)
    full_name = repository.full_name
    await db.delete(repository)
    await db.commit()
    return MessageResponse(
        message=f"{full_name} removido somente do monitor. O repositório no GitHub não foi alterado."
    )


@router.post("/{repository_id}/delete-github", response_model=MessageResponse)
async def delete_from_github(
    repository_id: uuid.UUID,
    payload: RepositoryDeleteRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> MessageResponse:
    repository = await _owned_repository(db, repository_id, current_user.id)
    if payload.confirmation.strip() != repository.full_name:
        raise HTTPException(
            status_code=400,
            detail=f"Para excluir definitivamente, digite exatamente {repository.full_name}.",
        )
    try:
        _, client = await get_repository_client(repository.id, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        await client.delete_repository(repository.full_name)
    except GitHubAPIError as exc:
        code = 403 if exc.status_code in {401, 403} else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    finally:
        await client.close()

    full_name = repository.full_name
    await db.delete(repository)
    await db.commit()
    return MessageResponse(
        message=f"{full_name} foi excluído definitivamente do GitHub e do monitor."
    )


@router.post("/{repository_id}/sync", response_model=SyncAcceptedResponse)
async def sync_repository_now(
    repository_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> SyncAcceptedResponse:
    repository = await _owned_repository(db, repository_id, current_user.id)
    try:
        await require_worker()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Sincronização não enfileirada. {exc}",
        ) from exc

    job = await create_job(
        db,
        user_id=current_user.id,
        connection_id=repository.connection_id,
        repository_id=repository.id,
        kind="repository.sync.manual",
        label=f"Sincronizar · {repository.full_name}",
        progress_total=1,
    )
    await db.commit()
    task = sync_repository_task.delay(str(repository_id), str(job.id))
    job.celery_task_id = task.id
    await db.commit()
    return SyncAcceptedResponse(
        message="Sincronização enviada ao worker e registrada na fila.",
        task_id=task.id,
        job_id=job.id,
    )


async def _run_workflow_action(
    repository_id: uuid.UUID,
    user_id: uuid.UUID,
    run_id: int,
    action: str,
) -> WorkflowActionResponse:
    try:
        repository, client = await get_repository_client(repository_id, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        if action == "rerun-failed":
            await client.rerun_failed_workflow(repository.full_name, run_id)
            message = "Jobs com falha foram enviados para nova execução."
        elif action == "rerun":
            await client.rerun_workflow(repository.full_name, run_id)
            message = "Workflow enviado para nova execução."
        elif action == "cancel":
            await client.cancel_workflow(repository.full_name, run_id)
            message = "Cancelamento solicitado ao GitHub."
        else:
            raise HTTPException(status_code=400, detail="Ação de workflow inválida.")
    except GitHubAPIError as exc:
        status_code = 403 if exc.status_code == 403 else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    finally:
        await client.close()
    return WorkflowActionResponse(message=message, run_id=run_id)


@router.post(
    "/{repository_id}/workflow-runs/{run_id}/rerun-failed",
    response_model=WorkflowActionResponse,
)
async def rerun_failed_workflow(
    repository_id: uuid.UUID,
    run_id: int,
    current_user: CurrentUser,
):
    return await _run_workflow_action(repository_id, current_user.id, run_id, "rerun-failed")


@router.post(
    "/{repository_id}/workflow-runs/{run_id}/rerun",
    response_model=WorkflowActionResponse,
)
async def rerun_workflow(
    repository_id: uuid.UUID,
    run_id: int,
    current_user: CurrentUser,
):
    return await _run_workflow_action(repository_id, current_user.id, run_id, "rerun")


@router.post(
    "/{repository_id}/workflow-runs/{run_id}/cancel",
    response_model=WorkflowActionResponse,
)
async def cancel_workflow(
    repository_id: uuid.UUID,
    run_id: int,
    current_user: CurrentUser,
):
    return await _run_workflow_action(repository_id, current_user.id, run_id, "cancel")
