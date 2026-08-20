from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.github import ConnectionStatus, HealthStatus
from app.schemas import (
    ChangePasswordRequest,
    DashboardResponse,
    DashboardStats,
    GitHubConnectionCreate,
    GitHubConnectionRead,
    GitHubRemoteRepository,
    LoginRequest,
    MessageResponse,
    NotificationRead,
    PaginatedResponse,
    PullRequestRead,
    RefreshRequest,
    ReleaseRead,
    RepositoryDetail,
    RepositoryImportRequest,
    RepositoryRead,
    RepositoryUpdate,
    SyncAcceptedResponse,
    UserRead,
    WebhookConfigureRequest,
    WebhookConfigureResult,
    WorkflowActionResponse,
    WorkflowRunRead,
)
from app.schemas.dashboard import DashboardWorkflow

NOW = datetime.now(UTC)
REPOSITORY_ID = uuid.uuid4()
CONNECTION_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def workflow_payload() -> dict:
    return {
        "id": uuid.uuid4(),
        "github_id": 101,
        "name": "CI",
        "display_title": "Build",
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        "head_branch": "main",
        "head_sha": "a" * 40,
        "run_number": 12,
        "run_attempt": 1,
        "html_url": "https://github.com/wkarts/project/actions/runs/101",
        "actor_login": "wkarts",
        "github_created_at": NOW,
        "github_updated_at": NOW,
        "run_started_at": NOW,
        "duration_seconds": 42,
    }


def repository_payload() -> dict:
    return {
        "id": REPOSITORY_ID,
        "connection_id": CONNECTION_ID,
        "github_id": 1,
        "owner": "wkarts",
        "name": "project",
        "full_name": "wkarts/project",
        "html_url": "https://github.com/wkarts/project",
        "description": "Projeto",
        "private": True,
        "fork": False,
        "archived": False,
        "disabled": False,
        "visibility": "private",
        "default_branch": "main",
        "language": "Python",
        "stargazers_count": 0,
        "forks_count": 0,
        "open_issue_count": 2,
        "open_pr_count": 1,
        "branch_count": 3,
        "pushed_at": NOW,
        "latest_commit_sha": "b" * 40,
        "latest_commit_message": "Commit",
        "latest_commit_author": "wkarts",
        "latest_commit_at": NOW,
        "latest_release_tag": "v0.1.0",
        "latest_release_name": "v0.1.0",
        "latest_release_at": NOW,
        "latest_workflow_id": 101,
        "latest_workflow_name": "CI",
        "latest_workflow_status": "completed",
        "latest_workflow_conclusion": "success",
        "latest_workflow_url": "https://github.com/wkarts/project/actions/runs/101",
        "latest_workflow_at": NOW,
        "health_score": 100,
        "health_status": HealthStatus.HEALTHY,
        "monitoring_enabled": True,
        "last_synced_at": NOW,
        "sync_error": None,
    }


def test_auth_and_connection_validation():
    login = LoginRequest(email="admin@argws.com.br", password="secret")
    assert str(login.email) == "admin@argws.com.br"
    assert ChangePasswordRequest(current_password="old", new_password="NewPassword@123")
    assert RefreshRequest(refresh_token="x" * 64)
    connection = GitHubConnectionCreate(token="github_pat_" + "x" * 30)
    assert connection.auto_import is True
    with pytest.raises(ValidationError):
        ChangePasswordRequest(current_password="old", new_password="short")


def test_repository_and_operational_schemas_roundtrip():
    repository = RepositoryRead.model_validate(repository_payload())
    workflow = WorkflowRunRead.model_validate(workflow_payload())
    pull = PullRequestRead(
        id=uuid.uuid4(), github_id=2, number=7, title="PR", state="open", draft=False,
        html_url="https://github.com/wkarts/project/pull/7", user_login="wkarts",
        head_ref="feature", base_ref="main", mergeable_state="clean",
        github_created_at=NOW, github_updated_at=NOW, closed_at=None, merged_at=None,
    )
    release = ReleaseRead(
        id=uuid.uuid4(), github_id=3, tag_name="v0.1.0", name="Release", draft=False,
        prerelease=False, html_url="https://github.com/wkarts/project/releases/tag/v0.1.0",
        target_commitish="main", github_created_at=NOW, published_at=NOW,
    )
    detail = RepositoryDetail(**repository.model_dump(), workflow_runs=[workflow], pull_requests=[pull], releases=[release])
    assert detail.workflow_runs[0].conclusion == "success"
    assert RepositoryUpdate(monitoring_enabled=False).monitoring_enabled is False
    assert WorkflowActionResponse(message="ok", run_id=101).run_id == 101


def test_dashboard_notification_and_pagination_schemas():
    notification = NotificationRead(
        id=uuid.uuid4(), repository_id=REPOSITORY_ID, event_type="workflow.failed",
        severity="error", title="Falha", message="Build falhou", url=None,
        payload={"run_id": 101}, read_at=None, created_at=NOW,
    )
    stats = DashboardStats(
        total_repositories=1, private_repositories=1, public_repositories=0,
        healthy=1, running=0, attention=0, failing=0, unknown=0,
        open_pull_requests=1, open_issues=2, unread_notifications=1,
        average_health_score=100,
    )
    workflow = DashboardWorkflow(**workflow_payload(), repository_id=REPOSITORY_ID, repository_full_name="wkarts/project")
    dashboard = DashboardResponse(
        stats=stats,
        repositories=[RepositoryRead.model_validate(repository_payload())],
        recent_workflows=[workflow],
        recent_notifications=[notification],
    )
    page = PaginatedResponse[NotificationRead](items=[notification], total=1, page=1, page_size=30, pages=1)
    assert dashboard.stats.average_health_score == 100
    assert page.items[0].severity == "error"


def test_remaining_github_and_common_schemas():
    user = UserRead(
        id=USER_ID, name="Administrador", email="admin@argws.com.br", is_active=True,
        is_superuser=True, must_change_password=True, last_login_at=None, created_at=NOW,
    )
    connection = GitHubConnectionRead(
        id=CONNECTION_ID, name="Principal", github_login="wkarts", github_user_id=57051272,
        token_last_four="1234", status=ConnectionStatus.ACTIVE, auto_import=True,
        api_url="https://api.github.com", last_sync_at=NOW, last_error=None,
        rate_limit_remaining=4999, rate_limit_reset_at=NOW, created_at=NOW, repository_count=1,
    )
    remote = GitHubRemoteRepository(
        github_id=1, owner="wkarts", name="project", full_name="wkarts/project",
        html_url="https://github.com/wkarts/project", description=None, private=True,
        archived=False, default_branch="main", language="Python", selected=True,
    )
    assert user.is_superuser and connection.repository_count == 1 and remote.selected
    assert RepositoryImportRequest(repository_ids=[1]).repository_ids == [1]
    assert SyncAcceptedResponse(message="ok", task_id="task").task_id == "task"
    assert WebhookConfigureRequest(repository_ids=[REPOSITORY_ID])
    assert WebhookConfigureResult(repository="wkarts/project", success=True, message="ok", webhook_id=1)
    assert MessageResponse(message="ok").message == "ok"
