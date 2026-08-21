from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.github import GitHubConnection, Repository
from app.schemas.github_tools import ToolResult
from app.services.audit import record_audit
from app.services.repository_compliance import normalize_full_name, validate_personal_owner

router = APIRouter(prefix="/github-tools", tags=["GitHub Tools"])


class LocalComplianceCleanupRequest(BaseModel):
    full_name: str = Field(min_length=3, max_length=520)
    confirmation: str = Field(min_length=1, max_length=600)


@router.post(
    "/connections/{connection_id}/compliance/remove-local",
    response_model=ToolResult,
)
async def remove_local_compliance_repository(
    connection_id: uuid.UUID,
    payload: LocalComplianceCleanupRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> ToolResult:
    result = await db.execute(
        select(GitHubConnection).where(
            GitHubConnection.id == connection_id,
            GitHubConnection.user_id == current_user.id,
        )
    )
    connection = result.scalar_one_or_none()
    if connection is None:
        raise HTTPException(status_code=404, detail="Conexão GitHub não encontrada.")

    try:
        full_name = normalize_full_name(payload.full_name)
        validate_personal_owner(full_name, connection.github_login)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    expected = f"REMOVER DO MONITOR {full_name}"
    if payload.confirmation != expected:
        raise HTTPException(status_code=400, detail=f"Digite exatamente: {expected}")

    local_result = await db.execute(
        select(Repository).where(
            Repository.connection_id == connection.id,
            Repository.full_name == full_name,
        )
    )
    repository = local_result.scalar_one_or_none()
    removed = repository is not None
    if repository is not None:
        await db.delete(repository)

    await record_audit(
        db,
        action="github.repository_compliance_local_removed",
        user_id=current_user.id,
        entity_type="repository",
        entity_id=full_name,
        details={
            "connection_id": str(connection.id),
            "github_login": connection.github_login,
            "removed": removed,
            "remote_repository_unchanged": True,
            "reason": "remote_delete_blocked_or_user_requested_local_cleanup",
        },
    )
    await db.commit()

    return ToolResult(
        message=(
            f"{full_name} foi removido somente do Git Monitor. "
            "O repositório remoto continua na conta GitHub enquanto a restrição legal impedir a exclusão."
        ),
        data={
            "full_name": full_name,
            "local_removed": removed,
            "remote_repository_unchanged": True,
            "support_required": True,
        },
    )
