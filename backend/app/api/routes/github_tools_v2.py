from __future__ import annotations

import base64
import logging
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.encryption import EncryptionService
from app.models.github import GitHubConnection, Repository
from app.schemas.platform import (
    BootstrapPreviewRequest,
    BranchProtectionRequest,
    RepositoryCreateOnlineRequest,
)
from app.services.audit import record_audit
from app.services.ghcr_service import GhcrError, GhcrService
from app.services.github_client import GitHubAPIError, GitHubClient
from app.services.repository_manager import RepositoryManagerError, RepositoryManagerService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/github-tools-v2", tags=["GitHub Tools v2"])


def _ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    return (
        forwarded.split(",", 1)[0].strip()
        if forwarded
        else request.client.host if request.client else ""
    )[:64] or None


def _allowed(user: CurrentUser, permission: str) -> None:
    permissions = (user.preferences or {}).get("permissions") or []
    if not user.is_superuser and permission not in permissions and "operations.*" not in permissions:
        raise HTTPException(status_code=403, detail=f"Permissão necessária: {permission}")


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, RepositoryManagerError | GhcrError):
        return HTTPException(status_code=400, detail=str(exc)[:1000])
    if isinstance(exc, GitHubAPIError):
        status_code = exc.status_code if exc.status_code in {400, 401, 403, 404, 409, 422, 429, 451} else 502
        messages = {
            400: "O GitHub recusou os parâmetros enviados.",
            401: "A conexão GitHub não está autenticada para esta operação.",
            403: "O token GitHub não possui permissão suficiente para esta operação.",
            404: "O recurso solicitado não existe ou não está acessível pela conexão selecionada.",
            409: "O GitHub recusou a operação por conflito de estado.",
            422: "O GitHub recusou a operação por validação.",
            429: "O limite de requisições do GitHub foi atingido. Tente novamente mais tarde.",
            451: "O recurso está indisponível por restrição legal no GitHub.",
            502: "O GitHub não respondeu de forma utilizável à operação.",
        }
        return HTTPException(status_code=status_code, detail=messages[status_code])
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail="Os parâmetros informados são inválidos.")
    logger.exception("Falha não tratada no GitHub Tools v2")
    return HTTPException(
        status_code=500,
        detail="Falha interna ao executar a operação. Consulte a Central de Logs pelo correlation ID.",
    )


async def _connection(
    db: DbSession,
    connection_id: uuid.UUID,
    user_id: uuid.UUID,
) -> GitHubConnection:
    item = await db.get(GitHubConnection, connection_id)
    if not item or item.user_id != user_id or not item.token_encrypted:
        raise HTTPException(status_code=404, detail="Conexão GitHub operacional não encontrada.")
    return item


async def _repo_client(
    db: DbSession,
    repository_id: uuid.UUID,
    user_id: uuid.UUID,
) -> tuple[Repository, GitHubConnection, GitHubClient]:
    repository = await db.get(Repository, repository_id)
    if not repository:
        raise HTTPException(status_code=404, detail="Repositório não encontrado.")
    connection = await _connection(db, repository.connection_id, user_id)
    token = EncryptionService().decrypt(connection.token_encrypted or "")
    return repository, connection, GitHubClient(token, api_url=connection.api_url)


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


async def _upsert_local_repository(
    db: DbSession,
    connection: GitHubConnection,
    payload: dict[str, Any],
) -> Repository:
    github_id = int(payload["id"])
    found = (
        await db.execute(
            select(Repository).where(
                Repository.connection_id == connection.id,
                Repository.github_id == github_id,
            )
        )
    ).scalar_one_or_none()
    owner = str(((payload.get("owner") or {}).get("login") or ""))
    values = {
        "owner": owner,
        "name": str(payload.get("name") or ""),
        "full_name": str(payload.get("full_name") or f"{owner}/{payload.get('name')}"),
        "html_url": str(payload.get("html_url") or ""),
        "description": payload.get("description"),
        "private": bool(payload.get("private")),
        "fork": bool(payload.get("fork")),
        "archived": bool(payload.get("archived")),
        "disabled": bool(payload.get("disabled")),
        "visibility": str(
            payload.get("visibility") or ("private" if payload.get("private") else "public")
        ),
        "default_branch": str(payload.get("default_branch") or "main"),
        "language": payload.get("language"),
        "stargazers_count": int(payload.get("stargazers_count") or 0),
        "forks_count": int(payload.get("forks_count") or 0),
        "open_issue_count": int(payload.get("open_issues_count") or 0),
        "github_created_at": _parse_date(payload.get("created_at")),
        "github_updated_at": _parse_date(payload.get("updated_at")),
        "pushed_at": _parse_date(payload.get("pushed_at")),
        "monitoring_enabled": True,
    }
    if found:
        for key, value in values.items():
            setattr(found, key, value)
        return found
    repository = Repository(
        connection_id=connection.id,
        github_id=github_id,
        branch_count=0,
        open_pr_count=0,
        health_score=0,
        health_status="unknown",
        extra_data={},
        **values,
    )
    db.add(repository)
    await db.flush()
    return repository


@router.post("/repositories/online")
async def create_repository_online(
    payload: RepositoryCreateOnlineRequest,
    current_user: CurrentUser,
    db: DbSession,
    request: Request,
) -> dict[str, Any]:
    _allowed(current_user, "repository.create")
    connection = await _connection(db, payload.connection_id, current_user.id)
    client = GitHubClient(
        EncryptionService().decrypt(connection.token_encrypted or ""),
        api_url=connection.api_url,
    )
    try:
        service = RepositoryManagerService(client)
        created = await service.create_repository(
            owner=payload.owner,
            name=payload.name,
            description=payload.description,
            private=payload.private,
            default_branch=payload.default_branch,
        )
        repository = await _upsert_local_repository(db, connection, created)
        preview = None
        if payload.template != "empty":
            preview = await service.bootstrap_preview(
                repository.full_name,
                branch=payload.default_branch,
                template=payload.template,
                options=payload.options,
            )
        await record_audit(
            db,
            action="repository.created_online",
            user_id=current_user.id,
            entity_type="repository",
            entity_id=str(repository.id),
            details={
                "full_name": repository.full_name,
                "private": repository.private,
                "default_branch": repository.default_branch,
                "template": payload.template,
            },
            ip_address=_ip(request),
        )
        await db.commit()
        return {
            "repository_id": str(repository.id),
            "full_name": repository.full_name,
            "html_url": repository.html_url,
            "default_branch": repository.default_branch,
            "bootstrap_preview": preview,
        }
    except (GitHubAPIError, RepositoryManagerError, ValueError) as exc:
        raise _error(exc) from exc
    finally:
        await client.close()


@router.patch("/repositories/{repository_id}/visibility")
async def change_visibility(
    repository_id: uuid.UUID,
    payload: dict[str, Any],
    current_user: CurrentUser,
    db: DbSession,
    request: Request,
) -> dict[str, Any]:
    _allowed(current_user, "repository.visibility")
    repository, _, client = await _repo_client(db, repository_id, current_user.id)
    private = payload.get("private")
    if not isinstance(private, bool):
        raise HTTPException(status_code=422, detail="private deve ser booleano.")
    expected = f"VISIBILIDADE {repository.full_name} {'private' if private else 'public'}"
    if payload.get("confirmation") != expected:
        raise HTTPException(status_code=400, detail=f"Digite exatamente: {expected}")
    try:
        result = await client.update_repository(repository.full_name, private=private)
        repository.private = bool(result.get("private"))
        repository.visibility = str(
            result.get("visibility") or ("private" if private else "public")
        )
        await record_audit(
            db,
            action="repository.visibility_changed",
            user_id=current_user.id,
            entity_type="repository",
            entity_id=str(repository.id),
            details={"full_name": repository.full_name, "private": private},
            ip_address=_ip(request),
        )
        await db.commit()
        return {
            "full_name": repository.full_name,
            "private": repository.private,
            "visibility": repository.visibility,
        }
    except Exception as exc:
        raise _error(exc) from exc
    finally:
        await client.close()


@router.post("/bootstrap/preview")
async def bootstrap_preview(
    payload: BootstrapPreviewRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> dict[str, Any]:
    repository, _, client = await _repo_client(db, payload.repository_id, current_user.id)
    try:
        return await RepositoryManagerService(client).bootstrap_preview(
            repository.full_name,
            branch=payload.branch,
            template=payload.template,
            options=payload.options,
        )
    except Exception as exc:
        raise _error(exc) from exc
    finally:
        await client.close()


@router.post("/repositories/{repository_id}/bootstrap/apply")
async def bootstrap_apply(
    repository_id: uuid.UUID,
    payload: dict[str, Any],
    current_user: CurrentUser,
    db: DbSession,
    request: Request,
) -> dict[str, Any]:
    _allowed(current_user, "repository.write")
    repository, _, client = await _repo_client(db, repository_id, current_user.id)
    branch = str(payload.get("branch") or repository.default_branch)
    files = list(payload.get("files") or [])
    try:
        result = await RepositoryManagerService(client).apply_bootstrap(
            repository.full_name,
            branch=branch,
            files=files,
        )
        await record_audit(
            db,
            action="repository.bootstrap_applied",
            user_id=current_user.id,
            entity_type="repository",
            entity_id=str(repository.id),
            details={
                "branch": branch,
                "changed": result["changed"],
                "paths": [str(x.get("path")) for x in files if x.get("action") != "keep"],
            },
            ip_address=_ip(request),
        )
        await db.commit()
        return result
    except Exception as exc:
        raise _error(exc) from exc
    finally:
        await client.close()


@router.get("/repositories/{repository_id}/branches")
async def branches(
    repository_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> list[dict[str, Any]]:
    repository, _, client = await _repo_client(db, repository_id, current_user.id)
    try:
        items = await client.list_branches(repository.full_name, limit=300)
        return [
            {
                "name": item.get("name"),
                "sha": ((item.get("commit") or {}).get("sha")),
                "protected": bool(item.get("protected")),
                "default": str(item.get("name")) == repository.default_branch,
            }
            for item in items
        ]
    finally:
        await client.close()


@router.get("/repositories/{repository_id}/branches/{branch}/protection")
async def branch_protection(
    repository_id: uuid.UUID,
    branch: str,
    current_user: CurrentUser,
    db: DbSession,
) -> dict[str, Any]:
    repository, _, client = await _repo_client(db, repository_id, current_user.id)
    try:
        return {
            "branch": branch,
            "protection": await RepositoryManagerService(client).get_branch_protection(
                repository.full_name,
                branch,
            ),
        }
    except Exception as exc:
        raise _error(exc) from exc
    finally:
        await client.close()


@router.put("/repositories/{repository_id}/branch-protection")
async def set_branch_protection(
    repository_id: uuid.UUID,
    payload: BranchProtectionRequest,
    current_user: CurrentUser,
    db: DbSession,
    request: Request,
) -> dict[str, Any]:
    _allowed(current_user, "repository.protection")
    repository, _, client = await _repo_client(db, repository_id, current_user.id)
    try:
        result = await RepositoryManagerService(client).set_branch_protection(
            repository.full_name,
            **payload.model_dump(),
        )
        await record_audit(
            db,
            action="repository.branch_protection_updated",
            user_id=current_user.id,
            entity_type="repository",
            entity_id=str(repository.id),
            details=payload.model_dump(),
            ip_address=_ip(request),
        )
        await db.commit()
        return {"branch": payload.branch, "protection": result}
    except Exception as exc:
        raise _error(exc) from exc
    finally:
        await client.close()


@router.get("/repositories/{repository_id}/compare")
async def compare(
    repository_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    base: str = Query(...),
    head: str = Query(...),
) -> dict[str, Any]:
    repository, _, client = await _repo_client(db, repository_id, current_user.id)
    try:
        payload = await client.get_json(
            f"/repos/{repository.full_name}/compare/{quote(base, safe='')}...{quote(head, safe='')}"
        )
        return payload if isinstance(payload, dict) else {}
    finally:
        await client.close()


@router.delete("/repositories/{repository_id}/branches/{branch}")
async def delete_branch(
    repository_id: uuid.UUID,
    branch: str,
    current_user: CurrentUser,
    db: DbSession,
    request: Request,
    confirmation: str = Query(...),
) -> dict[str, Any]:
    _allowed(current_user, "repository.delete_branch")
    repository, _, client = await _repo_client(db, repository_id, current_user.id)
    expected = f"EXCLUIR BRANCH {repository.full_name}:{branch}"
    if confirmation != expected:
        await client.close()
        raise HTTPException(status_code=400, detail=f"Digite exatamente: {expected}")
    if branch == repository.default_branch:
        await client.close()
        raise HTTPException(
            status_code=409,
            detail="A default branch não pode ser excluída por esta operação.",
        )
    try:
        await client.request(
            "DELETE",
            f"/repos/{repository.full_name}/git/refs/heads/{quote(branch, safe='')}",
        )
        await record_audit(
            db,
            action="repository.branch_deleted",
            user_id=current_user.id,
            entity_type="repository",
            entity_id=str(repository.id),
            details={"branch": branch},
            ip_address=_ip(request),
        )
        await db.commit()
        return {"deleted": True, "branch": branch}
    except Exception as exc:
        raise _error(exc) from exc
    finally:
        await client.close()


@router.get("/repositories/{repository_id}/files/content")
async def read_file(
    repository_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    path: str = Query(...),
    branch: str | None = None,
) -> dict[str, Any]:
    repository, _, client = await _repo_client(db, repository_id, current_user.id)
    ref = branch or repository.default_branch
    encoded = "/".join(quote(part, safe="") for part in path.strip("/").split("/"))
    try:
        payload = await client.get_json(
            f"/repos/{repository.full_name}/contents/{encoded}",
            params={"ref": ref},
        )
        if not isinstance(payload, dict) or payload.get("type") != "file":
            raise HTTPException(status_code=400, detail="O caminho informado não é um arquivo.")
        content = str(payload.get("content") or "")
        decoded = (
            base64.b64decode(content.replace("\n", "")).decode("utf-8", "replace")
            if content
            else ""
        )
        return {
            "path": payload.get("path"),
            "sha": payload.get("sha"),
            "size": payload.get("size"),
            "branch": ref,
            "content": decoded,
        }
    finally:
        await client.close()


@router.get("/repositories/{repository_id}/actions")
async def actions_data(
    repository_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> dict[str, Any]:
    repository, _, client = await _repo_client(db, repository_id, current_user.id)
    try:
        workflows = await client.list_workflows(repository.full_name, limit=100)
        runs = await client.list_workflow_runs(repository.full_name, limit=100)
        artifacts = await client.optional_paginate(
            "actions_artifacts",
            f"/repos/{repository.full_name}/actions/artifacts",
            limit=200,
            empty_statuses={403, 404},
        )
        caches: list[dict[str, Any]] = []
        try:
            cache_payload = await client.get_json(
                f"/repos/{repository.full_name}/actions/caches",
                params={"per_page": 100},
            )
            caches = list(cache_payload.get("actions_caches") or []) if isinstance(cache_payload, dict) else []
        except GitHubAPIError as exc:
            if exc.status_code not in {403, 404}:
                raise
        return {
            "workflows": workflows,
            "runs": runs,
            "artifacts": artifacts,
            "caches": caches,
        }
    finally:
        await client.close()


@router.get("/connections/{connection_id}/ghcr/packages")
async def ghcr_packages(
    connection_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    owner: str | None = None,
) -> list[dict[str, Any]]:
    connection = await _connection(db, connection_id, current_user.id)
    client = GitHubClient(
        EncryptionService().decrypt(connection.token_encrypted or ""),
        api_url=connection.api_url,
    )
    try:
        return await GhcrService(client, connection.github_login).list_packages(
            owner or connection.github_login,
            limit=300,
        )
    except Exception as exc:
        raise _error(exc) from exc
    finally:
        await client.close()


@router.get("/connections/{connection_id}/ghcr/packages/{package_name}")
async def ghcr_package(
    connection_id: uuid.UUID,
    package_name: str,
    current_user: CurrentUser,
    db: DbSession,
    owner: str | None = None,
) -> dict[str, Any]:
    connection = await _connection(db, connection_id, current_user.id)
    client = GitHubClient(
        EncryptionService().decrypt(connection.token_encrypted or ""),
        api_url=connection.api_url,
    )
    try:
        return await GhcrService(client, connection.github_login).package_detail(
            owner or connection.github_login,
            package_name,
        )
    except Exception as exc:
        raise _error(exc) from exc
    finally:
        await client.close()


@router.post("/connections/{connection_id}/ghcr/packages/{package_name}/delete-by-tag")
async def ghcr_delete_by_tag(
    connection_id: uuid.UUID,
    package_name: str,
    payload: dict[str, str],
    current_user: CurrentUser,
    db: DbSession,
    request: Request,
    owner: str | None = None,
) -> dict[str, Any]:
    _allowed(current_user, "ghcr.delete")
    connection = await _connection(db, connection_id, current_user.id)
    package_owner = owner or connection.github_login
    tag = str(payload.get("tag") or "")
    expected = f"EXCLUIR {package_owner}/{package_name}:{tag}"
    if payload.get("confirmation") != expected:
        raise HTTPException(status_code=400, detail=f"Digite exatamente: {expected}")
    client = GitHubClient(
        EncryptionService().decrypt(connection.token_encrypted or ""),
        api_url=connection.api_url,
    )
    try:
        result = await GhcrService(client, connection.github_login).delete_version_by_tag(
            package_owner,
            package_name,
            tag,
        )
        await record_audit(
            db,
            action="ghcr.version_deleted_by_tag",
            user_id=current_user.id,
            entity_type="ghcr_package",
            entity_id=f"{package_owner}/{package_name}",
            details=result,
            ip_address=_ip(request),
        )
        await db.commit()
        return result
    except Exception as exc:
        raise _error(exc) from exc
    finally:
        await client.close()


@router.post("/connections/{connection_id}/ghcr/packages/{package_name}/delete-all")
async def ghcr_delete_all(
    connection_id: uuid.UUID,
    package_name: str,
    payload: dict[str, Any],
    current_user: CurrentUser,
    db: DbSession,
    request: Request,
    owner: str | None = None,
) -> dict[str, Any]:
    _allowed(current_user, "ghcr.delete")
    connection = await _connection(db, connection_id, current_user.id)
    package_owner = owner or connection.github_login
    expected = f"EXCLUIR TODAS AS VERSOES {package_owner}/{package_name}"
    if payload.get("confirmation") != expected:
        raise HTTPException(status_code=400, detail=f"Digite exatamente: {expected}")
    client = GitHubClient(
        EncryptionService().decrypt(connection.token_encrypted or ""),
        api_url=connection.api_url,
    )
    try:
        result = await GhcrService(client, connection.github_login).delete_all_versions(
            package_owner,
            package_name,
            preserve_tags=set(str(x) for x in payload.get("preserve_tags") or []),
        )
        await record_audit(
            db,
            action="ghcr.versions_bulk_deleted",
            user_id=current_user.id,
            entity_type="ghcr_package",
            entity_id=f"{package_owner}/{package_name}",
            details={
                "deleted": result["deleted"],
                "preserved": result["preserved"],
                "failed": result["failed"],
            },
            ip_address=_ip(request),
        )
        await db.commit()
        return result
    except Exception as exc:
        raise _error(exc) from exc
    finally:
        await client.close()


@router.delete("/connections/{connection_id}/ghcr/packages/{package_name}")
async def ghcr_delete_package(
    connection_id: uuid.UUID,
    package_name: str,
    current_user: CurrentUser,
    db: DbSession,
    request: Request,
    owner: str | None = None,
    confirmation: str = Query(...),
) -> dict[str, Any]:
    _allowed(current_user, "ghcr.delete_package")
    connection = await _connection(db, connection_id, current_user.id)
    package_owner = owner or connection.github_login
    expected = f"{package_owner}/{package_name}"
    if confirmation != expected:
        raise HTTPException(status_code=400, detail=f"Digite exatamente: {expected}")
    client = GitHubClient(
        EncryptionService().decrypt(connection.token_encrypted or ""),
        api_url=connection.api_url,
    )
    try:
        service = GhcrService(client, connection.github_login)
        detail = await service.package_detail(package_owner, package_name)
        await service.delete_package(package_owner, package_name)
        await record_audit(
            db,
            action="ghcr.package_deleted",
            user_id=current_user.id,
            entity_type="ghcr_package",
            entity_id=expected,
            details={
                "version_count": detail.get("version_count"),
                "tag_count": detail.get("tag_count"),
            },
            ip_address=_ip(request),
        )
        await db.commit()
        return {"deleted": True, "package": expected}
    except Exception as exc:
        raise _error(exc) from exc
    finally:
        await client.close()
