from __future__ import annotations

import uuid
from datetime import UTC

from app.models.github import Repository
from app.services.github_mapping import apply_repository_base, parse_github_datetime


def test_apply_repository_base_maps_github_payload():
    repository = Repository(connection_id=uuid.uuid4(), github_id=1)
    apply_repository_base(
        repository,
        {
            "id": 123,
            "owner": {"login": "wkarts"},
            "name": "argws-git-monitor",
            "full_name": "wkarts/argws-git-monitor",
            "html_url": "https://github.com/wkarts/argws-git-monitor",
            "description": "Monitor",
            "private": True,
            "fork": False,
            "archived": False,
            "disabled": False,
            "visibility": "private",
            "default_branch": "main",
            "language": "Python",
            "stargazers_count": 2,
            "forks_count": 1,
            "created_at": "2026-08-20T10:00:00Z",
            "updated_at": "2026-08-20T11:00:00Z",
            "pushed_at": "2026-08-20T12:00:00Z",
        },
    )

    assert repository.github_id == 123
    assert repository.full_name == "wkarts/argws-git-monitor"
    assert repository.private is True
    assert repository.default_branch == "main"
    assert repository.pushed_at is not None
    assert repository.pushed_at.tzinfo == UTC


def test_parse_github_datetime_is_defensive():
    assert parse_github_datetime(None) is None
    assert parse_github_datetime("invalid") is None
    assert parse_github_datetime("2026-08-20T12:34:56Z") is not None
