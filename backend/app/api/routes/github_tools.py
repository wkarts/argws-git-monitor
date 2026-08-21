from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.encryption import EncryptionService
from app.models.github import GitHubConnection, Repository
from app.schemas.github_tools import (
    BootstrapRequest,
    BranchCreateRequest,
    BranchResult,
    DeletePathRequest,
    FileWriteRequest,
    PackageDeleteRequest,
    PackageVersion,
    ReleaseCreateRequest,
    RepositoryComplianceDeleteRequest,
    RepositoryComplianceProbeRequest,
    ToolResult,
    TreeItem,
    WorkflowDispatchRequest,
)
from app.services.audit import record_audit
from app.services.github_client import GitHubAPIError, GitHubClient
from app.services.github_management import GitHubManagementService
from app.services.github_sync import get_repository_client
from app.services.repository_compliance import (
    deletion_confirmation,
    normalize_full_name,
    probe_repository,
    validate_personal_owner,
)

router = APIRouter(prefix="/github-tools", tags=["GitHub Tools"])


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, GitHubAPIError):
        code = exc.status_code or 400
        if code not in {400, 401, 403, 404, 409, 422, 429, 451}:
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


def _compliance_delete_error(exc: GitHubAPIError) -> HTTPException:
    if exc.status_code == 451:
        return HTTPException(
            status_code=451,
            detail=(
                "O GitHub bloqueou também a operação de exclusão por restrição legal/DMCA. "
                "O Git Monitor não contorna essa restrição; nesse caso a remoção da conta "
                "precisa ser solicitada ao suporte do GitHub."
            ),
        )
    if exc.status_code == 403:
        return HTTPException(
            status_code=403,
            detail=(
                "O token não possui permissão para excluir este repositório ou o GitHub "
                "bloqueou a administração dele. Use um token com Administration: write "
                "ou delete_repo, conforme o tipo do token."
            ),
        )
    if exc.status_code == 404:
        return HTTPException(
            status_code=404,
            detail=(
                "O GitHub não encontrou o repositório para exclusão. Ele pode já ter sido "
                "removido ou estar totalmente oculto pela restrição."
            ),
        )
    return _http_error(exc)


@router.post(
    "/connections/{connection_id}/compliance/probe",
    response_model=ToolResult,
)
async def probe_compliance_repository(
    connection_id: uuid.UUID,
    payload: RepositoryComplianceProbeRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> ToolResult:
    connection = await _owned_connection(db, connection_id, current_user.id)
    if not connection.token_encrypted:
        raise HTTPException(status_code=400, detail="Conexão sem token operacional.")
    try:
        full_name = normalize_full_name(payload.full_name)
        validate_personal_owner(full_name, connection.github_login)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    token = EncryptionService().decrypt(connection.token_encrypted)
    client = GitHubClient(token, api_url=connection.api_url)
    try:
        status = await probe_repository(
            client,
            full_name=full_name,
            authenticated_login=connection.github_login,
        )
        local_result = await db.execute(
            select(Repository).where(
                Repository.connection_id == connection.id,
                Repository.full_name == full_name,
            )
        )
        local_repository = local_result.scalar_one_or_none()
        repository = status.repository or {}
        return ToolResult(
            message=status.message,
            data={
                "full_name": status.full_name,
                "authenticated_login": status.authenticated_login,
                "owned_by_connection": status.owned_by_connection,
                "status": status.status,
                "http_status": status.http_status,
                "accessible": status.accessible,
                "restricted": status.restricted,
                "fork": bool(repository.get("fork")) if repository else None,
                "private": bool(repository.get("private")) if repository else None,
                "disabled": bool(repository.get("disabled")) if repository else None,
                "html_url": repository.get("html_url") if repository else None,
                "monitored_locally": local_repository is not None,
                "local_repository_id": str(local_repository.id) if local_repository else None,
                "required_confirmation": deletion_confirmation(full_name),
            },
        )
    finally:
        await client.close()


@router.post(
    "/connections/{connection_id}/compliance/delete-repository",
    response_model=ToolResult,
)
async def delete_compliance_repository(
    connection_id: uuid.UUID,
    payload: RepositoryComplianceDeleteRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> ToolResult:
    connection = await _owned_connection(db, connection_id, current_user.id)
    if not connection.token_encrypted:
        raise HTTPException(status_code=400, detail="Conexão sem token operacional.")
    try:
        full_name = normalize_full_name(payload.full_name)
        validate_personal_owner(full_name, connection.github_login)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    expected = deletion_confirmation(full_name)
    if payload.confirmation != expected:
        raise HTTPException(status_code=400, detail=f"Digite exatamente: {expected}")

    token = EncryptionService().decrypt(connection.token_encrypted)
    client = GitHubClient(token, api_url=connection.api_url)
    try:
        try:
            await client.delete_repository(full_name)
        except GitHubAPIError as exc:
            raise _compliance_delete_error(exc) from exc

        local_result = await db.execute(
            select(Repository).where(
                Repository.connection_id == connection.id,
                Repository.full_name == full_name,
            )
        )
        local_repository = local_result.scalar_one_or_none()
        local_removed = False
        if local_repository is not None:
            await db.delete(local_repository)
            local_removed = True

        await record_audit(
            db,
            action="github.repository_compliance_deleted",
            user_id=current_user.id,
            entity_type="repository",
            entity_id=full_name,
            details={
                "connection_id": str(connection.id),
                "github_login": connection.github_login,
                "local_removed": local_removed,
                "reason": "user_requested_compliance_cleanup",
            },
        )
        await db.commit()
        return ToolResult(
            message=f"Repositório {full_name} removido da conta GitHub.",
            data={
                "full_name": full_name,
                "deleted": True,
                "local_removed": local_removed,
            },
        )
    finally:
        await client.close()


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
