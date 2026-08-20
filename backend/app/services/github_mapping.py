from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models.github import Repository


def parse_github_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def repository_owner(remote: dict[str, Any]) -> str:
    owner = remote.get("owner") or {}
    full_name = str(remote.get("full_name") or "unknown/unknown")
    return str(owner.get("login") or full_name.split("/", 1)[0])


def apply_repository_base(repository: Repository, remote: dict[str, Any]) -> None:
    repository.github_id = int(remote["id"])
    repository.owner = repository_owner(remote)
    repository.name = str(remote.get("name") or "unknown")
    repository.full_name = str(remote.get("full_name") or f"{repository.owner}/{repository.name}")
    repository.html_url = str(remote.get("html_url") or "https://github.com")
    repository.description = remote.get("description")
    repository.private = bool(remote.get("private", False))
    repository.fork = bool(remote.get("fork", False))
    repository.archived = bool(remote.get("archived", False))
    repository.disabled = bool(remote.get("disabled", False))
    repository.visibility = str(
        remote.get("visibility") or ("private" if repository.private else "public")
    )
    repository.default_branch = str(remote.get("default_branch") or "main")
    repository.language = remote.get("language")
    repository.stargazers_count = int(remote.get("stargazers_count") or 0)
    repository.forks_count = int(remote.get("forks_count") or 0)
    repository.github_created_at = parse_github_datetime(remote.get("created_at"))
    repository.github_updated_at = parse_github_datetime(remote.get("updated_at"))
    repository.pushed_at = parse_github_datetime(remote.get("pushed_at"))


def workflow_duration_seconds(run: dict[str, Any]) -> int | None:
    started = parse_github_datetime(run.get("run_started_at"))
    finished = parse_github_datetime(run.get("updated_at"))
    if not started or not finished:
        return None
    return max(int((finished - started).total_seconds()), 0)
