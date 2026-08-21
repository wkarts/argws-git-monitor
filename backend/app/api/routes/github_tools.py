from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.encryption import EncryptionService
from app.models.github import GitHubConnection
from app.schemas.github_tools import (
    BootstrapRequest,
    BranchCreateRequest,
    BranchResult,
    DeletePathRequest,
    FileWriteRequest,
    PackageDeleteRequest,
    PackageVersion,
    ReleaseCreateRequest,
    ToolResult,
    TreeItem,
    WorkflowDispatchRequest,
)
from app.services.github_client import GitHubAPIError, GitHubClient
from app.services.github_management import GitHubManagementService
from app.services.github_sync import get_repository_client

router = APIRouter(prefix="/github-tools", tags=["GitHub Tools"])


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, GitHubAPIError):
        code = exc.status_code or 400
        if code not in {400, 401, 403, 404, 409, 422, 429}:
            code = 400
        return HTTPException(status_code=code, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


async def _owned_connection(
    db: DbSession, connection_id: uuid.UUID, user_id: uuid.UUID
) -> GitHubConnection:
    result = await db.execute(
        select(GitHubConnection).where(
            GitHubConnection.id == connection_id,
            GitHubConnection.user_id == user_id,
        )
    )
    connection = result.scalar_one_or_none()
    if not connection:
        raise HTTPException(status_code=404, detail="Conexão GitHub não encontrada.")
    return connection


@router.get("/repositories/{repository_id}/branches")
async def list_branches(
    repository_id: uuid.UUID, current_user: CurrentUser
) -> list[dict[str, object]]:
    repository, client = await get_repository_client(repository_id, user_id=current_user.id)
    try:
        return await GitHubManagementService(client).list_branches(repository.full_name)
    except Exception as exc:
        raise _http_error(exc) from exc
    finally:
        await client.close()


@router.post("/repositories/{repository_id}/branches", response_model=BranchResult)
async def create_branch(
    repository_id: uuid.UUID,
    payload: BranchCreateRequest,
    current_user: CurrentUser,
) -> BranchResult:
    repository, client = await get_repository_client(repository_id, user_id=current_user.id)
    try:
        result = await GitHubManagementService(client).ensure_branch(
            repository.full_name,
            payload.branch,
            base_branch=payload.base_branch,
            set_default=payload.set_default,
        )
        return BranchResult(
            branch=str(result["branch"]),
            created=bool(result["created"]),
            set_default=bool(result["set_default"]),
        )
    except Exception as exc:
        raise _http_error(exc) from exc
    finally:
        await client.close()


@router.get("/repositories/{repository_id}/tree", response_model=list[TreeItem])
async def repository_tree(
    repository_id: uuid.UUID,
    current_user: CurrentUser,
    branch: str = Query(default="main", min_length=1, max_length=255),
    prefix: str | None = Query(default=None, max_length=1000),
) -> list[TreeItem]:
    repository, client = await get_repository_client(repository_id, user_id=current_user.id)
    try:
        items = await GitHubManagementService(client).list_tree(
            repository.full_name, branch=branch, prefix=prefix
        )
        return [TreeItem.model_validate(item) for item in items]
    except Exception as exc:
        raise _http_error(exc) from exc
    finally:
        await client.close()


@router.put("/repositories/{repository_id}/files", response_model=ToolResult)
async def write_file(
    repository_id: uuid.UUID,
    payload: FileWriteRequest,
    current_user: CurrentUser,
) -> ToolResult:
    repository, client = await get_repository_client(repository_id, user_id=current_user.id)
    try:
        result = await GitHubManagementService(client).put_file(
            repository.full_name,
            path=payload.path,
            content=payload.content,
            branch=payload.branch,
            message=payload.message,
            overwrite=payload.overwrite,
        )
        return ToolResult(message="Arquivo processado no GitHub.", data=result)
    except Exception as exc:
        raise _http_error(exc) from exc
    finally:
        await client.close()


@router.post("/repositories/{repository_id}/delete-path", response_model=ToolResult)
async def delete_path(
    repository_id: uuid.UUID,
    payload: DeletePathRequest,
    current_user: CurrentUser,
) -> ToolResult:
    repository, client = await get_repository_client(repository_id, user_id=current_user.id)
    expected = f"{repository.full_name}:{payload.path.strip('/')}"
    if payload.confirmation != expected:
        await client.close()
        raise HTTPException(
            status_code=400,
            detail=f"Confirmação inválida. Digite exatamente {expected}.",
        )
    try:
        result = await GitHubManagementService(client).delete_path(
            repository.full_name,
            path=payload.path,
            branch=payload.branch,
            message=f"chore: remove {payload.path} pelo ARGWS Git Monitor",
        )
        return ToolResult(message=f"{result['deleted']} arquivo(s) removido(s).", data=result)
    except Exception as exc:
        raise _http_error(exc) from exc
    finally:
        await client.close()


@router.post("/repositories/{repository_id}/bootstrap", response_model=ToolResult)
async def bootstrap_repository(
    repository_id: uuid.UUID,
    payload: BootstrapRequest,
    current_user: CurrentUser,
) -> ToolResult:
    repository, client = await get_repository_client(repository_id, user_id=current_user.id)
    try:
        service = GitHubManagementService(client)
        await service.ensure_branch(repository.full_name, payload.branch)
        result = await service.bootstrap_repository(
            repository.full_name,
            branch=payload.branch,
            overwrite=payload.overwrite,
            include_dockerfile=payload.include_dockerfile,
            include_workflow=payload.include_workflow,
        )
        return ToolResult(
            message=f"Bootstrap concluído: {result['changed']} arquivo(s) alterado(s).",
            data=result,
        )
    except Exception as exc:
        raise _http_error(exc) from exc
    finally:
        await client.close()


@router.post("/repositories/{repository_id}/releases", response_model=ToolResult)
async def create_release(
    repository_id: uuid.UUID,
    payload: ReleaseCreateRequest,
    current_user: CurrentUser,
) -> ToolResult:
    repository, client = await get_repository_client(repository_id, user_id=current_user.id)
    try:
        release = await GitHubManagementService(client).create_release(
            repository.full_name,
            tag_name=payload.tag_name,
            target_commitish=payload.target_commitish,
            name=payload.name,
            body=payload.body,
            prerelease=payload.prerelease,
        )
        return ToolResult(
            message=f"Release {payload.tag_name} criada.",
            data={
                "id": release.get("id"),
                "tag_name": release.get("tag_name"),
                "html_url": release.get("html_url"),
            },
        )
    except Exception as exc:
        raise _http_error(exc) from exc
    finally:
        await client.close()


@router.post("/repositories/{repository_id}/dispatch", response_model=ToolResult)
async def dispatch_workflow(
    repository_id: uuid.UUID,
    payload: WorkflowDispatchRequest,
    current_user: CurrentUser,
) -> ToolResult:
    repository, client = await get_repository_client(repository_id, user_id=current_user.id)
    try:
        await GitHubManagementService(client).dispatch_workflow(
            repository.full_name,
            workflow=payload.workflow,
            ref=payload.ref,
            inputs=payload.inputs,
        )
        return ToolResult(
            message=f"Workflow {payload.workflow} despachado em {payload.ref}."
        )
    except Exception as exc:
        raise _http_error(exc) from exc
    finally:
        await client.close()


@router.get(
    "/connections/{connection_id}/packages/{package_name}/versions",
    response_model=list[PackageVersion],
)
async def package_versions(
    connection_id: uuid.UUID,
    package_name: str,
    current_user: CurrentUser,
    db: DbSession,
    owner: str | None = Query(default=None, max_length=255),
) -> list[PackageVersion]:
    connection = await _owned_connection(db, connection_id, current_user.id)
    if not connection.token_encrypted:
        raise HTTPException(status_code=400, detail="Conexão sem token operacional.")
    token = EncryptionService().decrypt(connection.token_encrypted)
    client = GitHubClient(token, api_url=connection.api_url)
    try:
        items = await GitHubManagementService(client).package_versions(
            owner=owner or connection.github_login,
            package_name=package_name,
            authenticated_login=connection.github_login,
        )
        return [PackageVersion.model_validate(item) for item in items]
    except Exception as exc:
        raise _http_error(exc) from exc
    finally:
        await client.close()


@router.post(
    "/connections/{connection_id}/packages/{package_name}/versions/{version_id}/delete",
    response_model=ToolResult,
)
async def delete_package_version(
    connection_id: uuid.UUID,
    package_name: str,
    version_id: int,
    payload: PackageDeleteRequest,
    current_user: CurrentUser,
    db: DbSession,
    owner: str | None = Query(default=None, max_length=255),
) -> ToolResult:
    connection = await _owned_connection(db, connection_id, current_user.id)
    package_owner = owner or connection.github_login
    expected = f"{package_owner}/{package_name}:{version_id}"
    if payload.confirmation != expected:
        raise HTTPException(status_code=400, detail=f"Digite exatamente {expected}.")
    token = EncryptionService().decrypt(connection.token_encrypted or "")
    client = GitHubClient(token, api_url=connection.api_url)
    try:
        await GitHubManagementService(client).delete_package_version(
            owner=package_owner,
            package_name=package_name,
            version_id=version_id,
            authenticated_login=connection.github_login,
        )
        return ToolResult(message=f"Versão GHCR {version_id} removida.")
    except Exception as exc:
        raise _http_error(exc) from exc
    finally:
        await client.close()


@router.post(
    "/connections/{connection_id}/packages/{package_name}/delete",
    response_model=ToolResult,
)
async def delete_package(
    connection_id: uuid.UUID,
    package_name: str,
    payload: PackageDeleteRequest,
    current_user: CurrentUser,
    db: DbSession,
    owner: str | None = Query(default=None, max_length=255),
) -> ToolResult:
    connection = await _owned_connection(db, connection_id, current_user.id)
    package_owner = owner or connection.github_login
    expected = f"{package_owner}/{package_name}"
    if payload.confirmation != expected:
        raise HTTPException(status_code=400, detail=f"Digite exatamente {expected}.")
    token = EncryptionService().decrypt(connection.token_encrypted or "")
    client = GitHubClient(token, api_url=connection.api_url)
    try:
        await GitHubManagementService(client).delete_package(
            owner=package_owner,
            package_name=package_name,
            authenticated_login=connection.github_login,
        )
        return ToolResult(message=f"Pacote GHCR {expected} removido.")
    except Exception as exc:
        raise _http_error(exc) from exc
    finally:
        await client.close()
