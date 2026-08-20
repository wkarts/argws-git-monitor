from __future__ import annotations

import math

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from app.api.deps import CurrentUser, DbSession
from app.models.github import GitHubConnection, PullRequest, Release, Repository, WorkflowRun
from app.schemas.common import PaginatedResponse
from app.schemas.operations import (
    IssueSummaryRead,
    OperationPullRequestRead,
    OperationReleaseRead,
    OperationWorkflowRead,
)

router = APIRouter(prefix="/operations", tags=["Operações GitHub"])


def _pages(total: int, page_size: int) -> int:
    return max(math.ceil(total / page_size), 1)


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
        (
            await db.execute(
                select(func.count()).select_from(query.order_by(None).subquery())
            )
        ).scalar_one()
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
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=_pages(total, page_size),
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
        (
            await db.execute(
                select(func.count()).select_from(query.order_by(None).subquery())
            )
        ).scalar_one()
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
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=_pages(total, page_size),
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
        (
            await db.execute(
                select(func.count()).select_from(query.order_by(None).subquery())
            )
        ).scalar_one()
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
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=_pages(total, page_size),
    )


@router.get("/issues", response_model=PaginatedResponse[IssueSummaryRead])
async def list_issue_summaries(
    current_user: CurrentUser,
    db: DbSession,
    q: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
) -> PaginatedResponse[IssueSummaryRead]:
    query = (
        select(Repository)
        .join(GitHubConnection, Repository.connection_id == GitHubConnection.id)
        .where(
            GitHubConnection.user_id == current_user.id,
            Repository.open_issue_count > 0,
        )
    )
    if q:
        search = f"%{q.strip()}%"
        query = query.where(
            or_(Repository.full_name.ilike(search), Repository.description.ilike(search))
        )

    total = int(
        (
            await db.execute(
                select(func.count()).select_from(query.order_by(None).subquery())
            )
        ).scalar_one()
    )
    repositories = (
        await db.execute(
            query.order_by(
                Repository.open_issue_count.desc(),
                Repository.github_updated_at.desc().nullslast(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    items = [
        IssueSummaryRead(
            repository_id=repository.id,
            repository_full_name=repository.full_name,
            repository_private=repository.private,
            repository_html_url=repository.html_url,
            open_issue_count=repository.open_issue_count,
            health_score=repository.health_score,
            health_status=repository.health_status.value,
            last_synced_at=repository.last_synced_at,
        )
        for repository in repositories
    ]
    return PaginatedResponse[IssueSummaryRead](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=_pages(total, page_size),
    )
