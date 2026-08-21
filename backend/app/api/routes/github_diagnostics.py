from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.encryption import EncryptionService
from app.models.github import GitHubConnection
from app.schemas.github import GitHubConnectionDiagnostics
from app.services.github_client import GitHubAPIError, GitHubClient

router = APIRouter(prefix="/github", tags=["GitHub"])


@router.get(
    "/connections/{connection_id}/diagnostics",
    response_model=GitHubConnectionDiagnostics,
)
async def diagnose_connection(
    connection_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> GitHubConnectionDiagnostics:
    result = await db.execute(
        select(GitHubConnection).where(
            GitHubConnection.id == connection_id,
            GitHubConnection.user_id == current_user.id,
        )
    )
    connection = result.scalar_one_or_none()
    if not connection:
        raise HTTPException(status_code=404, detail="Conexão GitHub não encontrada.")
    if not connection.token_encrypted:
        raise HTTPException(status_code=400, detail="Conexão sem credencial operacional.")

    token = EncryptionService().decrypt(connection.token_encrypted)
    settings = get_settings()
    warnings: list[str] = []
    try:
        async with GitHubClient(token, api_url=connection.api_url) as client:
            profile = await client.get_authenticated_user()
            repositories = await client.list_repositories(limit=settings.github_repository_limit)
            private_count = sum(1 for item in repositories if bool(item.get("private")))
            writable_count = sum(
                1
                for item in repositories
                if bool((item.get("permissions") or {}).get("push"))
            )
            admin_count = sum(
                1
                for item in repositories
                if bool((item.get("permissions") or {}).get("admin"))
            )

            checked = 0
            observed = 0
            for item in repositories[:5]:
                full_name = str(item.get("full_name") or "")
                if not full_name:
                    continue
                checked += 1
                before = dict(client.optional_warnings)
                runs = await client.list_workflow_runs(full_name, limit=1)
                warning = client.optional_warnings.get("actions_runs")
                if warning and warning != before.get("actions_runs"):
                    warnings.append(f"{full_name}: {warning}")
                else:
                    observed += 1
                    if not runs:
                        await client.list_workflows(full_name, limit=1)
                        warning = client.optional_warnings.get("actions_workflows")
                        if warning:
                            warnings.append(f"{full_name}: {warning}")

            connection.rate_limit_remaining = client.rate_limit_remaining
            connection.rate_limit_reset_at = client.rate_limit_reset_at
            connection.last_error = None
            await db.commit()

            return GitHubConnectionDiagnostics(
                connected=True,
                github_login=str(profile.get("login") or connection.github_login),
                accessible_repositories=len(repositories),
                private_repositories=private_count,
                writable_repositories=writable_count,
                admin_repositories=admin_count,
                actions_samples_checked=checked,
                actions_samples_observed=observed,
                rate_limit_remaining=client.rate_limit_remaining,
                rate_limit_reset_at=client.rate_limit_reset_at,
                oauth_scopes=list(client.oauth_scopes),
                warnings=warnings[:20],
                checked_at=datetime.now(UTC),
            )
    except GitHubAPIError as exc:
        connection.last_error = str(exc)[:4000]
        await db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
