from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.database import session_scope
from app.models.github import Repository
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


def _latest_evidence(
    evidence: dict[str, dict[str, Any]],
) -> tuple[str | None, datetime | None, str | None]:
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
    """Recalcula atividade usando somente evidências já coletadas.

    A coleta principal de GitHub já lê commits, PRs, issues, Actions e releases. A
    versão anterior repetia chamadas para PRs/issues/events e multiplicava o consumo
    de rate limit. Eventos recebidos por webhook são gravados em repository_event e
    preservados junto às demais fontes.
    """

    repository_uuid = uuid.UUID(str(repository_id))
    async with session_scope() as session:
        repository = await session.get(Repository, repository_uuid)
        if not repository:
            raise ValueError("Repositório monitorado não encontrado.")
        evidence = dict((repository.extra_data or {}).get("activity_sources") or {})
        source, last_activity_at, summary = _latest_evidence(evidence)
        observed_at = datetime.now(UTC)
        repository.last_activity_at = last_activity_at
        repository.last_activity_type = source
        repository.last_activity_summary = summary
        repository.activity_observed_at = observed_at
        repository.extra_data = {
            **(repository.extra_data or {}),
            "activity_sources": evidence,
            "activity_observed_at": observed_at.isoformat(),
        }
        return {
            "repository_id": str(repository_uuid),
            "observed": bool(evidence),
            "last_activity_at": last_activity_at.isoformat() if last_activity_at else None,
            "last_activity_type": source,
            "last_activity_summary": summary,
            "sources": evidence,
            "warnings": (repository.extra_data or {}).get("activity_warnings") or {},
        }


async def sync_repository_with_activity(repository_id: uuid.UUID | str) -> dict[str, Any]:
    await sync_repository(repository_id)
    return await refresh_repository_activity(repository_id)
