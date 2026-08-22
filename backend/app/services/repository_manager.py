from __future__ import annotations

import difflib
import re
from typing import Any
from urllib.parse import quote

from app.services.github_client import GitHubAPIError, GitHubClient
from app.services.github_management import GitHubManagementService


class RepositoryManagerError(RuntimeError):
    pass


class RepositoryManagerService:
    def __init__(self, client: GitHubClient) -> None:
        self.client = client
        self.management = GitHubManagementService(client)

    async def validate_owner(self, owner: str) -> dict[str, Any]:
        encoded = quote(owner.strip(), safe="")
        authenticated = await self.client.get_authenticated_user()
        login = str(authenticated.get("login") or "")
        if owner.lower() == login.lower():
            return {"type": "user", "login": login, "can_create": True}
        try:
            org = await self.client.get_json(f"/orgs/{encoded}")
            membership = await self.client.get_json(f"/user/memberships/orgs/{encoded}")
            state = str((membership or {}).get("state") or "")
            role = str((membership or {}).get("role") or "")
            return {"type":"org","login":str((org or {}).get("login") or owner),"can_create":state=="active" and role in {"admin","member"},"membership_state":state,"role":role}
        except GitHubAPIError as exc:
            if exc.status_code == 404:
                raise RepositoryManagerError(f"Owner {owner} não existe ou não está acessível.") from exc
            raise

    async def repository_exists(self, full_name: str) -> bool:
        try:
            await self.client.get_repository(full_name); return True
        except GitHubAPIError as exc:
            if exc.status_code == 404: return False
            raise

    async def create_repository(self, *, owner:str, name:str, description:str|None, private:bool, default_branch:str) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z0-9._-]+", name): raise RepositoryManagerError("Nome de repositório inválido.")
        owner_info=await self.validate_owner(owner); full_name=f"{owner}/{name}"
        if await self.repository_exists(full_name): raise RepositoryManagerError(f"O repositório {full_name} já existe.")
        path="/user/repos" if owner_info["type"]=="user" else f"/orgs/{quote(owner,safe='')}/repos"
        response=await self.client.request("POST",path,json={"name":name,"description":description or "","private":private,"auto_init":True,"has_issues":True,"has_projects":True,"has_wiki":False,"delete_branch_on_merge":True})
        payload=response.json(); created_full_name=str(payload.get("full_name") or full_name); current_default=str(payload.get("default_branch") or "main")
        if default_branch!=current_default: await self.management.ensure_branch(created_full_name,default_branch,base_branch=current_default,set_default=True)
        return payload

    def template_files(self, *, repository_name:str, template:str, options:dict[str,Any]) -> dict[str,str]:
        files:dict[str,str]={}; include_readme=options.get("readme",template!="empty"); include_gitignore=options.get("gitignore",template in {"docker","docker_ghcr","custom"}); include_dockerfile=options.get("dockerfile",template in {"docker","docker_ghcr"}); include_dockerignore=options.get("dockerignore",template in {"docker","docker_ghcr"}); include_workflow=options.get("workflow",template=="docker_ghcr"); include_editorconfig=options.get("editorconfig",template in {"docker","docker_ghcr","custom"}); license_text=options.get("license_content")
        if include_readme: files["README.md"]=f"# {repository_name}\n\nInicializado pelo ARGWS Git Monitor.\n\n## Desenvolvimento\n\nDocumente aqui os comandos de build, testes e implantação.\n"
        if include_gitignore: files[".gitignore"]=".env\n.env.*\n!.env.example\nnode_modules/\n.venv/\n__pycache__/\ndist/\nbuild/\n*.log\n.DS_Store\n"
        if include_dockerfile: files["Dockerfile"]="FROM alpine:3.21\nWORKDIR /app\nCOPY . /app\nCMD [\"sh\", \"-c\", \"echo 'Ajuste o comando da aplicação' && sleep infinity\"]\n"
        if include_dockerignore: files[".dockerignore"]=".git\n.env\nnode_modules\n.venv\n__pycache__\n*.log\n"
        if include_editorconfig: files[".editorconfig"]="root = true\n\n[*]\ncharset = utf-8\nend_of_line = lf\ninsert_final_newline = true\nindent_style = space\nindent_size = 2\n"
        if license_text: files["LICENSE"]=str(license_text)
        if include_workflow:
            files[".github/workflows/docker-publish.yml"]="""name: Docker GHCR

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  packages: write

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: docker/setup-buildx-action@v4
      - uses: docker/login-action@v4
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v7
        with:
          context: .
          push: true
          tags: |
            ghcr.io/${{ github.repository }}:latest
            ghcr.io/${{ github.repository }}:sha-${{ github.sha }}
"""
        for item in options.get("custom_files") or []:
            path=str(item.get("path") or "").strip("/")
            if path: files[path]=str(item.get("content") or "")
        return files

    async def bootstrap_preview(self, full_name:str, *, branch:str, template:str, options:dict[str,Any])->dict[str,Any]:
        files=self.template_files(repository_name=full_name.split("/")[-1],template=template,options=options); result=[]
        for path,content in files.items():
            encoded="/".join(quote(part,safe="") for part in path.strip("/").split("/")); existing=None
            try:
                payload=await self.client.get_json(f"/repos/{full_name}/contents/{encoded}",params={"ref":branch}); existing=payload if isinstance(payload,dict) else None
            except GitHubAPIError as exc:
                if exc.status_code!=404: raise
            status="CREATE"; diff=""
            if existing:
                status="EXISTS"; download_url=existing.get("download_url")
                if download_url:
                    try:
                        import httpx
                        async with httpx.AsyncClient(timeout=30) as http: response=await http.get(str(download_url))
                        if response.is_success and response.text!=content:
                            status="UPDATE"; diff="\n".join(difflib.unified_diff(response.text.splitlines(),content.splitlines(),fromfile=f"a/{path}",tofile=f"b/{path}",lineterm=""))
                    except Exception: pass
            result.append({"path":path,"status":status,"existing_sha":existing.get("sha") if existing else None,"diff":diff[:12000],"content":content})
        return {"repository":full_name,"branch":branch,"files":result}

    async def apply_bootstrap(self, full_name:str, *, branch:str, files:list[dict[str,Any]])->dict[str,Any]:
        results=[]
        for item in files:
            action=str(item.get("action") or "keep")
            if action=="keep": continue
            results.append(await self.management.put_file(full_name,path=str(item.get("path") or ""),content=str(item.get("content") or ""),branch=branch,message=f"chore: bootstrap {item.get('path')} via ARGWS Git Monitor",overwrite=action=="replace"))
        return {"changed":sum(1 for item in results if item.get("changed")),"files":results}

    async def get_branch_protection(self, full_name:str, branch:str)->dict[str,Any]|None:
        try:
            payload=await self.client.get_json(f"/repos/{full_name}/branches/{quote(branch,safe='')}/protection"); return payload if isinstance(payload,dict) else {}
        except GitHubAPIError as exc:
            if exc.status_code==404: return None
            raise

    async def set_branch_protection(self, full_name:str, *, branch:str, require_pull_request:bool, approvals:int, enforce_admins:bool, allow_force_pushes:bool, allow_deletions:bool, required_status_checks:list[str])->dict[str,Any]:
        payload={"required_status_checks":{"strict":True,"contexts":required_status_checks} if required_status_checks else None,"enforce_admins":enforce_admins,"required_pull_request_reviews":{"dismiss_stale_reviews":False,"require_code_owner_reviews":False,"required_approving_review_count":approvals,"require_last_push_approval":False} if require_pull_request else None,"restrictions":None,"required_linear_history":False,"allow_force_pushes":allow_force_pushes,"allow_deletions":allow_deletions,"block_creations":False,"required_conversation_resolution":False,"lock_branch":False,"allow_fork_syncing":False}
        response=await self.client.request("PUT",f"/repos/{full_name}/branches/{quote(branch,safe='')}/protection",json=payload); result=response.json(); return result if isinstance(result,dict) else {}
