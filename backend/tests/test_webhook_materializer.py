from __future__ import annotations

from app.models.github import PullRequest, Release, WorkflowRun
from app.models.issue import Issue
from app.services.webhook_materializer import operational_values


def test_workflow_webhook_maps_directly_to_operational_row() -> None:
    resolved = operational_values(
        "workflow_run",
        {
            "workflow_run": {
                "id": 123,
                "name": "CI",
                "display_title": "feat: realtime",
                "event": "push",
                "status": "completed",
                "conclusion": "success",
                "head_branch": "main",
                "head_sha": "abc123",
                "run_number": 42,
                "run_attempt": 1,
                "html_url": "https://github.com/acme/repo/actions/runs/123",
                "actor": {"login": "wkarts"},
                "created_at": "2026-08-28T03:00:00Z",
                "run_started_at": "2026-08-28T03:00:05Z",
                "updated_at": "2026-08-28T03:01:05Z",
            }
        },
    )

    assert resolved is not None
    model, github_id, values = resolved
    assert model is WorkflowRun
    assert github_id == 123
    assert values["status"] == "completed"
    assert values["conclusion"] == "success"
    assert values["duration_seconds"] == 60
    assert values["actor_login"] == "wkarts"


def test_pull_release_and_issue_webhooks_map_without_rest_roundtrip() -> None:
    pull = operational_values(
        "pull_request",
        {
            "action": "opened",
            "number": 37,
            "pull_request": {
                "id": 3700,
                "number": 37,
                "title": "feat: monitor",
                "state": "open",
                "draft": False,
                "html_url": "https://github.com/acme/repo/pull/37",
                "user": {"login": "alice"},
                "head": {"ref": "feat/live"},
                "base": {"ref": "main"},
                "created_at": "2026-08-28T03:00:00Z",
                "updated_at": "2026-08-28T03:00:01Z",
            },
        },
    )
    release = operational_values(
        "release",
        {
            "release": {
                "id": 700,
                "tag_name": "v0.7.1",
                "name": "0.7.1",
                "draft": False,
                "prerelease": False,
                "html_url": "https://github.com/acme/repo/releases/tag/v0.7.1",
                "target_commitish": "main",
                "created_at": "2026-08-28T03:00:00Z",
                "published_at": "2026-08-28T03:02:00Z",
            }
        },
    )
    issue = operational_values(
        "issues",
        {
            "issue": {
                "id": 900,
                "number": 9,
                "title": "Monitor atrasado",
                "state": "open",
                "html_url": "https://github.com/acme/repo/issues/9",
                "user": {"login": "bob"},
                "comments": 2,
                "locked": False,
                "labels": [{"name": "bug"}, {"name": "realtime"}],
                "created_at": "2026-08-28T03:00:00Z",
                "updated_at": "2026-08-28T03:03:00Z",
            }
        },
    )

    assert pull is not None and pull[0] is PullRequest
    assert pull[2]["head_ref"] == "feat/live"
    assert release is not None and release[0] is Release
    assert release[2]["tag_name"] == "v0.7.1"
    assert issue is not None and issue[0] is Issue
    assert issue[2]["labels_text"] == "bug, realtime"


def test_non_operational_webhook_does_not_create_fake_row() -> None:
    assert operational_values("push", {"after": "abc"}) is None
    assert operational_values("workflow_run", {"workflow_run": {}}) is None
