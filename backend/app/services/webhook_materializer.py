from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.github import PullRequest, Release, Repository, WorkflowRun
from app.models.issue import Issue
from app.services.github_mapping import parse_github_datetime


_OPERATION_SOURCE = {
    "workflow_run": "actions",
    "pull_request": "pull_requests",
    "release": "releases",
    "issues": "issues",
}


def _login(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    raw = value.get("login") or value.get("name")
    return str(raw) if raw else None


def _workflow_values(payload: dict[str, Any]) -> tuple[int, dict[str, Any]] | None:
    run = payload.get("workflow_run") or {}
    if not isinstance(run, dict) or not run.get("id"):
        return None
    started = parse_github_datetime(run.get("run_started_at"))
    updated = parse_github_datetime(run.get("updated_at"))
    duration: int | None = None
    if started and updated and str(run.get("status") or "") == "completed":
        duration = max(0, int((updated - started).total_seconds()))
    actor = run.get("actor") or run.get("triggering_actor") or {}
    return int(run["id"]), {
        "name": str(run.get("name") or "GitHub Actions"),
        "display_title": run.get("display_title"),
        "event": run.get("event"),
        "status": str(run.get("status") or "unknown"),
        "conclusion": run.get("conclusion"),
        "head_branch": run.get("head_branch"),
        "head_sha": run.get("head_sha"),
        "run_number": run.get("run_number"),
        "run_attempt": run.get("run_attempt"),
        "html_url": str(run.get("html_url") or ""),
        "actor_login": _login(actor),
        "github_created_at": parse_github_datetime(run.get("created_at")),
        "github_updated_at": updated,
        "run_started_at": started,
        "duration_seconds": duration,
    }


def _pull_values(payload: dict[str, Any]) -> tuple[int, dict[str, Any]] | None:
    pull = payload.get("pull_request") or {}
    if not isinstance(pull, dict) or not pull.get("id"):
        return None
    head = pull.get("head") or {}
    base = pull.get("base") or {}
    return int(pull["id"]), {
        "number": int(pull.get("number") or payload.get("number") or 0),
        "title": str(pull.get("title") or "Pull request"),
        "state": str(pull.get("state") or "open"),
        "draft": bool(pull.get("draft", False)),
        "html_url": str(pull.get("html_url") or ""),
        "user_login": _login(pull.get("user")),
        "head_ref": head.get("ref") if isinstance(head, dict) else None,
        "base_ref": base.get("ref") if isinstance(base, dict) else None,
        "mergeable_state": pull.get("mergeable_state"),
        "github_created_at": parse_github_datetime(pull.get("created_at")),
        "github_updated_at": parse_github_datetime(pull.get("updated_at")),
        "closed_at": parse_github_datetime(pull.get("closed_at")),
        "merged_at": parse_github_datetime(pull.get("merged_at")),
    }


def _release_values(payload: dict[str, Any]) -> tuple[int, dict[str, Any]] | None:
    release = payload.get("release") or {}
    if not isinstance(release, dict) or not release.get("id"):
        return None
    return int(release["id"]), {
        "tag_name": str(release.get("tag_name") or "untagged"),
        "name": release.get("name"),
        "draft": bool(release.get("draft", False)),
        "prerelease": bool(release.get("prerelease", False)),
        "html_url": str(release.get("html_url") or ""),
        "target_commitish": release.get("target_commitish"),
        "github_created_at": parse_github_datetime(release.get("created_at")),
        "published_at": parse_github_datetime(release.get("published_at")),
    }


def _issue_values(payload: dict[str, Any]) -> tuple[int, dict[str, Any]] | None:
    issue = payload.get("issue") or {}
    if not isinstance(issue, dict) or not issue.get("id"):
        return None
    labels = issue.get("labels") or []
    label_names = [
        str(item.get("name"))
        for item in labels
        if isinstance(item, dict) and item.get("name")
    ]
    return int(issue["id"]), {
        "number": int(issue.get("number") or payload.get("number") or 0),
        "title": str(issue.get("title") or "Issue"),
        "state": str(issue.get("state") or "open"),
        "html_url": str(issue.get("html_url") or ""),
        "user_login": _login(issue.get("user")),
        "comments": int(issue.get("comments") or 0),
        "locked": bool(issue.get("locked", False)),
        "labels_text": ", ".join(label_names) or None,
        "github_created_at": parse_github_datetime(issue.get("created_at")),
        "github_updated_at": parse_github_datetime(issue.get("updated_at")),
        "closed_at": parse_github_datetime(issue.get("closed_at")),
    }


def operational_values(
    event: str,
    payload: dict[str, Any],
) -> tuple[type[Any], int, dict[str, Any]] | None:
    mapper = {
        "workflow_run": (WorkflowRun, _workflow_values),
        "pull_request": (PullRequest, _pull_values),
        "release": (Release, _release_values),
        "issues": (Issue, _issue_values),
    }.get(event)
    if mapper is None:
        return None
    model, factory = mapper
    values = factory(payload)
    if values is None:
        return None
    github_id, mapped = values
    return model, github_id, mapped


async def materialize_operational_event(
    session: AsyncSession,
    *,
    repository: Repository,
    event: str,
    payload: dict[str, Any],
    observed_at: datetime,
) -> bool:
    """Upsert do estado operacional diretamente a partir do webhook.

    O WebSocket só é publicado depois do commit no endpoint de webhook. Portanto,
    quando o frontend recebe o evento e relê /operations/*, a linha correspondente
    já está materializada; Celery fica somente como reconciliação/enriquecimento.
    """
    resolved = operational_values(event, payload)
    if resolved is None:
        return False
    model, github_id, values = resolved
    item = (
        await session.execute(
            select(model).where(
                model.repository_id == repository.id,
                model.github_id == github_id,
            )
        )
    ).scalar_one_or_none()
    if item is None:
        item = model(repository_id=repository.id, github_id=github_id, **values)
        session.add(item)
    else:
        for key, value in values.items():
            setattr(item, key, value)

    source_key = _OPERATION_SOURCE[event]
    extra = dict(repository.extra_data or {})
    sources = dict(extra.get("sync_sources") or {})
    source = dict(sources.get(source_key) or {})
    source.update(
        {
            "observed": True,
            "observed_at": observed_at.isoformat(),
            "transport": "webhook",
            "last_github_id": github_id,
        }
    )
    source["count"] = max(1, int(source.get("count") or source.get("run_count") or 0))
    sources[source_key] = source
    extra["sync_sources"] = sources
    repository.extra_data = extra
    await session.flush()
    return True
