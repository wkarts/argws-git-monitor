from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.schemas.operations import (
    IssueSummaryRead,
    OperationPullRequestRead,
    OperationReleaseRead,
    OperationWorkflowRead,
)

NOW = datetime.now(UTC)
REPOSITORY_ID = uuid.uuid4()


def test_aggregated_workflow_and_pull_request_schemas() -> None:
    workflow = OperationWorkflowRead(
        id=uuid.uuid4(),
        repository_id=REPOSITORY_ID,
        repository_full_name="wkarts/scheduler-pro-platform",
        repository_private=True,
        github_id=1001,
        name="Android CI",
        display_title="Build Android",
        event="push",
        status="completed",
        conclusion="failure",
        head_branch="main",
        head_sha="a" * 40,
        run_number=31,
        run_attempt=1,
        html_url="https://github.com/wkarts/scheduler-pro-platform/actions/runs/1001",
        actor_login="wkarts",
        github_created_at=NOW,
        github_updated_at=NOW,
        run_started_at=NOW,
        duration_seconds=1120,
    )
    pull_request = OperationPullRequestRead(
        id=uuid.uuid4(),
        repository_id=REPOSITORY_ID,
        repository_full_name="wkarts/scheduler-pro-platform",
        repository_private=True,
        github_id=2001,
        number=31,
        title="Ajusta build Android",
        state="open",
        draft=False,
        html_url="https://github.com/wkarts/scheduler-pro-platform/pull/31",
        user_login="wkarts",
        head_ref="fix/android-build",
        base_ref="main",
        mergeable_state="clean",
        github_created_at=NOW,
        github_updated_at=NOW,
        closed_at=None,
        merged_at=None,
    )

    assert workflow.repository_id == pull_request.repository_id
    assert workflow.conclusion == "failure"
    assert pull_request.number == 31


def test_aggregated_release_and_issue_summary_schemas() -> None:
    release = OperationReleaseRead(
        id=uuid.uuid4(),
        repository_id=REPOSITORY_ID,
        repository_full_name="wkarts/argws-pro-communication",
        repository_private=True,
        github_id=3001,
        tag_name="v0.2.0",
        name="ARGWS Git Monitor 0.2.0",
        draft=False,
        prerelease=False,
        html_url="https://github.com/wkarts/argws-pro-communication/releases/tag/v0.2.0",
        target_commitish="main",
        github_created_at=NOW,
        published_at=NOW,
    )
    issue_summary = IssueSummaryRead(
        repository_id=REPOSITORY_ID,
        repository_full_name="wkarts/argws-pro-communication",
        repository_private=True,
        repository_html_url="https://github.com/wkarts/argws-pro-communication",
        open_issue_count=4,
        health_score=83,
        health_status="attention",
        last_synced_at=NOW,
    )

    assert release.tag_name == "v0.2.0"
    assert issue_summary.health_score == 83
    assert issue_summary.open_issue_count == 4
