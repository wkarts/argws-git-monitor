from __future__ import annotations

import base64
import json
import mimetypes
import os
import shutil
import subprocess
import tarfile
import tempfile
import uuid
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import EncryptionService
from app.models.github import GitHubConnection
from app.models.platform import BackupSnapshot, StorageProvider
from app.services.backup_service import sha256_file
from app.services.github_client import GitHubClient
from app.services.storage_providers import build_storage_adapter


class RestoreError(RuntimeError):
    pass


def _git_env(token: str) -> dict[str, str]:
    credentials = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    env = os.environ.copy(); env.update({"GIT_TERMINAL_PROMPT":"0","GIT_CONFIG_COUNT":"1","GIT_CONFIG_KEY_0":"http.extraHeader","GIT_CONFIG_VALUE_0":f"Authorization: Basic {credentials}"}); return env


def _run(args: list[str], *, cwd: Path | None=None, env: dict[str,str] | None=None, timeout:int=1800)->str:
    process=subprocess.run(args,cwd=str(cwd) if cwd else None,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout,check=False)
    if process.returncode: raise RestoreError(process.stdout[-6000:])
    return process.stdout


def _safe_extract(tar:tarfile.TarFile,destination:Path)->None:
    base=destination.resolve()
    for member in tar.getmembers():
        target=(destination/member.name).resolve()
        if not str(target).startswith(str(base)+os.sep) and target!=base: raise RestoreError("Backup contém caminho inseguro.")
    tar.extractall(destination)


async def inspect_restore(session:AsyncSession,*,snapshot_id:uuid.UUID)->dict[str,Any]:
    snapshot=await session.get(BackupSnapshot,snapshot_id)
    if not snapshot: raise RestoreError("Backup não encontrado.")
    return {"snapshot_id":str(snapshot.id),"repository_id":str(snapshot.repository_id),"backup_type":snapshot.backup_type,"status":snapshot.status,"location":snapshot.location,"checksum_sha256":snapshot.checksum_sha256,"size_bytes":snapshot.size_bytes,"manifest":snapshot.manifest,"destructive":True,"warning":"Restaurar para repositório existente pode sobrescrever refs/tags. Use simulação antes da execução."}


async def restore_snapshot(session:AsyncSession,*,user_id:uuid.UUID,snapshot_id:uuid.UUID,destination:str,connection_id:uuid.UUID|None,repository_full_name:str|None,new_repository_name:str|None,branch:str|None,restore_tags:bool,restore_releases:bool,target_path:str|None,simulate:bool,confirmation:str|None)->dict[str,Any]:
    snapshot=await session.get(BackupSnapshot,snapshot_id)
    if not snapshot or snapshot.user_id!=user_id: raise RestoreError("Backup não encontrado.")
    if not snapshot.location or not snapshot.checksum_sha256: raise RestoreError("Backup não possui localização/checksum utilizável.")
    provider=await session.get(StorageProvider,snapshot.provider_id)
    if not provider or provider.user_id!=user_id: raise RestoreError("Provider do backup não encontrado.")
    preview=await inspect_restore(session,snapshot_id=snapshot_id)
    if simulate: return {"simulated":True,**preview}
    expected=f"RESTAURAR {snapshot.id}"
    if confirmation!=expected: raise RestoreError(f"Confirmação inválida. Digite exatamente: {expected}")
    with tempfile.TemporaryDirectory(prefix="argws-restore-") as temp:
        root=Path(temp); archive=root/"snapshot.tar.gz"; build_storage_adapter(provider).download(snapshot.location,archive)
        actual=sha256_file(archive)
        if actual!=snapshot.checksum_sha256: raise RestoreError(f"Checksum divergente. Esperado {snapshot.checksum_sha256}; recebido {actual}.")
        with tarfile.open(archive,"r:gz") as tar: _safe_extract(tar,root/"extracted")
        extracted=root/"extracted"; manifest=json.loads((extracted/"manifest.json").read_text("utf-8")); bundle=extracted/"repository.bundle"
        if destination in {"local","sftp"}:
            if not target_path: raise RestoreError("target_path é obrigatório para restauração em diretório.")
            if destination=="sftp": raise RestoreError("Restauração SFTP usa Deployment Target para credenciais e auditoria.")
            path=Path(target_path); path.mkdir(parents=True,exist_ok=True)
            if bundle.exists(): _run(["git","clone",str(bundle),str(path)])
            releases=extracted/"releases"
            if releases.exists(): shutil.copytree(releases,path/"releases",dirs_exist_ok=True)
            return {"simulated":False,"destination":str(path),"manifest":manifest,"checksum_valid":True}
        if not connection_id: raise RestoreError("connection_id é obrigatório para restauração no GitHub.")
        connection=await session.get(GitHubConnection,connection_id)
        if not connection or connection.user_id!=user_id or not connection.token_encrypted: raise RestoreError("Conexão GitHub inválida.")
        token=EncryptionService().decrypt(connection.token_encrypted); client=GitHubClient(token,api_url=connection.api_url)
        try:
            target=repository_full_name
            if destination=="new_github_repository":
                name=(new_repository_name or "").strip()
                if not name: raise RestoreError("Informe o nome do novo repositório.")
                created=await client.create_repository(name=name,description="Restaurado pelo ARGWS Git Monitor",private=True); target=str(created.get("full_name") or "")
            if not target: raise RestoreError("Repositório de destino não informado.")
        finally: await client.close()
        if not bundle.exists(): raise RestoreError("Este snapshot não contém bundle Git.")
        restore_repo=root/"restore.git"; _run(["git","clone","--mirror",str(bundle),str(restore_repo)]); env=_git_env(token); remote_url=f"https://github.com/{target}.git"; _run(["git","remote","set-url","origin",remote_url],cwd=restore_repo)
        if branch: _run(["git","push","origin",f"refs/heads/{branch}:refs/heads/{branch}","--force-with-lease"],cwd=restore_repo,env=env)
        elif restore_tags: _run(["git","push","--mirror","origin"],cwd=restore_repo,env=env,timeout=3600)
        else: _run(["git","push","origin","refs/heads/*:refs/heads/*"],cwd=restore_repo,env=env,timeout=3600)
        restored=[]
        if restore_releases:
            release_root=extracted/"releases"; client=GitHubClient(token,api_url=connection.api_url)
            try:
                for release in manifest.get("releases") or []:
                    tag=str(release.get("tag_name") or "").strip()
                    if not tag: continue
                    try:
                        response=await client.request("POST",f"/repos/{target}/releases",json={"tag_name":tag,"target_commitish":release.get("target_commitish") or branch or manifest.get("default_branch") or "main","name":release.get("name") or tag,"body":release.get("body") or "Restaurado pelo ARGWS Git Monitor","draft":bool(release.get("draft",False)),"prerelease":bool(release.get("prerelease",False))}); created=response.json()
                    except Exception as exc:
                        restored.append({"tag":tag,"status":"warning","error":str(exc)[:1000]}); continue
                    uploaded=[]; upload_url=str(created.get("upload_url") or "").split("{",1)[0]; tag_dir=release_root/tag.replace("/","_")
                    if upload_url and tag_dir.exists():
                        headers={"Authorization":f"Bearer {token}","Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"}
                        async with httpx.AsyncClient(timeout=300) as http:
                            for asset in release.get("assets") or []:
                                file_path=tag_dir/Path(str(asset.get("name") or "")).name
                                if not file_path.exists(): continue
                                checksum=str(asset.get("sha256") or "")
                                if checksum and sha256_file(file_path)!=checksum:
                                    restored.append({"tag":tag,"status":"warning","error":f"Checksum do asset {file_path.name} divergente"}); continue
                                mime=mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"; result=await http.post(upload_url,params={"name":file_path.name},headers={**headers,"Content-Type":mime},content=file_path.read_bytes())
                                if result.is_success: uploaded.append(file_path.name)
                                else: restored.append({"tag":tag,"status":"warning","error":f"Asset {file_path.name}: HTTP {result.status_code}"})
                    restored.append({"tag":tag,"status":"restored","assets":uploaded})
            finally: await client.close()
        return {"simulated":False,"destination":target,"manifest":manifest,"checksum_valid":True,"branch":branch,"restore_tags":restore_tags,"restored_releases":restored}
