from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.encryption import EncryptionService
from app.models.github import GitHubConnection, Repository
from app.services.github_client import GitHubAPIError, GitHubClient
from app.services.realtime import publish_event

router = APIRouter(prefix="/repository-controls", tags=["Controles de Repositório"])


class ActionsUpdate(BaseModel):
    enabled: bool
    cancel_in_progress: bool = True


async def _owned_repository(
    db: DbSession,
    repository_id: uuid.UUID,
    user_id: uuid.UUID,
) -> tuple[Repository, GitHubConnection]:
    result = await db.execute(
        select(Repository, GitHubConnection)
        .join(GitHubConnection, Repository.connection_id == GitHubConnection.id)
        .where(
            Repository.id == repository_id,
            GitHubConnection.user_id == user_id,
        )
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Repositório não encontrado.")
    repository, connection = row
    return repository, connection


def _blacklist_info(repository: Repository) -> dict[str, object] | None:
    value = (repository.extra_data or {}).get("blacklist")
    return value if isinstance(value, dict) else None


@router.get("/blacklist")
async def list_blacklist(current_user: CurrentUser, db: DbSession) -> list[dict[str, object]]:
    rows = (
        await db.execute(
            select(Repository, GitHubConnection)
            .join(GitHubConnection, Repository.connection_id == GitHubConnection.id)
            .where(
                GitHubConnection.user_id == current_user.id,
                Repository.monitoring_enabled.is_(False),
            )
            .order_by(Repository.full_name.asc())
        )
    ).all()
    items: list[dict[str, object]] = []
    for repository, connection in rows:
        info = _blacklist_info(repository)
        if info is None:
            continue
        items.append(
            {
                "repository_id": str(repository.id),
                "github_id": repository.github_id,
                "full_name": repository.full_name,
                "connection_id": str(connection.id),
                "connection_name": connection.name,
                "blacklisted_at": info.get("at"),
                "reason": info.get("reason"),
            }
        )
    return items


@router.post("/{repository_id}/blacklist")
async def blacklist_repository(
    repository_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> dict[str, object]:
    repository, _connection = await _owned_repository(db, repository_id, current_user.id)
    now = datetime.now(UTC)
    extra = dict(repository.extra_data or {})
    extra["blacklist"] = {
        "at": now.isoformat(),
        "reason": "Ocultado permanentemente do monitor pelo usuário.",
        "github_id": repository.github_id,
        "full_name": repository.full_name,
    }
    repository.extra_data = extra
    repository.monitoring_enabled = False
    repository.sync_error = None
    await db.commit()
    await publish_event(
        current_user.id,
        "repository.blacklisted",
        {"full_name": repository.full_name, "github_id": repository.github_id},
        repository_id=repository.id,
    )
    return {
        "message": (
            f"{repository.full_name} entrou na lista negra. Ele não será monitorado "
            "nem reativado automaticamente nas próximas sincronizações."
        ),
        "repository_id": str(repository.id),
        "blacklisted": True,
    }


@router.delete("/{repository_id}/blacklist")
async def restore_from_blacklist(
    repository_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> dict[str, object]:
    repository, _connection = await _owned_repository(db, repository_id, current_user.id)
    extra = dict(repository.extra_data or {})
    extra.pop("blacklist", None)
    repository.extra_data = extra
    repository.monitoring_enabled = True
    await db.commit()
    await publish_event(
        current_user.id,
        "repository.blacklist_removed",
        {"full_name": repository.full_name, "github_id": repository.github_id},
        repository_id=repository.id,
    )
    return {
        "message": f"{repository.full_name} saiu da lista negra e voltou ao monitoramento.",
        "repository_id": str(repository.id),
        "blacklisted": False,
    }


async def _github_client(connection: GitHubConnection) -> GitHubClient:
    if not connection.token_encrypted:
        raise HTTPException(status_code=400, detail="Conexão GitHub sem token operacional.")
    token = EncryptionService().decrypt(connection.token_encrypted)
    return GitHubClient(token, api_url=connection.api_url)


def _github_error(exc: GitHubAPIError) -> HTTPException:
    status_code = exc.status_code if exc.status_code in {400, 401, 403, 404, 409, 422, 451} else 502
    detail = {
        401: "A credencial GitHub não é válida para esta operação.",
        403: "O token precisa de permissão Administration no repositório para alterar GitHub Actions.",
        404: "O GitHub não encontrou o repositório ou o recurso de Actions.",
        451: "O recurso está indisponível no GitHub por restrição legal.",
    }.get(status_code, "O GitHub recusou a alteração de GitHub Actions.")
    return HTTPException(status_code=status_code, detail=detail)


@router.get("/{repository_id}/actions")
async def get_actions_state(
    repository_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> dict[str, object]:
    repository, connection = await _owned_repository(db, repository_id, current_user.id)
    client = await _github_client(connection)
    try:
        payload = await client.get_json(f"/repos/{repository.full_name}/actions/permissions")
    except GitHubAPIError as exc:
        raise _github_error(exc) from exc
    finally:
        await client.close()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="Resposta inválida do GitHub para Actions.")
    return {
        "repository_id": str(repository.id),
        "full_name": repository.full_name,
        "enabled": bool(payload.get("enabled", False)),
        "allowed_actions": payload.get("allowed_actions"),
        "sha_pinning_required": payload.get("sha_pinning_required"),
    }


@router.put("/{repository_id}/actions")
async def update_actions_state(
    repository_id: uuid.UUID,
    payload: ActionsUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> dict[str, object]:
    repository, connection = await _owned_repository(db, repository_id, current_user.id)
    client = await _github_client(connection)
    cancelled: list[int] = []
    cancel_errors: list[dict[str, object]] = []
    try:
        if not payload.enabled and payload.cancel_in_progress:
            try:
                runs = await client.list_workflow_runs(repository.full_name, limit=100)
                for run in runs:
                    status = str(run.get("status") or "").lower()
                    if status not in {"queued", "in_progress", "waiting", "pending", "requested"}:
                        continue
                    run_id = int(run["id"])
                    try:
                        await client.cancel_workflow(repository.full_name, run_id)
                        cancelled.append(run_id)
                    except GitHubAPIError as cancel_exc:
                        cancel_errors.append(
                            {
                                "run_id": run_id,
                                "status_code": cancel_exc.status_code,
                            }
                        )

            except GitHubAPIError:
                # Falha ao enumerar runs não impede a alteração da política global.
                pass

        await client.request(
            "PUT",
            f"/repos/{repository.full_name}/actions/permissions",
            json={"enabled": payload.enabled},
        )
    except GitHubAPIError as exc:
        raise _github_error(exc) from exc
    finally:
        await client.close()

    extra = dict(repository.extra_data or {})
    extra["actions_control"] = {
        "enabled": payload.enabled,
        "changed_at": datetime.now(UTC).isoformat(),
        "cancelled_runs": cancelled,
    }
    repository.extra_data = extra
    await db.commit()
    await publish_event(
        current_user.id,
        "repository.actions_changed",
        {
            "full_name": repository.full_name,
            "enabled": payload.enabled,
            "cancelled_runs": cancelled,
            "cancel_errors": cancel_errors,
        },
        repository_id=repository.id,
    )
    return {
        "repository_id": str(repository.id),
        "full_name": repository.full_name,
        "enabled": payload.enabled,
        "cancelled_runs": cancelled,
        "cancel_errors": cancel_errors,
        "message": (
            "GitHub Actions foi ativado para o repositório."
            if payload.enabled
            else "GitHub Actions foi desativado para o repositório."
        ),
    }
