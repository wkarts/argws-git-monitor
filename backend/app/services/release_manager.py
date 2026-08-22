from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import EncryptionService
from app.models.github import GitHubConnection, Repository
from app.models.platform import PublishingChannel, StorageProvider
from app.services.github_client import GitHubClient
from app.services.replication_service import replicate_repository
from app.services.storage_providers import build_storage_adapter


class ReleaseManagerError(RuntimeError):
    pass


async def _upload_assets(upload_url:str, token:str, assets:list[dict[str,Any]])->list[dict[str,Any]]:
    uploaded=[]
    if not upload_url: return uploaded
    async with httpx.AsyncClient(timeout=300,follow_redirects=True) as http:
        for asset in assets:
            local_path=Path(str(asset.get("local_path") or ""))
            if not local_path.is_file(): raise ReleaseManagerError(f"Asset não encontrado: {local_path}")
            media=mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
            response=await http.post(upload_url,headers={"Authorization":f"Bearer {token}","Accept":"application/vnd.github+json","Content-Type":media,"X-GitHub-Api-Version":"2022-11-28"},params={"name":asset.get("name") or local_path.name,"label":asset.get("label")},content=local_path.read_bytes()); response.raise_for_status(); uploaded.append(response.json())
    return uploaded


async def create_release(session:AsyncSession,*,user_id:uuid.UUID,repository_id:uuid.UUID,tag_name:str,target_commitish:str,name:str|None,body:str|None,draft:bool,prerelease:bool,make_latest:bool,create_tag:bool,assets:list[dict[str,Any]],channel_ids:list[uuid.UUID])->dict[str,Any]:
    repository=await session.get(Repository,repository_id)
    if not repository: raise ReleaseManagerError("Repositório não encontrado.")
    connection=await session.get(GitHubConnection,repository.connection_id)
    if not connection or connection.user_id!=user_id or not connection.token_encrypted: raise ReleaseManagerError("Conexão GitHub inválida.")
    token=EncryptionService().decrypt(connection.token_encrypted); client=GitHubClient(token,api_url=connection.api_url)
    try:
        if create_tag:
            try: await client.get_json(f"/repos/{repository.full_name}/git/ref/tags/{quote(tag_name,safe='')}")
            except Exception:
                target=await client.get_json(f"/repos/{repository.full_name}/commits/{quote(target_commitish,safe='')}"); sha=str((target or {}).get("sha") or "")
                if not sha: raise ReleaseManagerError(f"Não foi possível resolver {target_commitish}.")
                await client.request("POST",f"/repos/{repository.full_name}/git/refs",json={"ref":f"refs/tags/{tag_name}","sha":sha})
        response=await client.request("POST",f"/repos/{repository.full_name}/releases",json={"tag_name":tag_name,"target_commitish":target_commitish,"name":name or tag_name,"body":body or "","draft":draft,"prerelease":prerelease,"generate_release_notes":not bool(body),"make_latest":"true" if make_latest else "false"}); release=response.json(); release_id=release.get("id"); uploaded_assets=await _upload_assets(str(release.get("upload_url") or "").split("{",1)[0],token,assets)
        published=[]
        for channel_id in channel_ids:
            channel=await session.get(PublishingChannel,channel_id)
            if not channel or channel.user_id!=user_id or not channel.enabled: continue
            if channel.kind=="github_release": published.append({"channel":channel.name,"status":"already_published"}); continue
            if channel.storage_provider_id:
                provider=await session.get(StorageProvider,channel.storage_provider_id)
                if not provider or provider.user_id!=user_id: raise ReleaseManagerError(f"Canal {channel.name}: provider inválido.")
                adapter=build_storage_adapter(provider)
                for asset in assets:
                    local_path=Path(str(asset.get("local_path") or ""))
                    if not local_path.is_file(): continue
                    location=adapter.upload(local_path,f"{repository.owner}/{repository.name}/releases/{tag_name}/{asset.get('name') or local_path.name}"); published.append({"channel":channel.name,"status":"completed","asset":local_path.name,"location":location})
            elif channel.kind=="github_repository" and channel.repository_id:
                destination=await session.get(Repository,channel.repository_id)
                if not destination: raise ReleaseManagerError(f"Canal {channel.name}: repositório de destino não encontrado.")
                destination_connection=await session.get(GitHubConnection,destination.connection_id)
                if not destination_connection or destination_connection.user_id!=user_id or not destination_connection.token_encrypted: raise ReleaseManagerError(f"Canal {channel.name}: conexão de destino inválida.")
                await replicate_repository(session,user_id=user_id,repository_id=repository.id,mode="release",destination_kind="github_repository",destination_connection_id=destination_connection.id,destination_repository=destination.full_name,provider_id=None,branch=None,release_tag=tag_name,overwrite=False)
                destination_token=EncryptionService().decrypt(destination_connection.token_encrypted); destination_client=GitHubClient(destination_token,api_url=destination_connection.api_url)
                try:
                    destination_response=await destination_client.request("POST",f"/repos/{destination.full_name}/releases",json={"tag_name":tag_name,"target_commitish":tag_name,"name":name or tag_name,"body":body or "","draft":draft,"prerelease":prerelease,"generate_release_notes":not bool(body),"make_latest":"true" if make_latest else "false"}); destination_release=destination_response.json(); destination_assets=await _upload_assets(str(destination_release.get("upload_url") or "").split("{",1)[0],destination_token,assets); published.append({"channel":channel.name,"status":"completed","repository_id":str(destination.id),"repository":destination.full_name,"release_id":destination_release.get("id"),"assets":len(destination_assets)})
                finally: await destination_client.close()
        return {"repository":repository.full_name,"release_id":release_id,"tag_name":tag_name,"html_url":release.get("html_url"),"assets":uploaded_assets,"channels":published}
    finally: await client.close()
