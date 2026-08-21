from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.core.database import session_scope
from app.core.encryption import EncryptionService
from app.models.activity import NotificationSeverity
from app.models.github import GitHubConnection, Repository
from app.models.inactivity import (
    InactivityActionLog,
    InactivityPolicy,
    InactivityPolicyRepository,
)
from app.services.github_client import GitHubClient
from app.services.github_mapping import apply_repository_base, parse_github_datetime
from app.services.notifications import create_notification


UNIT_MULTIPLIERS = {
    "hours": timedelta(hours=1),
    "days": timedelta(days=1),
    "weeks": timedelta(weeks=1),
    "months": timedelta(days=30),
}


def timeout_delta(value: int, unit: str) -> timedelta:
    base = UNIT_MULTIPLIERS.get(unit)
    if base is None:
        raise ValueError(f"Unidade de timeout inválida: {unit}")
    return base * value


def repository_activity_for_sources(
    repository: Repository,
    sources: list[str],
) -> tuple[datetime | None, str | None, str | None]:
    payload = repository.extra_data or {}
    evidence = payload.get("activity_sources") or {}
    candidates: list[tuple[datetime, str, str]] = []
    for source in sources:
        item = evidence.get(source)
        if not isinstance(item, dict):
            continue
        when = parse_github_datetime(str(item.get("at") or ""))
        if when:
            candidates.append((when, source, str(item.get("summary") or source)))
    if not candidates:
        return None, None, None
    when, source, summary = max(candidates, key=lambda item: item[0])
    return when, source, summary


async def _already_notified(
    policy_id: uuid.UUID,
    repository_id: uuid.UUID,
    last_activity_at: datetime,
) -> bool:
    async with session_scope() as session:
        result = await session.execute(
            select(InactivityActionLog.id)
            .where(
                InactivityActionLog.policy_id == policy_id,
                InactivityActionLog.repository_id == repository_id,
                InactivityActionLog.action == "notify",
                InactivityActionLog.status == "success",
                InactivityActionLog.last_activity_at == last_activity_at,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None


async def evaluate_inactivity_policies(
    *,
    user_id: uuid.UUID | None = None,
    policy_id: uuid.UUID | None = None,
) -> dict[str, int]:
    now = datetime.now(UTC)
    async with session_scope() as session:
        query = select(InactivityPolicy).where(InactivityPolicy.enabled.is_(True))
        if user_id is not None:
            query = query.where(InactivityPolicy.user_id == user_id)
        if policy_id is not None:
            query = query.where(InactivityPolicy.id == policy_id)
        policies = list((await session.execute(query)).scalars().all())

    result_counts = {
        "policies": len(policies),
        "repositories": 0,
        "due": 0,
        "privatized": 0,
        "notified": 0,
        "skipped": 0,
        "failed": 0,
    }

    for policy in policies:
        async with session_scope() as session:
            rows = (
                await session.execute(
                    select(Repository, GitHubConnection)
                    .join(
                        InactivityPolicyRepository,
                        InactivityPolicyRepository.repository_id == Repository.id,
                    )
                    .join(GitHubConnection, Repository.connection_id == GitHubConnection.id)
                    .where(
                        InactivityPolicyRepository.policy_id == policy.id,
                        GitHubConnection.user_id == policy.user_id,
                        Repository.monitoring_enabled.is_(True),
                    )
                    .order_by(Repository.full_name.asc())
                )
            ).all()

        result_counts["repositories"] += len(rows)
        delta = timeout_delta(policy.timeout_value, policy.timeout_unit)

        for repository, connection in rows:
            last_activity_at, source, summary = repository_activity_for_sources(
                repository, list(policy.activity_sources or [])
            )
            if last_activity_at is None or repository.activity_observed_at is None:
                result_counts["skipped"] += 1
                continue

            threshold_at = last_activity_at + delta
            if now < threshold_at:
                result_counts["skipped"] += 1
                continue

            result_counts["due"] += 1
            reason = (
                f"Sem atividade nas fontes selecionadas desde {last_activity_at.isoformat()} "
                f"({source or 'fonte desconhecida'}: {summary or 'sem resumo'}). "
                f"Timeout da política: {policy.timeout_value} {policy.timeout_unit}."
            )

            if policy.action == "notify":
                if await _already_notified(policy.id, repository.id, last_activity_at):
                    result_counts["skipped"] += 1
                    continue
                async with session_scope() as session:
                    session.add(
                        InactivityActionLog(
                            policy_id=policy.id,
                            repository_id=repository.id,
                            repository_full_name=repository.full_name,
                            action="notify",
                            status="success",
                            previous_private=repository.private,
                            last_activity_at=last_activity_at,
                            threshold_at=threshold_at,
                            reason=reason,
                            result={"source": source, "summary": summary},
                            error=None,
                            created_at=now,
                        )
                    )
                    await create_notification(
                        session,
                        user_id=policy.user_id,
                        repository_id=repository.id,
                        event_type="inactivity.timeout",
                        severity=NotificationSeverity.WARNING,
                        title=f"Inatividade detectada: {repository.full_name}",
                        message=reason,
                        url=repository.html_url,
                        payload={"policy_id": str(policy.id), "action": "notify"},
                    )
                result_counts["notified"] += 1
                continue

            if policy.action != "private":
                result_counts["skipped"] += 1
                continue
            if repository.private:
                result_counts["skipped"] += 1
                continue
            if not connection.token_encrypted:
                result_counts["failed"] += 1
                continue

            token = EncryptionService().decrypt(connection.token_encrypted)
            client = GitHubClient(token, api_url=connection.api_url)
            try:
                remote = await client.update_repository(repository.full_name, private=True)
                async with session_scope() as session:
                    current = await session.get(Repository, repository.id)
                    if current:
                        apply_repository_base(current, remote)
                    session.add(
                        InactivityActionLog(
                            policy_id=policy.id,
                            repository_id=repository.id,
                            repository_full_name=repository.full_name,
                            action="private",
                            status="success",
                            previous_private=False,
                            last_activity_at=last_activity_at,
                            threshold_at=threshold_at,
                            reason=reason,
                            result={"private": True, "source": source, "summary": summary},
                            error=None,
                            created_at=now,
                        )
                    )
                    await create_notification(
                        session,
                        user_id=policy.user_id,
                        repository_id=repository.id,
                        event_type="inactivity.auto_private",
                        severity=NotificationSeverity.WARNING,
                        title=f"Repositório privado por inatividade: {repository.full_name}",
                        message=reason,
                        url=repository.html_url,
                        payload={"policy_id": str(policy.id), "action": "private"},
                    )
                result_counts["privatized"] += 1
            except Exception as exc:
                async with session_scope() as session:
                    session.add(
                        InactivityActionLog(
                            policy_id=policy.id,
                            repository_id=repository.id,
                            repository_full_name=repository.full_name,
                            action="private",
                            status="failed",
                            previous_private=repository.private,
                            last_activity_at=last_activity_at,
                            threshold_at=threshold_at,
                            reason=reason,
                            result={},
                            error=str(exc)[:4000],
                            created_at=now,
                        )
                    )
                    await create_notification(
                        session,
                        user_id=policy.user_id,
                        repository_id=repository.id,
                        event_type="inactivity.auto_private_failed",
                        severity=NotificationSeverity.ERROR,
                        title=f"Falha ao privar: {repository.full_name}",
                        message=f"{reason} GitHub recusou a operação: {exc}",
                        url=repository.html_url,
                        payload={"policy_id": str(policy.id), "action": "private"},
                    )
                result_counts["failed"] += 1
            finally:
                await client.close()

        async with session_scope() as session:
            current_policy = await session.get(InactivityPolicy, policy.id)
            if current_policy:
                current_policy.last_evaluated_at = now

    return result_counts
