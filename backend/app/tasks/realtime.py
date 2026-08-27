from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import dispose_engine, session_scope
from app.core.encryption import EncryptionService
from app.models.github import ConnectionStatus, GitHubConnection, Repository
from app.services.github_client import GitHubClient
from app.services.realtime import publish_event
from app.services.webhook_provisioning import ensure_repository_webhook
from app.tasks.celery_app import celery_app

WEBHOOK_RECHECK_AFTER = timedelta(hours=24)
WEBHOOK_ERROR_RETRY_AFTER = timedelta(hours=2)
MAX_REPOSITORIES_PER_CONNECTION = 25


def run_async(coro):
    async def runner():
        try:
            return await coro
        finally:
            await dispose_engine()

    return asyncio.run(runner())


def _timestamp(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _needs_recheck(repository: Repository, now: datetime) -> bool:
    state = (repository.extra_data or {}).get("realtime_webhook")
    if not isinstance(state, dict):
        return True
    status = str(state.get("status") or "")
    checked_at = _timestamp(state.get("verified_at") or state.get("attempted_at"))
    if checked_at is None:
        return True
    interval = WEBHOOK_RECHECK_AFTER if status == "ok" else WEBHOOK_ERROR_RETRY_AFTER
    return now - checked_at >= interval


@celery_app.task(name="realtime.ensure_repository_webhooks")
def ensure_repository_webhooks_task():
    async def execute():
        settings = get_settings()
        webhook_url = (
            f"{settings.public_base_url.rstrip('/')}{settings.api_v1_prefix}/webhooks/github"
        )
        now = datetime.now(UTC)
        summary = {"checked": 0, "created": 0, "updated": 0, "failed": 0, "skipped": 0}

        async with session_scope() as session:
            connections = (
                await session.execute(
                    select(GitHubConnection).where(
                        GitHubConnection.status == ConnectionStatus.ACTIVE,
                        GitHubConnection.token_encrypted.is_not(None),
                    )
                )
            ).scalars().all()

        for connection in connections:
            token = EncryptionService().decrypt(connection.token_encrypted or "")
            async with session_scope() as session:
                repositories = (
                    await session.execute(
                        select(Repository)
                        .where(
                            Repository.connection_id == connection.id,
                            Repository.monitoring_enabled.is_(True),
                            Repository.archived.is_(False),
                            Repository.disabled.is_(False),
                        )
                        .order_by(Repository.last_synced_at.asc().nullsfirst())
                    )
                ).scalars().all()
                candidates = [repo for repo in repositories if _needs_recheck(repo, now)]
                summary["skipped"] += max(0, len(repositories) - len(candidates))
                candidates = candidates[:MAX_REPOSITORIES_PER_CONNECTION]

            if not candidates:
                continue

            async with GitHubClient(token, api_url=connection.api_url) as client:
                for candidate in candidates:
                    summary["checked"] += 1
                    state: dict[str, object]
                    try:
                        result = await ensure_repository_webhook(
                            client,
                            full_name=candidate.full_name,
                            webhook_url=webhook_url,
                            secret=settings.github_webhook_secret,
                        )
                        summary["created" if result.get("created") else "updated"] += 1
                        state = {
                            "status": "ok",
                            "webhook_id": result.get("id"),
                            "url": webhook_url,
                            "events": result.get("events") or [],
                            "verified_at": now.isoformat(),
                            "error": None,
                        }
                    except Exception as exc:
                        summary["failed"] += 1
                        state = {
                            "status": "error",
                            "url": webhook_url,
                            "attempted_at": now.isoformat(),
                            "error": f"{type(exc).__name__}: {exc}"[:1000],
                        }

                    async with session_scope() as session:
                        repository = await session.get(Repository, candidate.id)
                        if repository:
                            extra = dict(repository.extra_data or {})
                            extra["realtime_webhook"] = state
                            repository.extra_data = extra

            try:
                await publish_event(
                    connection.user_id,
                    "realtime.webhooks_reconciled",
                    {
                        "connection_id": str(connection.id),
                        "connection_name": connection.name,
                        **summary,
                    },
                )
            except Exception:
                pass

        return summary

    return run_async(execute())
