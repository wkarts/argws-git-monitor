from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.core.database import session_scope
from app.core.encryption import EncryptionService
from app.models.github import ConnectionStatus, Repository
from app.services.github_client import GitHubClient
from app.services.github_mapping import parse_github_datetime
from app.services.github_sync import sync_repository

DEFAULT_ACTIVITY_SOURCES = [
    "push",
    "commit",
    "pull_request",
    "issue",
    "actions",
    "release",
    "repository_event",
    "repository_metadata",
]

EVENT_SOURCE_MAP = {
    "PushEvent": "push",
    "CreateEvent": "repository_event",
    "DeleteEvent": "repository_event",
    "ForkEvent": "repository_event",
    "MemberEvent": "repository_event",
    "PublicEvent": "repository_event",
    "PullRequestEvent": "pull_request",
    "PullRequestReviewEvent": "pull_request",
    "PullRequestReviewCommentEvent": "pull_request",
    "IssuesEvent": "issue",
    "IssueCommentEvent": "issue",
    "ReleaseEvent": "release",
}


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = value if value.tzinfo else value.replace(tzinfo=UTC)
    return normalized.isoformat()


def _candidate(
    evidence: dict[str, dict[str, Any]],
    source: str,
    when: datetime | None,
    summary: str,
) -> None:
    if when is None:
        return
    normalized = when if when.tzinfo else when.replace(tzinfo=UTC)
    current = evidence.get(source)
    current_at = parse_github_datetime(str(current.get("at"))) if current else None
    if current_at is None or normalized > current_at:
        evidence[source] = {"at": _iso(normalized), "summary": summary}


def _latest_evidence(evidence: dict[str, dict[str, Any]]) -> tuple[str | None, datetime | None, str | None]:
    candidates: list[tuple[datetime, str, str]] = []
    for source, item in evidence.items():
        when = parse_github_datetime(str(item.get("at") or ""))
        if when:
            candidates.append((when, source, str(item.get("summary") or source)))
    if not candidates:
        return None, None, None
    when, source, summary = max(candidates, key=lambda item: item[0])
    return source, when, summary


async def refresh_repository_activity(repository_id: uuid.UUID | str) -> dict[str, Any]:
    repository_uuid = uuid.UUID(str(repository_id))
    async with session_scope() as session:
        result = await session.execute(
            select(Repository)
            .options(joinedload(Repository.connection))
            .where(Repository.id == repository_uuid)
        )
        repository = result.scalar_one_or_none()
        if not repository:
            raise ValueError("Repositório monitorado não encontrado.")
        if repository.connection.status == ConnectionStatus.DEMO:
            return {"repository_id": str(repository_uuid), "observed": False, "sources": {}}
        if not repository.connection.token_encrypted:
            raise ValueError("Conexão GitHub sem credencial.")

        full_name = repository.full_name
        token = EncryptionService().decrypt(repository.connection.token_encrypted)
        api_url = repository.connection.api_url
        base_evidence: dict[str, dict[str, Any]] = {}
        _candidate(base_evidence, "push", repository.pushed_at, "Último push informado pelo GitHub")
        _candidate(base_evidence, "commit", repository.latest_commit_at, "Último commit observado")
        _candidate(base_evidence, "actions", repository.latest_workflow_at, "Última execução GitHub Actions")
        _candidate(base_evidence, "release", repository.latest_release_at, "Última release publicada")
        _candidate(
            base_evidence,
            "repository_metadata",
            repository.github_updated_at,
            "Metadados do repositório atualizados",
        )

    client = GitHubClient(token, api_url=api_url)
    try:
        events = await client.optional_paginate(
            "repository_events",
            f"/repos/{full_name}/events",
            limit=100,
            empty_statuses={403, 404},
        )
        pulls = await client.optional_paginate(
            "pull_request_activity",
            f"/repos/{full_name}/pulls",
            params={"state": "all", "sort": "updated", "direction": "desc"},
            limit=30,
            empty_statuses={403, 404},
        )
        issues = await client.optional_paginate(
            "issue_activity",
            f"/repos/{full_name}/issues",
            params={"state": "all", "sort": "updated", "direction": "desc"},
            limit=30,
            empty_statuses={403, 404},
        )

        evidence = dict(base_evidence)
        for item in pulls:
            _candidate(
                evidence,
                "pull_request",
                parse_github_datetime(item.get("updated_at")),
                f"PR #{item.get('number')} atualizado: {item.get('title') or 'sem título'}",
            )
        for item in issues:
            if item.get("pull_request"):
                continue
            _candidate(
                evidence,
                "issue",
                parse_github_datetime(item.get("updated_at")),
                f"Issue #{item.get('number')} atualizada: {item.get('title') or 'sem título'}",
            )
        for item in events:
            event_type = str(item.get("type") or "RepositoryEvent")
            source = EVENT_SOURCE_MAP.get(event_type, "repository_event")
            actor = str((item.get("actor") or {}).get("login") or "GitHub")
            _candidate(
                evidence,
                source,
                parse_github_datetime(item.get("created_at")),
                f"{event_type} por {actor}",
            )

        source, last_activity_at, summary = _latest_evidence(evidence)
        observed_at = datetime.now(UTC)
        async with session_scope() as session:
            repository = await session.get(Repository, repository_uuid)
            if not repository:
                return {"repository_id": str(repository_uuid), "observed": False, "sources": evidence}
            repository.last_activity_at = last_activity_at
            repository.last_activity_type = source
            repository.last_activity_summary = summary
            repository.activity_observed_at = observed_at
            repository.extra_data = {
                **(repository.extra_data or {}),
                "activity_sources": evidence,
                "activity_observed_at": observed_at.isoformat(),
                "activity_warnings": client.optional_warnings,
            }
        return {
            "repository_id": str(repository_uuid),
            "observed": True,
            "last_activity_at": _iso(last_activity_at),
            "last_activity_type": source,
            "last_activity_summary": summary,
            "sources": evidence,
            "warnings": client.optional_warnings,
        }
    finally:
        await client.close()


async def sync_repository_with_activity(repository_id: uuid.UUID | str) -> dict[str, Any]:
    await sync_repository(repository_id)
    return await refresh_repository_activity(repository_id)
