from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.services.github_client import GitHubAPIError, GitHubClient

FULL_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


@dataclass(slots=True, frozen=True)
class RepositoryAccessStatus:
    full_name: str
    authenticated_login: str
    owned_by_connection: bool
    status: str
    http_status: int | None
    accessible: bool
    restricted: bool
    message: str
    repository: dict[str, Any] | None = None


def normalize_full_name(value: str) -> str:
    normalized = value.strip().strip("/")
    if not FULL_NAME_RE.fullmatch(normalized):
        raise ValueError("Informe o repositório no formato owner/repo.")
    return normalized


def validate_personal_owner(full_name: str, authenticated_login: str) -> None:
    owner, _name = full_name.split("/", 1)
    if owner.casefold() != authenticated_login.casefold():
        raise PermissionError(
            "Esta operação de conformidade só remove repositórios da própria conta GitHub conectada."
        )


def deletion_confirmation(full_name: str) -> str:
    return f"EXCLUIR {full_name}"


def classify_access_error(
    full_name: str,
    authenticated_login: str,
    exc: GitHubAPIError,
) -> RepositoryAccessStatus:
    code = exc.status_code
    if code == 451:
        status = "legal_restriction"
        restricted = True
        message = (
            "O GitHub marcou este repositório como indisponível por restrição legal/DMCA. "
            "O Git Monitor pode tentar somente a exclusão definitiva da cópia na sua conta."
        )
    elif code == 403:
        status = "forbidden"
        restricted = True
        message = (
            "O GitHub recusou o acesso administrativo. Verifique se o token possui permissão "
            "para excluir repositórios (Administration: write ou delete_repo, conforme o token)."
        )
    elif code == 404:
        status = "not_visible"
        restricted = True
        message = (
            "O repositório não está visível pela API. Ele pode já ter sido removido, estar "
            "indisponível ou bloqueado. Ainda é possível tentar DELETE pelo nome completo."
        )
    elif code == 401:
        status = "unauthorized"
        restricted = True
        message = "A conexão GitHub não está autorizada. Atualize ou substitua o token."
    else:
        status = "error"
        restricted = False
        message = str(exc)

    return RepositoryAccessStatus(
        full_name=full_name,
        authenticated_login=authenticated_login,
        owned_by_connection=True,
        status=status,
        http_status=code,
        accessible=False,
        restricted=restricted,
        message=message,
    )


async def probe_repository(
    client: GitHubClient,
    *,
    full_name: str,
    authenticated_login: str,
) -> RepositoryAccessStatus:
    normalized = normalize_full_name(full_name)
    validate_personal_owner(normalized, authenticated_login)
    try:
        repository = await client.get_repository(normalized)
    except GitHubAPIError as exc:
        return classify_access_error(normalized, authenticated_login, exc)

    return RepositoryAccessStatus(
        full_name=normalized,
        authenticated_login=authenticated_login,
        owned_by_connection=True,
        status="accessible",
        http_status=200,
        accessible=True,
        restricted=bool(repository.get("disabled")),
        message="Repositório acessível pela API do GitHub.",
        repository=repository,
    )
