from __future__ import annotations

import base64
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import EncryptionService
from app.models.github import GitHubConnection, Repository
from app.models.platform import StorageProvider
from app.services.github_client import GitHubClient
from app.services.storage_providers import build_storage_adapter


class ReplicationError(RuntimeError):
    pass


def _env(token: str) -> dict[str, str]:
    credentials = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    env = os.environ.copy(); env.update({"GIT_TERMINAL_PROMPT":"0","GIT_CONFIG_COUNT":"1","GIT_CONFIG_KEY_0":"http.extraHeader","GIT_CONFIG_VALUE_0":f"Authorization: Basic {credentials}"}); return env


def _run(args:list[str],*,cwd:Path|None=None,env:dict[str,str]|None=None,timeout:int=3600)->str:
    process=subprocess.run(args,cwd=str(cwd) if cwd else None,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout,check=False)
    if process.returncode: raise ReplicationError(process.stdout[-6000:])
    return process.stdout


async def replicate_repository(session:AsyncSession,*,user_id:uuid.UUID,repository_id:uuid.UUID,mode:str,destination_kind:str,destination_connection_id:uuid.UUID|None,destination_repository:str|None,provider_id:uuid.UUID|None,branch:str|None,release_tag:str|None,overwrite:bool)->dict[str,Any]:
    source=await session.get(Repository,repository_id)
    if not source: raise ReplicationError("Repositório de origem não encontrado.")
    source_connection=await session.get(GitHubConnection,source.connection_id)
    if not source_connection or source_connection.user_id!=user_id or not source_connection.token_encrypted: raise ReplicationError("Conexão de origem inválida.")
    source_token=EncryptionService().decrypt(source_connection.token_encrypted)
    if destination_kind=="github_repository":
        if not destination_connection_id or not destination_repository: raise ReplicationError("Conexão e repositório de destino são obrigatórios.")
        destination_connection=await session.get(GitHubConnection,destination_connection_id)
        if not destination_connection or destination_connection.user_id!=user_id or not destination_connection.token_encrypted: raise ReplicationError("Conexão GitHub de destino inválida.")
        destination_token=EncryptionService().decrypt(destination_connection.token_encrypted)
        if source.full_name.lower()==destination_repository.lower() and source_connection.id==destination_connection.id: raise ReplicationError("Origem e destino são iguais; replicação recusada para evitar loop.")
        with tempfile.TemporaryDirectory(prefix="argws-replicate-") as temp:
            mirror=Path(temp)/"mirror.git"; _run(["git","clone","--mirror",f"https://github.com/{source.full_name}.git",str(mirror)],env=_env(source_token)); _run(["git","remote","set-url","origin",f"https://github.com/{destination_repository}.git"],cwd=mirror)
            if mode=="mirror": _run(["git","push","--mirror","origin"],cwd=mirror,env=_env(destination_token))
            elif mode=="branch":
                selected=branch or source.default_branch; force=["--force-with-lease"] if overwrite else []; _run(["git","push",*force,"origin",f"refs/heads/{selected}:refs/heads/{selected}"],cwd=mirror,env=_env(destination_token))
            elif mode=="release":
                if not release_tag: raise ReplicationError("release_tag é obrigatório.")
                _run(["git","push","origin",f"refs/tags/{release_tag}:refs/tags/{release_tag}"],cwd=mirror,env=_env(destination_token))
            else: raise ReplicationError(f"Modo {mode} não é suportado para GitHub → GitHub.")
        return {"source":source.full_name,"destination":destination_repository,"mode":mode,"status":"completed"}
    if destination_kind=="storage_provider":
        if not provider_id: raise ReplicationError("provider_id é obrigatório.")
        provider=await session.get(StorageProvider,provider_id)
        if not provider or provider.user_id!=user_id: raise ReplicationError("Provider inválido.")
        adapter=build_storage_adapter(provider)
        with tempfile.TemporaryDirectory(prefix="argws-replicate-") as temp:
            root=Path(temp)
            if mode in {"mirror","branch"}:
                bundle=root/f"{source.owner}-{source.name}.bundle"; mirror=root/"mirror.git"; _run(["git","clone","--mirror",f"https://github.com/{source.full_name}.git",str(mirror)],env=_env(source_token)); refs=["--all"] if mode=="mirror" else [f"refs/heads/{branch or source.default_branch}"]; _run(["git","bundle","create",str(bundle),*refs],cwd=mirror); location=adapter.upload(bundle,f"{source.owner}/{source.name}/replicas/{bundle.name}"); return {"source":source.full_name,"location":location,"mode":mode}
            if mode in {"release","artifacts"}:
                if not release_tag: raise ReplicationError("release_tag é obrigatório.")
                client=GitHubClient(source_token,api_url=source_connection.api_url)
                try:
                    releases=await client.list_releases(source.full_name,limit=100); release=next((i for i in releases if str(i.get("tag_name") or "")==release_tag),None)
                    if not release: raise ReplicationError(f"Release {release_tag} não encontrada.")
                    locations=[]
                    async with httpx.AsyncClient(timeout=300,follow_redirects=True) as http:
                        for asset in release.get("assets") or []:
                            url=asset.get("url")
                            if not url: continue
                            response=await http.get(str(url),headers={"Authorization":f"Bearer {source_token}","Accept":"application/octet-stream"}); response.raise_for_status(); local=root/Path(str(asset.get("name") or asset.get("id"))).name; local.write_bytes(response.content); locations.append(adapter.upload(local,f"{source.owner}/{source.name}/releases/{release_tag}/{local.name}"))
                    return {"source":source.full_name,"release":release_tag,"locations":locations,"mode":mode}
                finally: await client.close()
    raise ReplicationError(f"Destino de replicação não suportado: {destination_kind}")
