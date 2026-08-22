from __future__ import annotations

from typing import Any
from urllib.parse import quote

from app.services.github_client import GitHubAPIError, GitHubClient
from app.services.github_management import GitHubManagementService


class GhcrError(RuntimeError):
    pass


class GhcrService:
    def __init__(self, client: GitHubClient, authenticated_login: str) -> None:
        self.client = client
        self.authenticated_login = authenticated_login
        self.management = GitHubManagementService(client)

    async def list_packages(self, owner: str, limit: int = 100) -> list[dict[str, Any]]:
        owner_type = await self.management.owner_type(owner)
        encoded = quote(owner, safe="")
        if owner_type == "org": path = f"/orgs/{encoded}/packages"
        elif owner.lower() == self.authenticated_login.lower(): path = "/user/packages"
        else: path = f"/users/{encoded}/packages"
        try:
            return await self.client.paginate(path, params={"package_type":"container"}, limit=limit)
        except GitHubAPIError as exc:
            if exc.status_code in {403,404}: return []
            raise

    async def package_detail(self, owner: str, package_name: str) -> dict[str, Any]:
        packages=await self.list_packages(owner,limit=300)
        package=next((item for item in packages if str(item.get("name"))==package_name),None)
        versions=await self.management.package_versions(owner=owner,package_name=package_name,authenticated_login=self.authenticated_login,limit=300)
        return {"package":package,"versions":versions,"version_count":len(versions),"tag_count":sum(len(item.get("tags") or []) for item in versions)}

    async def find_version_by_tag(self, owner:str, package_name:str, tag:str)->dict[str,Any]|None:
        versions=await self.management.package_versions(owner=owner,package_name=package_name,authenticated_login=self.authenticated_login,limit=500)
        return next((item for item in versions if tag in (item.get("tags") or [])),None)

    async def delete_version_by_tag(self, owner:str, package_name:str, tag:str)->dict[str,Any]:
        version=await self.find_version_by_tag(owner,package_name,tag)
        if not version: raise GhcrError(f"Tag {tag} não encontrada em {package_name}.")
        await self.management.delete_package_version(owner=owner,package_name=package_name,version_id=int(version["id"]),authenticated_login=self.authenticated_login)
        return {"deleted_version_id":version["id"],"tag":tag}

    async def delete_all_versions(self, owner:str, package_name:str, *, preserve_tags:set[str]|None=None)->dict[str,Any]:
        preserve_tags=preserve_tags or set(); versions=await self.management.package_versions(owner=owner,package_name=package_name,authenticated_login=self.authenticated_login,limit=500); deleted=[]; preserved=[]; failed=[]
        for version in versions:
            tags=set(version.get("tags") or [])
            if tags & preserve_tags: preserved.append({"id":version["id"],"tags":sorted(tags)}); continue
            try:
                await self.management.delete_package_version(owner=owner,package_name=package_name,version_id=int(version["id"]),authenticated_login=self.authenticated_login); deleted.append(int(version["id"]))
            except Exception as exc: failed.append({"id":version["id"],"error":str(exc)})
        return {"deleted":deleted,"preserved":preserved,"failed":failed}

    async def delete_package(self, owner:str, package_name:str)->None:
        await self.management.delete_package(owner=owner,package_name=package_name,authenticated_login=self.authenticated_login)
