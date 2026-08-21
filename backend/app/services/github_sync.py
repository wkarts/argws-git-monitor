from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import joinedload

from app.core.config import get_settings
from app.core.database import session_scope
from app.core.encryption import EncryptionService
from app.models.activity import NotificationSeverity
from app.models.github import (
    ConnectionStatus,
    GitHubConnection,
    PullRequest,
    Release,
    Repository,
    WorkflowRun,
)
from app.models.issue import Issue
from app.services.github_client import GitHubClient
from app.services.github_mapping import (
    apply_repository_base,
    parse_github_datetime,
    workflow_duration_seconds,
)
from app.services.health import FAILURE_CONCLUSIONS, calculate_repository_health
from app.services.notifications import create_notification

logger = logging.getLogger(__name__)


async def sync_connection(
    connection_id: uuid.UUID | str,
    *,
    selected_github_ids: set[int] | None = None,
    full_sync: bool = True,
) -> dict[str, int]:
    settings = get_settings()
    connection_uuid = uuid.UUID(str(connection_id))

    async with session_scope() as session:
        connection = await session.get(GitHubConnection, connection_uuid)
        if not connection:
            raise ValueError("Conexão GitHub não encontrada.")
        if connection.status == ConnectionStatus.DEMO:
            return {"repositories": 0, "synced": 0, "errors": 0}
        if not connection.token_encrypted:
            raise ValueError("Conexão sem credencial armazenada.")
        token = EncryptionService().decrypt(connection.token_encrypted)
        api_url = connection.api_url

    repository_ids: list[uuid.UUID] = []
    errors = 0
    try:
        async with GitHubClient(token, api_url=api_url) as client:
            remote_repositories = await client.list_repositories(limit=settings.github_repository_limit)
            if selected_github_ids is not None:
                remote_repositories = [
                    item for item in remote_repositories if int(item["id"]) in selected_github_ids
                ]

            async with session_scope() as session:
                connection = await session.get(GitHubConnection, connection_uuid)
                if not connection:
                    raise ValueError("Conexão GitHub removida durante a sincronização.")

                existing_result = await session.execute(
                    select(Repository).where(Repository.connection_id == connection_uuid)
                )
                existing = {item.github_id: item for item in existing_result.scalars().all()}

                for remote in remote_repositories:
                    github_id = int(remote["id"])
                    repository = existing.get(github_id)
                    if repository is None:
                        repository = Repository(connection_id=connection_uuid, github_id=github_id)
                        session.add(repository)
                    apply_repository_base(repository, remote)
                    repository.sync_error = None
                    await session.flush()
                    if repository.monitoring_enabled and not repository.archived and not repository.disabled:
                        repository_ids.append(repository.id)

                connection.status = ConnectionStatus.ACTIVE
                connection.last_error = None
                connection.rate_limit_remaining = client.rate_limit_remaining
                connection.rate_limit_reset_at = client.rate_limit_reset_at

            synced = 0
            if full_sync:
                semaphore = asyncio.Semaphore(max(1, settings.github_concurrency))

                async def sync_one(repository_id: uuid.UUID) -> bool:
                    nonlocal errors
                    async with semaphore:
                        if (
                            client.rate_limit_remaining is not None
                            and client.rate_limit_remaining < 100
                        ):
                            logger.warning(
                                "Repositório adiado por limite baixo do GitHub: "
                                "connection=%s repository=%s remaining=%s",
                                connection_uuid,
                                repository_id,
                                client.rate_limit_remaining,
                            )
                            return False
                        try:
                            await sync_repository(repository_id, client=client)
                            return True
                        except Exception as exc:
                            errors += 1
                            logger.warning(
                                "Falha ao sincronizar repositório %s: %s",
                                repository_id,
                                exc,
                            )
                            return False

                results = await asyncio.gather(
                    *(sync_one(repository_id) for repository_id in repository_ids)
                )
                synced = sum(results)

            async with session_scope() as session:
                connection = await session.get(GitHubConnection, connection_uuid)
                if connection:
                    connection.last_sync_at = datetime.now(UTC)
                    connection.rate_limit_remaining = client.rate_limit_remaining
                    connection.rate_limit_reset_at = client.rate_limit_reset_at
                    connection.last_error = (
                        f"{errors} repositório(s) apresentaram erro na sincronização."
                        if errors
                        else None
                    )
                    connection.status = ConnectionStatus.ERROR if errors else ConnectionStatus.ACTIVE

            return {
                "repositories": len(remote_repositories),
                "synced": synced,
                "errors": errors,
            }
    except Exception as exc:
        async with session_scope() as session:
            connection = await session.get(GitHubConnection, connection_uuid)
            if connection:
                connection.status = ConnectionStatus.ERROR
                connection.last_error = str(exc)[:4000]
        raise


def _source_state(
    warnings: dict[str, str],
    key: str,
    *,
    count: int,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    warning = warnings.get(key)
    return {
        "observed": warning is None,
        "count": count,
        "error": warning,
        "observed_at": datetime.now(UTC).isoformat(),
        **(extra or {}),
    }


async def sync_repository(
    repository_id: uuid.UUID | str,
    *,
    client: GitHubClient | None = None,
) -> None:
    repository_uuid = uuid.UUID(str(repository_id))
    owns_client = client is None

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
            return
        if not repository.connection.token_encrypted:
            raise ValueError("Conexão GitHub sem credencial.")
        full_name = repository.full_name
        token = EncryptionService().decrypt(repository.connection.token_encrypted)
        api_url = repository.connection.api_url

    github_client = client or GitHubClient(token, api_url=api_url)
    github_client.optional_warnings.clear()
    try:
        remote_repo = await github_client.get_repository(full_name)
        commits = await github_client.list_commits(full_name, limit=1)
        branches = await github_client.list_branches(full_name, limit=100)
        workflows = await github_client.list_workflows(full_name, limit=100)
        workflow_runs = await github_client.list_workflow_runs(full_name, limit=50)
        pull_requests = await github_client.list_pull_requests(full_name, limit=100)
        issues = await github_client.list_issues(full_name, limit=100)
        releases = await github_client.list_releases(full_name, limit=30)
        warnings = dict(github_client.optional_warnings)

        async with session_scope() as session:
            result = await session.execute(
                select(Repository)
                .options(joinedload(Repository.connection))
                .where(Repository.id == repository_uuid)
            )
            repository = result.scalar_one_or_none()
            if not repository:
                return

            previous_workflow_id = repository.latest_workflow_id
            previous_workflow_conclusion = repository.latest_workflow_conclusion
            previous_release_tag = repository.latest_release_tag

            apply_repository_base(repository, remote_repo)
            repository.branch_count = len(branches)
            repository.open_pr_count = len(pull_requests)
            repository.open_issue_count = len(issues)

            latest_commit = commits[0] if commits else None
            if latest_commit:
                commit_data = latest_commit.get("commit") or {}
                commit_author = commit_data.get("author") or {}
                api_author = latest_commit.get("author") or {}
                repository.latest_commit_sha = latest_commit.get("sha")
                repository.latest_commit_message = commit_data.get("message")
                repository.latest_commit_author = api_author.get("login") or commit_author.get("name")
                repository.latest_commit_at = parse_github_datetime(commit_author.get("date"))
            else:
                repository.latest_commit_sha = None
                repository.latest_commit_message = None
                repository.latest_commit_author = None
                repository.latest_commit_at = None

            latest_run = workflow_runs[0] if workflow_runs else None
            if latest_run:
                repository.latest_workflow_id = int(latest_run["id"])
                repository.latest_workflow_name = latest_run.get("name")
                repository.latest_workflow_status = latest_run.get("status")
                repository.latest_workflow_conclusion = latest_run.get("conclusion")
                repository.latest_workflow_url = latest_run.get("html_url")
                repository.latest_workflow_at = parse_github_datetime(latest_run.get("updated_at"))
            else:
                repository.latest_workflow_id = None
                repository.latest_workflow_name = None
                repository.latest_workflow_status = None
                repository.latest_workflow_conclusion = None
                repository.latest_workflow_url = None
                repository.latest_workflow_at = None

            latest_release = next(
                (item for item in releases if not item.get("draft")),
                releases[0] if releases else None,
            )
            if latest_release:
                repository.latest_release_tag = latest_release.get("tag_name")
                repository.latest_release_name = latest_release.get("name")
                repository.latest_release_at = parse_github_datetime(
                    latest_release.get("published_at") or latest_release.get("created_at")
                )
            else:
                repository.latest_release_tag = None
                repository.latest_release_name = None
                repository.latest_release_at = None

            repository.sync_error = None
            repository.last_synced_at = datetime.now(UTC)

            actions_observed = (
                "actions_workflows" not in warnings and "actions_runs" not in warnings
            )
            ci_configured: bool | None = len(workflows) > 0 if actions_observed else None
            health = calculate_repository_health(
                archived=repository.archived,
                disabled=repository.disabled,
                sync_error=repository.sync_error,
                pushed_at=repository.pushed_at,
                latest_workflow_status=repository.latest_workflow_status,
                latest_workflow_conclusion=repository.latest_workflow_conclusion,
                open_pr_count=repository.open_pr_count,
                open_issue_count=repository.open_issue_count,
                ci_configured=ci_configured,
            )
            repository.health_score = health.score
            repository.health_status = health.status
            repository.extra_data = {
                **(repository.extra_data or {}),
                "health_reasons": list(health.reasons),
                "health_components": health.components,
                "health_coverage": health.coverage,
                "sync_sources": {
                    "commits": _source_state(warnings, "commits", count=len(commits)),
                    "branches": _source_state(warnings, "branches", count=len(branches)),
                    "actions": _source_state(
                        warnings,
                        "actions_runs" if "actions_runs" in warnings else "actions_workflows",
                        count=len(workflow_runs),
                        extra={
                            "workflow_count": len(workflows),
                            "run_count": len(workflow_runs),
                            "observed": actions_observed,
                            "error": warnings.get("actions_runs") or warnings.get("actions_workflows"),
                        },
                    ),
                    "pull_requests": _source_state(warnings, "pull_requests", count=len(pull_requests)),
                    "issues": _source_state(warnings, "issues", count=len(issues)),
                    "releases": _source_state(warnings, "releases", count=len(releases)),
                },
            }

            await session.execute(
                delete(WorkflowRun).where(WorkflowRun.repository_id == repository.id)
            )
            for item in workflow_runs:
                session.add(
                    WorkflowRun(
                        repository_id=repository.id,
                        github_id=int(item["id"]),
                        name=str(item.get("name") or "Workflow"),
                        display_title=item.get("display_title"),
                        event=item.get("event"),
                        status=str(item.get("status") or "unknown"),
                        conclusion=item.get("conclusion"),
                        head_branch=item.get("head_branch"),
                        head_sha=item.get("head_sha"),
                        run_number=item.get("run_number"),
                        run_attempt=item.get("run_attempt"),
                        html_url=str(item.get("html_url") or repository.html_url),
                        actor_login=(item.get("actor") or {}).get("login"),
                        github_created_at=parse_github_datetime(item.get("created_at")),
                        github_updated_at=parse_github_datetime(item.get("updated_at")),
                        run_started_at=parse_github_datetime(item.get("run_started_at")),
                        duration_seconds=workflow_duration_seconds(item),
                    )
                )

            await session.execute(
                delete(PullRequest).where(PullRequest.repository_id == repository.id)
            )
            for item in pull_requests:
                session.add(
                    PullRequest(
                        repository_id=repository.id,
                        github_id=int(item["id"]),
                        number=int(item["number"]),
                        title=str(item.get("title") or "Pull request"),
                        state=str(item.get("state") or "open"),
                        draft=bool(item.get("draft", False)),
                        html_url=str(item.get("html_url") or repository.html_url),
                        user_login=(item.get("user") or {}).get("login"),
                        head_ref=(item.get("head") or {}).get("ref"),
                        base_ref=(item.get("base") or {}).get("ref"),
                        mergeable_state=item.get("mergeable_state"),
                        github_created_at=parse_github_datetime(item.get("created_at")),
                        github_updated_at=parse_github_datetime(item.get("updated_at")),
                        closed_at=parse_github_datetime(item.get("closed_at")),
                        merged_at=parse_github_datetime(item.get("merged_at")),
                    )
                )

            await session.execute(delete(Issue).where(Issue.repository_id == repository.id))
            for item in issues:
                labels = [
                    str(label.get("name") or "")
                    for label in (item.get("labels") or [])
                    if isinstance(label, dict) and label.get("name")
                ]
                session.add(
                    Issue(
                        repository_id=repository.id,
                        github_id=int(item["id"]),
                        number=int(item["number"]),
                        title=str(item.get("title") or "Issue"),
                        state=str(item.get("state") or "open"),
                        html_url=str(item.get("html_url") or f"{repository.html_url}/issues"),
                        user_login=(item.get("user") or {}).get("login"),
                        comments=int(item.get("comments") or 0),
                        locked=bool(item.get("locked", False)),
                        labels_text=", ".join(labels) or None,
                        github_created_at=parse_github_datetime(item.get("created_at")),
                        github_updated_at=parse_github_datetime(item.get("updated_at")),
                        closed_at=parse_github_datetime(item.get("closed_at")),
                    )
                )

            await session.execute(delete(Release).where(Release.repository_id == repository.id))
            for item in releases:
                session.add(
                    Release(
                        repository_id=repository.id,
                        github_id=int(item["id"]),
                        tag_name=str(item.get("tag_name") or "sem-tag"),
                        name=item.get("name"),
                        draft=bool(item.get("draft", False)),
                        prerelease=bool(item.get("prerelease", False)),
                        html_url=str(item.get("html_url") or repository.html_url),
                        target_commitish=item.get("target_commitish"),
                        github_created_at=parse_github_datetime(item.get("created_at")),
                        published_at=parse_github_datetime(item.get("published_at")),
                    )
                )

            new_conclusion = (repository.latest_workflow_conclusion or "").lower()
            previous_conclusion = (previous_workflow_conclusion or "").lower()
            if previous_workflow_id and repository.latest_workflow_id != previous_workflow_id:
                if new_conclusion in FAILURE_CONCLUSIONS:
                    await create_notification(
                        session,
                        user_id=repository.connection.user_id,
                        repository_id=repository.id,
                        event_type="workflow.failed",
                        severity=NotificationSeverity.ERROR,
                        title=f"Build falhou: {repository.full_name}",
                        message=(
                            f"{repository.latest_workflow_name or 'Workflow'} terminou como "
                            f"{new_conclusion}."
                        ),
                        url=repository.latest_workflow_url,
                        payload={"run_id": repository.latest_workflow_id},
                    )
                elif new_conclusion == "success" and previous_conclusion in FAILURE_CONCLUSIONS:
                    await create_notification(
                        session,
                        user_id=repository.connection.user_id,
                        repository_id=repository.id,
                        event_type="workflow.recovered",
                        severity=NotificationSeverity.SUCCESS,
                        title=f"Build recuperada: {repository.full_name}",
                        message=f"{repository.latest_workflow_name or 'Workflow'} voltou a concluir com sucesso.",
                        url=repository.latest_workflow_url,
                        payload={"run_id": repository.latest_workflow_id},
                    )

            if (
                previous_release_tag
                and repository.latest_release_tag
                and repository.latest_release_tag != previous_release_tag
            ):
                await create_notification(
                    session,
                    user_id=repository.connection.user_id,
                    repository_id=repository.id,
                    event_type="release.published",
                    severity=NotificationSeverity.SUCCESS,
                    title=f"Nova release: {repository.full_name}",
                    message=f"A versão {repository.latest_release_tag} foi publicada.",
                    url=(latest_release or {}).get("html_url"),
                    payload={"tag": repository.latest_release_tag},
                )
    except Exception as exc:
        async with session_scope() as session:
            repository = await session.get(Repository, repository_uuid)
            if repository:
                repository.sync_error = str(exc)[:4000]
                repository.last_synced_at = datetime.now(UTC)
                source_data = (repository.extra_data or {}).get("sync_sources") or {}
                actions_source = source_data.get("actions") or {}
                ci_configured = (
                    int(actions_source.get("workflow_count") or 0) > 0
                    if actions_source.get("observed") is True
                    else None
                )
                health = calculate_repository_health(
                    archived=repository.archived,
                    disabled=repository.disabled,
                    sync_error=repository.sync_error,
                    pushed_at=repository.pushed_at,
                    latest_workflow_status=repository.latest_workflow_status,
                    latest_workflow_conclusion=repository.latest_workflow_conclusion,
                    open_pr_count=repository.open_pr_count,
                    open_issue_count=repository.open_issue_count,
                    ci_configured=ci_configured,
                )
                repository.health_score = health.score
                repository.health_status = health.status
        raise
    finally:
        if owns_client:
            await github_client.close()


async def get_repository_client(
    repository_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
) -> tuple[Repository, GitHubClient]:
    async with session_scope() as session:
        result = await session.execute(
            select(Repository)
            .join(GitHubConnection)
            .options(joinedload(Repository.connection))
            .where(Repository.id == repository_id, GitHubConnection.user_id == user_id)
        )
        repository = result.scalar_one_or_none()
        if not repository:
            raise ValueError("Repositório não encontrado.")
        if not repository.connection.token_encrypted:
            raise ValueError("A conexão deste repositório não possui token operacional.")
        token = EncryptionService().decrypt(repository.connection.token_encrypted)
        return repository, GitHubClient(token, api_url=repository.connection.api_url)
