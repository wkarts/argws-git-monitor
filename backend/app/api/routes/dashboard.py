from __future__ import annotations

from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models.activity import Notification
from app.models.github import GitHubConnection, HealthStatus, Repository, WorkflowRun
from app.schemas.dashboard import DashboardResponse, DashboardStats, DashboardWorkflow
from app.schemas.notification import NotificationRead
from app.schemas.repository import RepositoryRead, WorkflowRunRead

from fastapi import APIRouter

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("", response_model=DashboardResponse)
async def dashboard(current_user: CurrentUser, db: DbSession) -> DashboardResponse:
    repository_result = await db.execute(
        select(Repository)
        .join(GitHubConnection)
        .where(GitHubConnection.user_id == current_user.id)
        .order_by(
            Repository.health_score.asc(),
            Repository.github_updated_at.desc().nullslast(),
        )
    )
    repositories = repository_result.scalars().all()

    notification_result = await db.execute(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(10)
    )
    notifications = notification_result.scalars().all()

    workflow_result = await db.execute(
        select(WorkflowRun, Repository.full_name)
        .join(Repository, WorkflowRun.repository_id == Repository.id)
        .join(GitHubConnection, Repository.connection_id == GitHubConnection.id)
        .where(GitHubConnection.user_id == current_user.id)
        .order_by(WorkflowRun.github_created_at.desc().nullslast())
        .limit(10)
    )
    workflow_rows = workflow_result.all()

    health_counts = {status: 0 for status in HealthStatus}
    for repository in repositories:
        health_counts[repository.health_status] += 1

    # Conta todas as não lidas no banco, sem carregar seus identificadores em memória.
    unread_result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.read_at.is_(None),
        )
    )
    unread = int(unread_result.scalar_one())

    total = len(repositories)
    average = round(sum(item.health_score for item in repositories) / total) if total else 0
    stats = DashboardStats(
        total_repositories=total,
        private_repositories=sum(1 for item in repositories if item.private),
        public_repositories=sum(1 for item in repositories if not item.private),
        healthy=health_counts[HealthStatus.HEALTHY],
        running=health_counts[HealthStatus.RUNNING],
        attention=health_counts[HealthStatus.ATTENTION],
        failing=health_counts[HealthStatus.FAILING],
        unknown=health_counts[HealthStatus.UNKNOWN],
        open_pull_requests=sum(item.open_pr_count for item in repositories),
        open_issues=sum(item.open_issue_count for item in repositories),
        unread_notifications=unread,
        average_health_score=average,
    )

    recent_workflows: list[DashboardWorkflow] = []
    for workflow, full_name in workflow_rows:
        base = WorkflowRunRead.model_validate(workflow).model_dump()
        recent_workflows.append(
            DashboardWorkflow(
                **base,
                repository_id=workflow.repository_id,
                repository_full_name=full_name,
            )
        )

    return DashboardResponse(
        stats=stats,
        repositories=[RepositoryRead.model_validate(item) for item in repositories[:12]],
        recent_workflows=recent_workflows,
        recent_notifications=[NotificationRead.model_validate(item) for item in notifications],
    )
