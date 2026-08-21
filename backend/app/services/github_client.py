from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from app.core.config import get_settings


class GitHubAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GitHubRateLimitError(GitHubAPIError):
    pass


class GitHubClient:
    def __init__(self, token: str, *, api_url: str | None = None) -> None:
        settings = get_settings()
        self.api_url = (api_url or settings.github_api_url).rstrip("/")
        self.timeout = settings.github_request_timeout_seconds
        self.rate_limit_remaining: int | None = None
        self.rate_limit_reset_at: datetime | None = None
        self.oauth_scopes: list[str] = []
        self.accepted_permissions: str | None = None
        self._client = httpx.AsyncClient(
            base_url=self.api_url,
            timeout=httpx.Timeout(self.timeout),
            follow_redirects=True,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": settings.github_api_version,
                "User-Agent": f"ARGWS-Git-Monitor/{settings.app_version}",
            },
        )

    async def __aenter__(self) -> GitHubClient:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    def _capture_response_metadata(self, response: httpx.Response) -> None:
        remaining = response.headers.get("x-ratelimit-remaining")
        reset = response.headers.get("x-ratelimit-reset")
        scopes = response.headers.get("x-oauth-scopes")
        accepted_permissions = response.headers.get("x-accepted-github-permissions")
        if remaining and remaining.isdigit():
            self.rate_limit_remaining = int(remaining)
        if reset and reset.isdigit():
            self.rate_limit_reset_at = datetime.fromtimestamp(int(reset), tz=UTC)
        if scopes is not None:
            self.oauth_scopes = [item.strip() for item in scopes.split(",") if item.strip()]
        if accepted_permissions:
            self.accepted_permissions = accepted_permissions

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        response: httpx.Response | None = None
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = await self._client.request(method, path, params=params, json=json)
                break
            except (httpx.ConnectError, httpx.ReadTimeout) as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(0.5 * (2**attempt))
            except httpx.HTTPError as exc:
                raise GitHubAPIError(f"Falha de comunicação com o GitHub: {exc}") from exc
        if response is None:
            raise GitHubAPIError(f"Falha de comunicação com o GitHub: {last_error}") from last_error

        self._capture_response_metadata(response)
        if response.status_code == 403 and self.rate_limit_remaining == 0:
            reset_text = (
                self.rate_limit_reset_at.isoformat() if self.rate_limit_reset_at else "desconhecido"
            )
            raise GitHubRateLimitError(
                f"Limite da API do GitHub atingido; redefinição em {reset_text}.",
                status_code=403,
            )
        if response.status_code >= 400:
            try:
                payload = response.json()
                detail = payload.get("message") or str(payload)
            except ValueError:
                detail = response.text[:500]
            raise GitHubAPIError(
                f"GitHub respondeu HTTP {response.status_code}: {detail}",
                status_code=response.status_code,
            )
        return response

    async def get_json(
        self, path: str, *, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | list[Any]:
        response = await self.request("GET", path, params=params)
        return response.json()

    async def paginate(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        limit: int = 300,
    ) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        page = 1
        base_params = dict(params or {})
        while len(collected) < limit:
            page_params = {**base_params, "per_page": min(100, limit - len(collected)), "page": page}
            response = await self.request("GET", path, params=page_params)
            payload = response.json()
            if isinstance(payload, dict):
                items = payload.get("workflow_runs") or payload.get("items") or []
            else:
                items = payload
            if not isinstance(items, list):
                raise GitHubAPIError(f"Resposta inesperada do GitHub em {path}.")
            collected.extend(item for item in items if isinstance(item, dict))
            if "rel=\"next\"" not in response.headers.get("link", ""):
                break
            page += 1
            await asyncio.sleep(0)
        return collected[:limit]

    async def get_authenticated_user(self) -> dict[str, Any]:
        payload = await self.get_json("/user")
        if not isinstance(payload, dict):
            raise GitHubAPIError("O GitHub não retornou o usuário autenticado.")
        return payload

    async def list_repositories(self, *, limit: int = 300) -> list[dict[str, Any]]:
        return await self.paginate(
            "/user/repos",
            params={
                "affiliation": "owner,collaborator,organization_member",
                "visibility": "all",
                "sort": "updated",
                "direction": "desc",
            },
            limit=limit,
        )

    async def create_repository(
        self,
        *,
        name: str,
        description: str | None = None,
        private: bool = True,
        auto_init: bool = True,
    ) -> dict[str, Any]:
        response = await self.request(
            "POST",
            "/user/repos",
            json={
                "name": name,
                "description": description or "",
                "private": private,
                "auto_init": auto_init,
                "has_issues": True,
                "has_projects": True,
                "has_wiki": False,
                "delete_branch_on_merge": True,
            },
        )
        payload = response.json()
        if not isinstance(payload, dict):
            raise GitHubAPIError("O GitHub não retornou o repositório criado.")
        return payload

    async def get_repository(self, full_name: str) -> dict[str, Any]:
        payload = await self.get_json(f"/repos/{full_name}")
        if not isinstance(payload, dict):
            raise GitHubAPIError(f"Resposta inválida para o repositório {full_name}.")
        return payload

    async def update_repository(
        self,
        full_name: str,
        *,
        private: bool | None = None,
        archived: bool | None = None,
        description: str | None = None,
        default_branch: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if private is not None:
            payload["private"] = private
        if archived is not None:
            payload["archived"] = archived
        if description is not None:
            payload["description"] = description
        if default_branch is not None:
            payload["default_branch"] = default_branch
        if not payload:
            return await self.get_repository(full_name)
        response = await self.request("PATCH", f"/repos/{full_name}", json=payload)
        data = response.json()
        if not isinstance(data, dict):
            raise GitHubAPIError(f"Resposta inválida ao atualizar {full_name}.")
        return data

    async def delete_repository(self, full_name: str) -> None:
        await self.request("DELETE", f"/repos/{full_name}")

    async def list_commits(self, full_name: str, *, limit: int = 1) -> list[dict[str, Any]]:
        return await self.paginate(f"/repos/{full_name}/commits", limit=limit)

    async def list_branches(self, full_name: str, *, limit: int = 100) -> list[dict[str, Any]]:
        return await self.paginate(f"/repos/{full_name}/branches", limit=limit)

    async def list_workflow_runs(
        self, full_name: str, *, limit: int = 30
    ) -> list[dict[str, Any]]:
        return await self.paginate(f"/repos/{full_name}/actions/runs", limit=limit)

    async def list_pull_requests(
        self, full_name: str, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        return await self.paginate(
            f"/repos/{full_name}/pulls",
            params={"state": "open", "sort": "updated", "direction": "desc"},
            limit=limit,
        )

    async def list_releases(self, full_name: str, *, limit: int = 20) -> list[dict[str, Any]]:
        return await self.paginate(f"/repos/{full_name}/releases", limit=limit)

    async def rerun_failed_workflow(self, full_name: str, run_id: int) -> None:
        await self.request("POST", f"/repos/{full_name}/actions/runs/{run_id}/rerun-failed-jobs")

    async def rerun_workflow(self, full_name: str, run_id: int) -> None:
        await self.request("POST", f"/repos/{full_name}/actions/runs/{run_id}/rerun")

    async def cancel_workflow(self, full_name: str, run_id: int) -> None:
        await self.request("POST", f"/repos/{full_name}/actions/runs/{run_id}/cancel")

    async def create_webhook(
        self,
        full_name: str,
        *,
        webhook_url: str,
        secret: str,
    ) -> dict[str, Any]:
        parsed = urlparse(webhook_url)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise ValueError("URL de webhook inválida.")
        response = await self.request(
            "POST",
            f"/repos/{full_name}/hooks",
            json={
                "name": "web",
                "active": True,
                "events": ["push", "pull_request", "workflow_run", "release", "issues"],
                "config": {
                    "url": webhook_url,
                    "content_type": "json",
                    "secret": secret,
                    "insecure_ssl": "0",
                },
            },
        )
        payload = response.json()
        return payload if isinstance(payload, dict) else {}
