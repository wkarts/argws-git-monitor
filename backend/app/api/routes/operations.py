from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, or_, select

from app.api.deps import CurrentUser, DbSession
from app.models.github import GitHubConnection, PullRequest, Release, Repository, WorkflowRun
from app.models.issue import Issue
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.operations import (
    IssueCreateRequest,
    IssueStateRequest,
    OperationIssueRead,
    OperationModuleStatus,
    OperationPullRequestRead,
    OperationReleaseRead,
    OperationsStatusResponse,
    OperationWorkflowRead,
)
from app.services.github_client import GitHubAPIError
from app.services.github_sync import get_repository_client, sync_repository

router = APIRouter(prefix="/operations", tags=["Operações GitHub"])


def _pages(total: int, page_size: int) -> int:
    return max(math.ceil(total / page_size), 1)


@router.get("/status", response_model=OperationsStatusResponse)
async def operations_status(
    current_user: CurrentUser,
    db: DbSession,
) -> OperationsStatusResponse:
    repositories = (
        await db.execute(
            select(Repository)
            .join(GitHubConnection, Repository.connection_id == GitHubConnection.id)
            .where(
                GitHubConnection.user_id == current_user.id,
                Repository.monitoring_enabled.is_(True),
            )
        )
    ).scalars().all()

    definitions = [
        ("actions", "GitHub Actions"),
        ("pull_requests", "Pull Requests"),
        ("issues", "Issues"),
        ("releases", "Releases"),
    ]
    modules: list[OperationModuleStatus] = []
    for key, label in definitions:
        observed = 0
        errors: list[str] = []
        count = 0
        last_observed: datetime | None = None
        for repository in repositories:
            source = ((repository.extra_data or {}).get("sync_sources") or {}).get(key) or {}
            if source.get("observed") is True:
                observed += 1
            error = source.get("error")
            if error:
                errors.append(f"{repository.full_name}: {error}")
            count += int(source.get("count") or source.get("run_count") or 0)
            raw_observed = source.get("observed_at")
            if raw_observed:
                try:
                    parsed = datetime.fromisoformat(str(raw_observed).replace("Z", "+00:00"))
                    parsed = parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
                    if last_observed is None or parsed > last_observed:
                        last_observed = parsed
                except ValueError:
                    pass
        modules.append(
            OperationModuleStatus(
                key=key,
                label=label,
                monitored_repositories=len(repositories),
                observed_repositories=observed,
                error_repositories=len(errors),
                item_count=count,
                last_observed_at=last_observed,
                errors=errors[:20],
            )
        )

    last_sync = max(
        (item.last_synced_at for item in repositories if item.last_synced_at),
        default=None,
    )
    return OperationsStatusResponse(
        monitored_repositories=len(repositories),
        last_repository_sync_at=last_sync,
        modules=modules,
    )


@router.get("/actions", response_model=PaginatedResponse[OperationWorkflowRead])
async def list_actions(
    current_user: CurrentUser,
    db: DbSession,
    q: str | None = Query(default=None, max_length=200),
    state: str | None = Query(default=None, max_length=40),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
) -> PaginatedResponse[OperationWorkflowRead]:
    query = (
        select(WorkflowRun, Repository)
        .join(Repository, WorkflowRun.repository_id == Repository.id)
        .join(GitHubConnection, Repository.connection_id == GitHubConnection.id)
        .where(GitHubConnection.user_id == current_user.id)
    )
    if q:
        search = f"%{q.strip()}%"
        query = query.where(
            or_(
                Repository.full_name.ilike(search),
                WorkflowRun.name.ilike(search),
                WorkflowRun.display_title.ilike(search),
                WorkflowRun.head_branch.ilike(search),
            )
        )
    normalized_state = (state or "").strip().lower()
    if normalized_state == "running":
        query = query.where(WorkflowRun.status.in_(["queued", "in_progress", "waiting", "pending"]))
    elif normalized_state == "success":
        query = query.where(WorkflowRun.conclusion == "success")
    elif normalized_state == "failure":
        query = query.where(
            WorkflowRun.conclusion.in_(
                ["failure", "cancelled", "timed_out", "action_required", "startup_failure"]
            )
        )

    total = int(
        (await db.execute(select(func.count()).select_from(query.order_by(None).subquery()))).scalar_one()
    )
    rows = (
        await db.execute(
            query.order_by(WorkflowRun.github_updated_at.desc().nullslast())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    items = [
        OperationWorkflowRead(
            id=run.id,
            repository_id=repository.id,
            repository_full_name=repository.full_name,
            repository_private=repository.private,
            github_id=run.github_id,
            name=run.name,
            display_title=run.display_title,
            event=run.event,
            status=run.status,
            conclusion=run.conclusion,
            head_branch=run.head_branch,
            head_sha=run.head_sha,
            run_number=run.run_number,
            run_attempt=run.run_attempt,
            html_url=run.html_url,
            actor_login=run.actor_login,
            github_created_at=run.github_created_at,
            github_updated_at=run.github_updated_at,
            run_started_at=run.run_started_at,
            duration_seconds=run.duration_seconds,
        )
        for run, repository in rows
    ]
    return PaginatedResponse[OperationWorkflowRead](
        items=items, total=total, page=page, page_size=page_size, pages=_pages(total, page_size)
    )


@router.get("/pull-requests", response_model=PaginatedResponse[OperationPullRequestRead])
async def list_pull_requests(
    current_user: CurrentUser,
    db: DbSession,
    q: str | None = Query(default=None, max_length=200),
    draft: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
) -> PaginatedResponse[OperationPullRequestRead]:
    query = (
        select(PullRequest, Repository)
        .join(Repository, PullRequest.repository_id == Repository.id)
        .join(GitHubConnection, Repository.connection_id == GitHubConnection.id)
        .where(GitHubConnection.user_id == current_user.id, PullRequest.state == "open")
    )
    if q:
        search = f"%{q.strip()}%"
        query = query.where(
            or_(
                Repository.full_name.ilike(search),
                PullRequest.title.ilike(search),
                PullRequest.user_login.ilike(search),
                PullRequest.head_ref.ilike(search),
            )
        )
    if draft is not None:
        query = query.where(PullRequest.draft == draft)

    total = int(
        (await db.execute(select(func.count()).select_from(query.order_by(None).subquery()))).scalar_one()
    )
    rows = (
        await db.execute(
            query.order_by(PullRequest.github_updated_at.desc().nullslast())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    items = [
        OperationPullRequestRead(
            id=pull.id,
            repository_id=repository.id,
            repository_full_name=repository.full_name,
            repository_private=repository.private,
            github_id=pull.github_id,
            number=pull.number,
            title=pull.title,
            state=pull.state,
            draft=pull.draft,
            html_url=pull.html_url,
            user_login=pull.user_login,
            head_ref=pull.head_ref,
            base_ref=pull.base_ref,
            mergeable_state=pull.mergeable_state,
            github_created_at=pull.github_created_at,
            github_updated_at=pull.github_updated_at,
            closed_at=pull.closed_at,
            merged_at=pull.merged_at,
        )
        for pull, repository in rows
    ]
    return PaginatedResponse[OperationPullRequestRead](
        items=items, total=total, page=page, page_size=page_size, pages=_pages(total, page_size)
    )


@router.get("/releases", response_model=PaginatedResponse[OperationReleaseRead])
async def list_releases(
    current_user: CurrentUser,
    db: DbSession,
    q: str | None = Query(default=None, max_length=200),
    prerelease: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
) -> PaginatedResponse[OperationReleaseRead]:
    query = (
        select(Release, Repository)
        .join(Repository, Release.repository_id == Repository.id)
        .join(GitHubConnection, Repository.connection_id == GitHubConnection.id)
        .where(GitHubConnection.user_id == current_user.id)
    )
    if q:
        search = f"%{q.strip()}%"
        query = query.where(
            or_(
                Repository.full_name.ilike(search),
                Release.tag_name.ilike(search),
                Release.name.ilike(search),
                Release.target_commitish.ilike(search),
            )
        )
    if prerelease is not None:
        query = query.where(Release.prerelease == prerelease)

    total = int(
        (await db.execute(select(func.count()).select_from(query.order_by(None).subquery()))).scalar_one()
    )
    rows = (
        await db.execute(
            query.order_by(Release.published_at.desc().nullslast())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    items = [
        OperationReleaseRead(
            id=release.id,
            repository_id=repository.id,
            repository_full_name=repository.full_name,
            repository_private=repository.private,
            github_id=release.github_id,
            tag_name=release.tag_name,
            name=release.name,
            draft=release.draft,
            prerelease=release.prerelease,
            html_url=release.html_url,
            target_commitish=release.target_commitish,
            github_created_at=release.github_created_at,
            published_at=release.published_at,
        )
        for release, repository in rows
    ]
    return PaginatedResponse[OperationReleaseRead](
        items=items, total=total, page=page, page_size=page_size, pages=_pages(total, page_size)
    )


@router.get("/issues", response_model=PaginatedResponse[OperationIssueRead])
async def list_issues(
    current_user: CurrentUser,
    db: DbSession,
    q: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
) -> PaginatedResponse[OperationIssueRead]:
    query = (
        select(Issue, Repository)
        .join(Repository, Issue.repository_id == Repository.id)
        .join(GitHubConnection, Repository.connection_id == GitHubConnection.id)
        .where(GitHubConnection.user_id == current_user.id, Issue.state == "open")
    )
    if q:
        search = f"%{q.strip()}%"
        query = query.where(
            or_(
                Repository.full_name.ilike(search),
                Issue.title.ilike(search),
                Issue.user_login.ilike(search),
                Issue.labels_text.ilike(search),
            )
        )
    total = int(
        (await db.execute(select(func.count()).select_from(query.order_by(None).subquery()))).scalar_one()
    )
    rows = (
        await db.execute(
            query.order_by(Issue.github_updated_at.desc().nullslast())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    items = [
        OperationIssueRead(
            id=issue.id,
            repository_id=repository.id,
            repository_full_name=repository.full_name,
            repository_private=repository.private,
            github_id=issue.github_id,
            number=issue.number,
            title=issue.title,
            state=issue.state,
            html_url=issue.html_url,
            user_login=issue.user_login,
            comments=issue.comments,
            locked=issue.locked,
            labels=[part.strip() for part in (issue.labels_text or "").split(",") if part.strip()],
            github_created_at=issue.github_created_at,
            github_updated_at=issue.github_updated_at,
            closed_at=issue.closed_at,
        )
        for issue, repository in rows
    ]
    return PaginatedResponse[OperationIssueRead](
        items=items, total=total, page=page, page_size=page_size, pages=_pages(total, page_size)
    )


async def _owned_repository(db: DbSession, repository_id: uuid.UUID, user_id: uuid.UUID) -> Repository:
    result = await db.execute(
        select(Repository)
        .join(GitHubConnection, Repository.connection_id == GitHubConnection.id)
        .where(Repository.id == repository_id, GitHubConnection.user_id == user_id)
    )
    repository = result.scalar_one_or_none()
    if not repository:
        raise HTTPException(status_code=404, detail="Repositório não encontrado.")
    return repository


@router.post("/issues", response_model=MessageResponse)
async def create_issue(
    payload: IssueCreateRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> MessageResponse:
    repository = await _owned_repository(db, payload.repository_id, current_user.id)
    try:
        _, client = await get_repository_client(repository.id, user_id=current_user.id)
        try:
            created = await client.create_issue(
                repository.full_name,
                title=payload.title,
                body=payload.body,
            )
        finally:
            await client.close()
        await sync_repository(repository.id)
    except (GitHubAPIError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MessageResponse(message=f"Issue #{created.get('number')} criada em {repository.full_name}.")


@router.patch("/issues/{issue_id}/state", response_model=MessageResponse)
async def update_issue_state(
    issue_id: uuid.UUID,
    payload: IssueStateRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> MessageResponse:
    row = (
        await db.execute(
            select(Issue, Repository)
            .join(Repository, Issue.repository_id == Repository.id)
            .join(GitHubConnection, Repository.connection_id == GitHubConnection.id)
            .where(Issue.id == issue_id, GitHubConnection.user_id == current_user.id)
        )
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Issue não encontrada.")
    issue, repository = row
    try:
        _, client = await get_repository_client(repository.id, user_id=current_user.id)
        try:
            await client.update_issue_state(repository.full_name, issue.number, payload.state)
        finally:
            await client.close()
        await sync_repository(repository.id)
    except (GitHubAPIError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MessageResponse(
        message=f"Issue #{issue.number} marcada como {payload.state} em {repository.full_name}."
    )
