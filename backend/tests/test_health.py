from datetime import UTC, datetime, timedelta

from app.models.github import HealthStatus
from app.services.health import calculate_repository_health


def test_successful_active_repository_is_healthy():
    result = calculate_repository_health(
        archived=False,
        disabled=False,
        sync_error=None,
        pushed_at=datetime.now(UTC) - timedelta(hours=2),
        latest_workflow_status="completed",
        latest_workflow_conclusion="success",
        open_pr_count=2,
        open_issue_count=5,
    )
    assert result.score == 100
    assert result.status == HealthStatus.HEALTHY


def test_failed_workflow_is_failing():
    result = calculate_repository_health(
        archived=False,
        disabled=False,
        sync_error=None,
        pushed_at=datetime.now(UTC),
        latest_workflow_status="completed",
        latest_workflow_conclusion="failure",
        open_pr_count=0,
        open_issue_count=0,
    )
    assert result.score == 50
    assert result.status == HealthStatus.FAILING


def test_running_workflow_is_running():
    result = calculate_repository_health(
        archived=False,
        disabled=False,
        sync_error=None,
        pushed_at=datetime.now(UTC),
        latest_workflow_status="in_progress",
        latest_workflow_conclusion=None,
        open_pr_count=0,
        open_issue_count=0,
    )
    assert result.status == HealthStatus.RUNNING


def test_archived_inactive_repository_requires_attention():
    result = calculate_repository_health(
        archived=True,
        disabled=False,
        sync_error=None,
        pushed_at=datetime.now(UTC) - timedelta(days=200),
        latest_workflow_status="completed",
        latest_workflow_conclusion="success",
        open_pr_count=30,
        open_issue_count=120,
    )
    assert result.status == HealthStatus.FAILING
    assert result.score == 20
    assert len(result.reasons) >= 4


def test_repository_without_ci_is_unknown_when_otherwise_active():
    result = calculate_repository_health(
        archived=False,
        disabled=False,
        sync_error=None,
        pushed_at=datetime.now(UTC),
        latest_workflow_status=None,
        latest_workflow_conclusion=None,
        open_pr_count=0,
        open_issue_count=0,
    )
    assert result.status == HealthStatus.UNKNOWN
    assert result.score == 90


def test_sync_error_requires_attention():
    result = calculate_repository_health(
        archived=False,
        disabled=False,
        sync_error="timeout",
        pushed_at=datetime.now(UTC),
        latest_workflow_status="completed",
        latest_workflow_conclusion="success",
        open_pr_count=0,
        open_issue_count=0,
    )
    assert result.status == HealthStatus.ATTENTION
    assert result.score == 65
