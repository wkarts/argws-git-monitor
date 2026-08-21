from __future__ import annotations

import base64
from typing import Any
from urllib.parse import quote

from app.services.github_client import GitHubAPIError, GitHubClient


class GitHubManagementService:
    """Operações online equivalentes à ferramenta PowerShell, usando a API GitHub."""

    def __init__(self, client: GitHubClient) -> None:
        self.client = client

    async def list_branches(self, full_name: str) -> list[dict[str, Any]]:
        return await self.client.list_branches(full_name, limit=200)

    async def ensure_branch(
        self,
        full_name: str,
        branch: str,
        *,
        base_branch: str | None = None,
        set_default: bool = False,
    ) -> dict[str, Any]:
        branch_name = branch.strip()
        if not branch_name:
            raise ValueError("Nome da branch é obrigatório.")
        encoded = quote(branch_name, safe="")
        try:
            payload = await self.client.get_json(f"/repos/{full_name}/git/ref/heads/{encoded}")
            created = False
        except GitHubAPIError as exc:
            if exc.status_code != 404:
                raise
            repository = await self.client.get_repository(full_name)
            source_branch = base_branch or str(repository.get("default_branch") or "main")
            source_encoded = quote(source_branch, safe="")
            source = await self.client.get_json(
                f"/repos/{full_name}/git/ref/heads/{source_encoded}"
            )
            if not isinstance(source, dict):
                raise GitHubAPIError("Referência base inválida retornada pelo GitHub.")
            sha = str(((source.get("object") or {}).get("sha") or ""))
            if not sha:
                raise GitHubAPIError("Não foi possível identificar o SHA da branch base.")
            response = await self.client.request(
                "POST",
                f"/repos/{full_name}/git/refs",
                json={"ref": f"refs/heads/{branch_name}", "sha": sha},
            )
            payload = response.json()
            created = True

        if set_default:
            await self.client.update_repository(full_name, default_branch=branch_name)
        return {"branch": branch_name, "created": created, "set_default": set_default, "ref": payload}

    async def list_tree(
        self,
        full_name: str,
        *,
        branch: str,
        prefix: str | None = None,
    ) -> list[dict[str, Any]]:
        encoded = quote(branch, safe="")
        payload = await self.client.get_json(
            f"/repos/{full_name}/git/trees/{encoded}",
            params={"recursive": "1"},
        )
        if not isinstance(payload, dict):
            raise GitHubAPIError("Árvore inválida retornada pelo GitHub.")
        tree = payload.get("tree") or []
        normalized_prefix = (prefix or "").strip("/")
        items: list[dict[str, Any]] = []
        for item in tree:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "")
            if normalized_prefix and path != normalized_prefix and not path.startswith(
                f"{normalized_prefix}/"
            ):
                continue
            items.append(
                {
                    "path": path,
                    "type": str(item.get("type") or ""),
                    "mode": str(item.get("mode") or ""),
                    "sha": str(item.get("sha") or ""),
                    "size": item.get("size"),
                }
            )
        return items

    async def get_file_sha(self, full_name: str, *, path: str, branch: str) -> str | None:
        normalized = path.strip("/")
        encoded_path = "/".join(quote(part, safe="") for part in normalized.split("/"))
        try:
            payload = await self.client.get_json(
                f"/repos/{full_name}/contents/{encoded_path}", params={"ref": branch}
            )
        except GitHubAPIError as exc:
            if exc.status_code == 404:
                return None
            raise
        if isinstance(payload, dict):
            sha = payload.get("sha")
            return str(sha) if sha else None
        return None

    async def put_file(
        self,
        full_name: str,
        *,
        path: str,
        content: str,
        branch: str,
        message: str,
        overwrite: bool = True,
    ) -> dict[str, Any]:
        normalized = path.strip("/")
        if not normalized or normalized.endswith("/"):
            raise ValueError("Informe um caminho de arquivo válido.")
        existing_sha = await self.get_file_sha(full_name, path=normalized, branch=branch)
        if existing_sha and not overwrite:
            return {"path": normalized, "changed": False, "reason": "already_exists"}
        encoded_path = "/".join(quote(part, safe="") for part in normalized.split("/"))
        body: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if existing_sha:
            body["sha"] = existing_sha
        response = await self.client.request(
            "PUT", f"/repos/{full_name}/contents/{encoded_path}", json=body
        )
        payload = response.json()
        return {
            "path": normalized,
            "changed": True,
            "created": existing_sha is None,
            "result": payload if isinstance(payload, dict) else {},
        }

    async def delete_file(
        self,
        full_name: str,
        *,
        path: str,
        branch: str,
        message: str,
    ) -> bool:
        normalized = path.strip("/")
        sha = await self.get_file_sha(full_name, path=normalized, branch=branch)
        if not sha:
            return False
        encoded_path = "/".join(quote(part, safe="") for part in normalized.split("/"))
        await self.client.request(
            "DELETE",
            f"/repos/{full_name}/contents/{encoded_path}",
            json={"message": message, "sha": sha, "branch": branch},
        )
        return True

    async def delete_path(
        self,
        full_name: str,
        *,
        path: str,
        branch: str,
        message: str,
        max_files: int = 500,
    ) -> dict[str, Any]:
        normalized = path.strip("/")
        direct_sha = await self.get_file_sha(full_name, path=normalized, branch=branch)
        if direct_sha:
            deleted = await self.delete_file(
                full_name, path=normalized, branch=branch, message=message
            )
            return {"deleted": 1 if deleted else 0, "paths": [normalized] if deleted else []}

        tree = await self.list_tree(full_name, branch=branch, prefix=normalized)
        files = [item["path"] for item in tree if item.get("type") == "blob"]
        if len(files) > max_files:
            raise ValueError(
                f"O diretório possui {len(files)} arquivos; limite de segurança é {max_files}."
            )
        deleted_paths: list[str] = []
        for file_path in sorted(files, key=lambda value: value.count("/"), reverse=True):
            if await self.delete_file(
                full_name,
                path=file_path,
                branch=branch,
                message=message,
            ):
                deleted_paths.append(file_path)
        return {"deleted": len(deleted_paths), "paths": deleted_paths}

    async def create_release(
        self,
        full_name: str,
        *,
        tag_name: str,
        target_commitish: str,
        name: str | None = None,
        body: str | None = None,
        prerelease: bool = False,
    ) -> dict[str, Any]:
        response = await self.client.request(
            "POST",
            f"/repos/{full_name}/releases",
            json={
                "tag_name": tag_name,
                "target_commitish": target_commitish,
                "name": name or tag_name,
                "body": body or "",
                "draft": False,
                "prerelease": prerelease,
                "generate_release_notes": not bool(body),
            },
        )
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    async def dispatch_workflow(
        self,
        full_name: str,
        *,
        workflow: str,
        ref: str,
        inputs: dict[str, str] | None = None,
    ) -> None:
        workflow_id = quote(workflow.strip(), safe="")
        await self.client.request(
            "POST",
            f"/repos/{full_name}/actions/workflows/{workflow_id}/dispatches",
            json={"ref": ref, "inputs": inputs or {}},
        )

    async def bootstrap_repository(
        self,
        full_name: str,
        *,
        branch: str,
        overwrite: bool,
        include_dockerfile: bool,
        include_workflow: bool,
    ) -> dict[str, Any]:
        repository_name = full_name.split("/", 1)[-1]
        files: dict[str, str] = {
            "README.md": (
                f"# {repository_name}\n\n"
                "Repositório inicializado pelo ARGWS Git Monitor.\n\n"
                "## Desenvolvimento\n\nDescreva aqui os comandos de desenvolvimento e implantação.\n"
            ),
            ".gitignore": (
                ".env\n.env.*\n!.env.example\nnode_modules/\n.venv/\n__pycache__/\n"
                "dist/\nbuild/\n*.log\n.DS_Store\n"
            ),
        }
        if include_dockerfile:
            files["Dockerfile"] = (
                "FROM alpine:3.21\n"
                "WORKDIR /app\n"
                "CMD [\"sh\", \"-c\", \"echo 'Configure o Dockerfile do projeto' && sleep infinity\"]\n"
            )
        if include_workflow:
            files[".github/workflows/docker-publish.yml"] = (
                "name: Docker GHCR\n\n"
                "on:\n"
                "  push:\n"
                "    branches: [main]\n"
                "  workflow_dispatch:\n\n"
                "permissions:\n"
                "  contents: read\n"
                "  packages: write\n\n"
                "jobs:\n"
                "  publish:\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n"
                "      - uses: actions/checkout@v6\n"
                "      - uses: docker/setup-buildx-action@v4\n"
                "      - uses: docker/login-action@v4\n"
                "        with:\n"
                "          registry: ghcr.io\n"
                "          username: ${{ github.actor }}\n"
                "          password: ${{ secrets.GITHUB_TOKEN }}\n"
                "      - uses: docker/build-push-action@v7\n"
                "        with:\n"
                "          context: .\n"
                "          push: true\n"
                "          tags: |\n"
                "            ghcr.io/${{ github.repository }}:latest\n"
                "            ghcr.io/${{ github.repository }}:sha-${{ github.sha }}\n"
            )
        results = []
        for path, content in files.items():
            results.append(
                await self.put_file(
                    full_name,
                    path=path,
                    content=content,
                    branch=branch,
                    message=f"chore: adiciona {path} pelo ARGWS Git Monitor",
                    overwrite=overwrite,
                )
            )
        return {"files": results, "changed": sum(1 for item in results if item["changed"])}

    async def owner_type(self, owner: str) -> str:
        try:
            await self.client.get_json(f"/orgs/{quote(owner, safe='')}")
            return "org"
        except GitHubAPIError as exc:
            if exc.status_code != 404:
                raise
            return "user"

    async def package_versions(
        self,
        *,
        owner: str,
        package_name: str,
        authenticated_login: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        package = quote(package_name, safe="")
        owner_kind = await self.owner_type(owner)
        if owner_kind == "org":
            path = f"/orgs/{quote(owner, safe='')}/packages/container/{package}/versions"
        elif owner.lower() == authenticated_login.lower():
            path = f"/user/packages/container/{package}/versions"
        else:
            path = f"/users/{quote(owner, safe='')}/packages/container/{package}/versions"
        versions = await self.client.paginate(path, limit=limit)
        normalized: list[dict[str, Any]] = []
        for item in versions:
            metadata = item.get("metadata") or {}
            container = metadata.get("container") or {}
            normalized.append(
                {
                    "id": int(item["id"]),
                    "name": str(item.get("name") or ""),
                    "url": item.get("html_url"),
                    "created_at": item.get("created_at"),
                    "updated_at": item.get("updated_at"),
                    "tags": [str(tag) for tag in (container.get("tags") or [])],
                }
            )
        return normalized

    async def delete_package_version(
        self,
        *,
        owner: str,
        package_name: str,
        version_id: int,
        authenticated_login: str,
    ) -> None:
        package = quote(package_name, safe="")
        owner_kind = await self.owner_type(owner)
        if owner_kind == "org":
            base = f"/orgs/{quote(owner, safe='')}/packages/container/{package}"
        elif owner.lower() == authenticated_login.lower():
            base = f"/user/packages/container/{package}"
        else:
            base = f"/users/{quote(owner, safe='')}/packages/container/{package}"
        await self.client.request("DELETE", f"{base}/versions/{version_id}")

    async def delete_package(
        self,
        *,
        owner: str,
        package_name: str,
        authenticated_login: str,
    ) -> None:
        package = quote(package_name, safe="")
        owner_kind = await self.owner_type(owner)
        if owner_kind == "org":
            path = f"/orgs/{quote(owner, safe='')}/packages/container/{package}"
        elif owner.lower() == authenticated_login.lower():
            path = f"/user/packages/container/{package}"
        else:
            path = f"/users/{quote(owner, safe='')}/packages/container/{package}"
        await self.client.request("DELETE", path)
