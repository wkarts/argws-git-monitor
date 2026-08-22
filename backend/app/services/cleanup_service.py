from __future__ import annotations

import fnmatch
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import EncryptionService
from app.models.github import GitHubConnection, Repository
from app.models.platform import ActionClass, CleanupAnalysis, CleanupCandidate, CleanupProfile, CleanupStatus, DeploymentRecord
from app.services.ghcr_service import GhcrService
from app.services.github_client import GitHubAPIError, GitHubClient
from app.services.github_management import GitHubManagementService

class CleanupError(RuntimeError): pass

def _dt(value: Any) -> datetime | None:
    if not value: return None
    try: return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError: return None

def _older(value: Any, days: int) -> bool:
    stamp=_dt(value); return bool(stamp and stamp < datetime.now(UTC)-timedelta(days=max(0,days)))

def _default_criteria()->dict[str,Any]:
    return {"runs_failed_days":30,"runs_any_days":90,"artifacts_days":30,"cache_days":14,"releases_days":180,"release_tag_pattern":"","release_prerelease":False,"release_draft":False,"release_without_assets":False,"ghcr_untagged_days":30,"branches_merged_days":60,"branches_stale_days":120}

def _default_preservation()->dict[str,Any]:
    return {"preserve_default_branch":True,"preserve_latest_release":True,"preserve_last_releases":5,"preserve_protected_branches":True,"preserve_deployment_refs":True,"preserve_latest_image":True,"preserve_tags":[],"preserve_branches":[]}

async def _resolve_checkpoint(client:GitHubClient,repository:Repository,requested:dict[str,Any])->dict[str,Any]:
    checkpoint=dict(requested or {}); branch=str(checkpoint.get("branch") or repository.default_branch); tag=str(checkpoint.get("tag") or ""); sha=str(checkpoint.get("sha") or "")
    if tag and not sha:
        try:
            ref=await client.get_json(f"/repos/{repository.full_name}/git/ref/tags/{quote(tag,safe='')}"); sha=str(((ref or {}).get("object") or {}).get("sha") or "")
        except GitHubAPIError as exc: raise CleanupError(f"Checkpoint tag {tag} não existe ou não está acessível.") from exc
    if not sha:
        commit=await client.get_json(f"/repos/{repository.full_name}/commits/{quote(branch,safe='')}"); sha=str((commit or {}).get("sha") or "")
    if not sha: raise CleanupError("Não foi possível resolver o SHA do checkpoint canônico.")
    try: commit=await client.get_json(f"/repos/{repository.full_name}/commits/{sha}")
    except GitHubAPIError as exc: raise CleanupError(f"Checkpoint SHA {sha} não existe.") from exc
    return {**checkpoint,"branch":branch,"tag":tag or None,"sha":str((commit or {}).get("sha") or sha),"resolved_at":datetime.now(UTC).isoformat()}

def _candidate(resource_type:str,key:str,resource_id:Any,action_class:str,reason:str,*,metadata:dict[str,Any]|None=None,size:int|None=None,dependencies:list[dict[str,Any]]|None=None,protected:bool=False)->dict[str,Any]:
    return {"resource_type":resource_type,"resource_key":key,"resource_id":str(resource_id) if resource_id is not None else None,"action_class":action_class,"reason":reason,"metadata":metadata or {},"size_bytes":size,"dependencies":dependencies or [],"protected":protected,"selected":False}

async def build_cleanup_analysis(session:AsyncSession,*,user_id:uuid.UUID,repository_id:uuid.UUID,profile_id:uuid.UUID|None=None,criteria:dict[str,Any]|None=None,preservation_rules:dict[str,Any]|None=None,canonical_checkpoint:dict[str,Any]|None=None,job_id:uuid.UUID|None=None)->CleanupAnalysis:
    repository=await session.get(Repository,repository_id)
    if not repository: raise CleanupError("Repositório não encontrado.")
    connection=await session.get(GitHubConnection,repository.connection_id)
    if not connection or connection.user_id!=user_id or not connection.token_encrypted: raise CleanupError("Conexão GitHub inválida.")
    profile=await session.get(CleanupProfile,profile_id) if profile_id else None
    if profile and (profile.user_id!=user_id or profile.repository_id!=repository_id): raise CleanupError("Cleanup Profile não pertence a este repositório.")
    merged_criteria={**_default_criteria(),**(profile.criteria if profile else {}),**(criteria or {})}; rules={**_default_preservation(),**(profile.preservation_rules if profile else {}),**(preservation_rules or {})}; requested_checkpoint={**(profile.canonical_checkpoint if profile else {}),**(canonical_checkpoint or {})}; reference=f"CLN-{datetime.now(UTC).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
    analysis=CleanupAnalysis(user_id=user_id,repository_id=repository_id,profile_id=profile_id,job_id=job_id,reference=reference,status=CleanupStatus.ANALYZING.value,checkpoint={},preservation_rules=rules,metrics={},dependency_graph={},plan=[],dry_run={},estimated_reclaimed_bytes=0,result={},created_at=datetime.now(UTC)); session.add(analysis); await session.flush()
    token=EncryptionService().decrypt(connection.token_encrypted); client=GitHubClient(token,api_url=connection.api_url)
    try:
        checkpoint=await _resolve_checkpoint(client,repository,requested_checkpoint); analysis.checkpoint=checkpoint
        branches=await client.list_branches(repository.full_name,limit=300); releases=await client.list_releases(repository.full_name,limit=200); tags=await client.optional_paginate("tags",f"/repos/{repository.full_name}/tags",limit=300,empty_statuses={403,404}); runs=await client.list_workflow_runs(repository.full_name,limit=300); artifacts=await client.optional_paginate("actions_artifacts",f"/repos/{repository.full_name}/actions/artifacts",limit=300,empty_statuses={403,404})
        cache_payload:dict[str,Any]|list[Any]=[]
        try: cache_payload=await client.get_json(f"/repos/{repository.full_name}/actions/caches",params={"per_page":100})
        except GitHubAPIError as exc:
            if exc.status_code not in {403,404}: raise
        caches=list(cache_payload.get("actions_caches") or []) if isinstance(cache_payload,dict) else []
        packages=await GhcrService(client,connection.github_login).list_packages(repository.owner,limit=100); package_details=[]
        for package in packages[:50]:
            name=str(package.get("name") or "")
            if not name: continue
            try:
                detail=await GhcrService(client,connection.github_login).package_detail(repository.owner,name); package_details.append({"name":name,**detail})
            except GitHubAPIError: continue
        deployment_rows=(await session.execute(select(DeploymentRecord).where(DeploymentRecord.repository_id==repository.id))).scalars().all(); deployment_refs:set[str]=set()
        for deployment in deployment_rows:
            if deployment.requested_ref: deployment_refs.add(str(deployment.requested_ref))
            for payload in (deployment.previous_version or {},deployment.deployed_version or {}):
                for value in payload.values():
                    if isinstance(value,str) and len(value)<=255: deployment_refs.add(value)
        preserve_tags=set(str(x) for x in rules.get("preserve_tags") or []); preserve_branches=set(str(x) for x in rules.get("preserve_branches") or [])
        if checkpoint.get("tag"): preserve_tags.add(str(checkpoint["tag"]))
        if checkpoint.get("branch"): preserve_branches.add(str(checkpoint["branch"]))
        if rules.get("preserve_default_branch",True): preserve_branches.add(repository.default_branch)
        if rules.get("preserve_deployment_refs",True): preserve_tags|=deployment_refs; preserve_branches|=deployment_refs
        ordered_releases=sorted(releases,key=lambda x:str(x.get("published_at") or x.get("created_at") or ""),reverse=True)
        if rules.get("preserve_latest_release",True) and ordered_releases: preserve_tags.add(str(ordered_releases[0].get("tag_name") or ""))
        for item in ordered_releases[:max(0,int(rules.get("preserve_last_releases") or 0))]: preserve_tags.add(str(item.get("tag_name") or ""))
        graph:dict[str,dict[str,list[Any]]]=defaultdict(lambda:{"runs":[],"artifacts":[],"releases":[],"ghcr_versions":[],"deployments":[]}); run_by_id={}
        for run in runs:
            rid=str(run.get("id") or ""); run_by_id[rid]=run; sha=str(run.get("head_sha") or "")
            if sha: graph[sha]["runs"].append(run.get("id"))
        for artifact in artifacts:
            run_id=str(((artifact.get("workflow_run") or {}).get("id") or "")); run=run_by_id.get(run_id); sha=str((run or {}).get("head_sha") or "")
            if sha: graph[sha]["artifacts"].append(artifact.get("id"))
        for release in releases:
            target=str(release.get("target_commitish") or "")
            if len(target)>=7: graph[target]["releases"].append(release.get("id"))
        for deployment in deployment_rows:
            ref=str(deployment.requested_ref or "")
            if ref: graph[ref]["deployments"].append(str(deployment.id))
        for package in package_details:
            package_name=str(package.get("name") or "")
            for version in package.get("versions") or []:
                tags_for_version=[str(x) for x in version.get("tags") or []]
                for tag in tags_for_version:
                    sha_hint=tag.removeprefix("sha-") if tag.startswith("sha-") else ""
                    if len(sha_hint)>=7: graph[sha_hint]["ghcr_versions"].append({"package":package_name,"version_id":version.get("id"),"tags":tags_for_version})
        candidates=[]; runs_failed_days=int(merged_criteria.get("runs_failed_days") or 0); runs_any_days=int(merged_criteria.get("runs_any_days") or 0)
        for run in runs:
            created=run.get("created_at"); conclusion=str(run.get("conclusion") or ""); reason=None
            if runs_failed_days and conclusion in {"failure","cancelled","timed_out"} and _older(created,runs_failed_days): reason=f"Run {conclusion} com mais de {runs_failed_days} dias."
            elif runs_any_days and _older(created,runs_any_days): reason=f"Run com mais de {runs_any_days} dias."
            if reason:
                sha=str(run.get("head_sha") or ""); protected=bool(sha==checkpoint.get("sha") or sha in deployment_refs); candidates.append(_candidate("workflow_run",f"run:{run.get('id')}",run.get("id"),ActionClass.SAFE.value if not protected else ActionClass.REVIEW.value,reason,metadata={"name":run.get("name"),"head_sha":sha,"conclusion":conclusion,"created_at":created},dependencies=[{"sha":sha}] if sha else [],protected=protected))
        artifact_days=int(merged_criteria.get("artifacts_days") or 0)
        for artifact in artifacts:
            if artifact_days and _older(artifact.get("created_at"),artifact_days):
                run_id=str(((artifact.get("workflow_run") or {}).get("id") or "")); run=run_by_id.get(run_id); sha=str((run or {}).get("head_sha") or ""); protected=bool(sha==checkpoint.get("sha") or sha in deployment_refs); candidates.append(_candidate("artifact",f"artifact:{artifact.get('name') or artifact.get('id')}",artifact.get("id"),ActionClass.SAFE.value if not protected else ActionClass.REVIEW.value,f"Artifact com mais de {artifact_days} dias.",metadata={"name":artifact.get("name"),"run_id":run_id,"head_sha":sha,"created_at":artifact.get("created_at")},size=int(artifact.get("size_in_bytes") or 0),dependencies=[{"run_id":run_id},{"sha":sha}] if sha else [{"run_id":run_id}],protected=protected))
        release_days=int(merged_criteria.get("releases_days") or 0); tag_pattern=str(merged_criteria.get("release_tag_pattern") or "")
        for release in releases:
            tag=str(release.get("tag_name") or ""); reasons=[]
            if release_days and _older(release.get("published_at") or release.get("created_at"),release_days): reasons.append(f"mais de {release_days} dias")
            if tag_pattern and fnmatch.fnmatch(tag,tag_pattern): reasons.append(f"tag corresponde a {tag_pattern}")
            if merged_criteria.get("release_prerelease") and release.get("prerelease"): reasons.append("prerelease")
            if merged_criteria.get("release_draft") and release.get("draft"): reasons.append("draft")
            if merged_criteria.get("release_without_assets") and not release.get("assets"): reasons.append("sem assets")
            if reasons:
                protected=tag in preserve_tags; candidates.append(_candidate("release",f"release:{tag}",release.get("id"),ActionClass.DESTRUCTIVE.value,", ".join(reasons),metadata={"tag":tag,"published_at":release.get("published_at"),"assets":len(release.get("assets") or [])},protected=protected)); candidates.append(_candidate("tag",f"tag:{tag}",tag,ActionClass.DESTRUCTIVE.value,f"Tag vinculada à release candidata {tag}.",metadata={"tag":tag},protected=protected))
        cache_days=int(merged_criteria.get("cache_days") or 0)
        for cache in caches:
            if cache_days and _older(cache.get("last_accessed_at") or cache.get("created_at"),cache_days):
                ref=str(cache.get("ref") or ""); protected=bool(any(x and x in ref for x in preserve_branches)); candidates.append(_candidate("actions_cache",f"cache:{cache.get('key') or cache.get('id')}",cache.get("id"),ActionClass.SAFE.value if not protected else ActionClass.REVIEW.value,f"Cache não acessado há mais de {cache_days} dias.",metadata={"key":cache.get("key"),"ref":ref,"last_accessed_at":cache.get("last_accessed_at")},size=int(cache.get("size_in_bytes") or 0),protected=protected))
        ghcr_days=int(merged_criteria.get("ghcr_untagged_days") or 0)
        for package in package_details:
            package_name=str(package.get("name") or "")
            for version in package.get("versions") or []:
                version_tags=[str(x) for x in version.get("tags") or []]
                if version_tags or (ghcr_days and not _older(version.get("created_at"),ghcr_days)): continue
                candidates.append(_candidate("ghcr_version",f"ghcr:{package_name}:{version.get('id')}",version.get("id"),ActionClass.REVIEW.value,f"Versão GHCR sem tag com mais de {ghcr_days} dias.",metadata={"package_name":package_name,"tags":version_tags,"digest":version.get("name"),"created_at":version.get("created_at")}))
        merged_days=int(merged_criteria.get("branches_merged_days") or 0); stale_days=int(merged_criteria.get("branches_stale_days") or 0)
        for branch in branches[:80]:
            name=str(branch.get("name") or "")
            if not name or name==repository.default_branch: continue
            protected=bool(branch.get("protected") or name in preserve_branches); sha=str((branch.get("commit") or {}).get("sha") or ""); updated=None
            try:
                commit=await client.get_json(f"/repos/{repository.full_name}/commits/{sha}"); updated=(((commit or {}).get("commit") or {}).get("committer") or {}).get("date")
            except GitHubAPIError: pass
            is_merged=False
            try:
                cmp=await client.get_json(f"/repos/{repository.full_name}/compare/{quote(repository.default_branch,safe='')}...{quote(name,safe='')}"); is_merged=isinstance(cmp,dict) and int(cmp.get("ahead_by") or 0)==0 and str(cmp.get("status") or "") in {"behind","identical"}
            except GitHubAPIError: pass
            if is_merged and (not merged_days or _older(updated,merged_days)): candidates.append(_candidate("branch",f"branch:{name}",name,ActionClass.REVIEW.value,f"Branch já incorporada à default e sem atualização recente ({merged_days} dias).",metadata={"sha":sha,"updated_at":updated,"merged":True},protected=protected))
            elif stale_days and _older(updated,stale_days): candidates.append(_candidate("branch",f"branch:{name}",name,ActionClass.DESTRUCTIVE.value,f"Branch não confirmada como mergeada e sem atualização há mais de {stale_days} dias.",metadata={"sha":sha,"updated_at":updated,"merged":False},protected=protected))
        for raw in candidates: session.add(CleanupCandidate(analysis_id=analysis.id,**raw))
        analysis.metrics={"workflow_runs":len(runs),"artifacts":len(artifacts),"actions_caches":len(caches),"releases":len(releases),"tags":len(tags),"ghcr_packages":len(package_details),"ghcr_versions":sum(len(p.get("versions") or []) for p in package_details),"branches":len(branches),"candidates":len(candidates),"selected":0,"protected":sum(1 for x in candidates if x["protected"])}; analysis.dependency_graph=dict(graph); analysis.plan=[{"step":1,"name":"Validate canonical checkpoint","status":"pending"},{"step":2,"name":"Protect referenced resources","status":"pending"},{"step":3,"name":"Cancel selected active runs","status":"pending"},{"step":4,"name":"Delete selected Actions artifacts","status":"pending"},{"step":5,"name":"Delete selected workflow runs","status":"pending"},{"step":6,"name":"Delete selected releases and tags","status":"pending"},{"step":7,"name":"Delete selected Actions cache","status":"pending"},{"step":8,"name":"Preserve/rebuild canonical images when configured","status":"pending"},{"step":9,"name":"Delete selected GHCR versions","status":"pending"},{"step":10,"name":"Delete explicitly selected branches","status":"pending"},{"step":11,"name":"Validate repository","status":"pending"},{"step":12,"name":"Generate final audit report","status":"pending"}]; analysis.status=CleanupStatus.PLANNED.value; await session.flush(); return analysis
    except Exception as exc:
        analysis.status=CleanupStatus.FAILED.value; analysis.error=str(exc); analysis.completed_at=datetime.now(UTC); await session.flush(); raise
    finally: await client.close()

async def set_cleanup_selection(session:AsyncSession,*,user_id:uuid.UUID,analysis_id:uuid.UUID,candidate_ids:list[uuid.UUID])->CleanupAnalysis:
    analysis=await session.get(CleanupAnalysis,analysis_id)
    if not analysis or analysis.user_id!=user_id: raise CleanupError("Análise não encontrada.")
    candidates=(await session.execute(select(CleanupCandidate).where(CleanupCandidate.analysis_id==analysis.id))).scalars().all(); requested=set(candidate_ids); unknown=requested-{x.id for x in candidates}
    if unknown: raise CleanupError("A seleção contém candidato que não pertence à análise.")
    for item in candidates: item.selected=item.id in requested and not item.protected
    analysis.metrics={**analysis.metrics,"selected":sum(1 for x in candidates if x.selected)}; analysis.status=CleanupStatus.REVIEW.value; analysis.dry_run={}; await session.flush(); return analysis

async def dry_run_cleanup(session:AsyncSession,*,user_id:uuid.UUID,analysis_id:uuid.UUID)->CleanupAnalysis:
    analysis=await session.get(CleanupAnalysis,analysis_id)
    if not analysis or analysis.user_id!=user_id: raise CleanupError("Análise não encontrada.")
    repository=await session.get(Repository,analysis.repository_id); connection=await session.get(GitHubConnection,repository.connection_id) if repository else None
    if not repository or not connection or connection.user_id!=user_id or not connection.token_encrypted: raise CleanupError("Conexão/repositório indisponível.")
    selected=(await session.execute(select(CleanupCandidate).where(CleanupCandidate.analysis_id==analysis.id,CleanupCandidate.selected.is_(True)))).scalars().all(); token=EncryptionService().decrypt(connection.token_encrypted); client=GitHubClient(token,api_url=connection.api_url); conflicts=[]; valid=0
    try:
        checkpoint=await _resolve_checkpoint(client,repository,analysis.checkpoint)
        if checkpoint.get("sha")!=analysis.checkpoint.get("sha"): conflicts.append({"type":"checkpoint_changed","expected":analysis.checkpoint.get("sha"),"actual":checkpoint.get("sha")})
        for item in selected:
            if item.protected: conflicts.append({"candidate_id":str(item.id),"resource":item.resource_key,"reason":"protected"}); continue
            try:
                if item.resource_type=="artifact": await client.get_json(f"/repos/{repository.full_name}/actions/artifacts/{item.resource_id}")
                elif item.resource_type=="workflow_run": await client.get_json(f"/repos/{repository.full_name}/actions/runs/{item.resource_id}")
                elif item.resource_type=="release": await client.get_json(f"/repos/{repository.full_name}/releases/{item.resource_id}")
                elif item.resource_type=="branch": await client.get_json(f"/repos/{repository.full_name}/branches/{quote(item.resource_id or '',safe='')}")
                elif item.resource_type=="ghcr_version":
                    versions=await GitHubManagementService(client).package_versions(owner=repository.owner,package_name=str(item.metadata.get("package_name") or ""),authenticated_login=connection.github_login,limit=500)
                    if not any(str(x.get("id"))==str(item.resource_id) for x in versions): raise CleanupError("GHCR version não existe mais.")
                valid+=1
            except Exception as exc: conflicts.append({"candidate_id":str(item.id),"resource":item.resource_key,"reason":"resource_changed_or_missing","error":str(exc)[:500]})
        critical=sum(1 for x in conflicts if x.get("type")=="checkpoint_changed" or x.get("reason")=="protected"); analysis.dry_run={"checked_at":datetime.now(UTC).isoformat(),"selected":len(selected),"valid":valid,"conflicts":conflicts,"critical_conflicts":critical,"warnings":len(conflicts)-critical,"delete_calls":0}; analysis.status=CleanupStatus.READY.value if not critical else CleanupStatus.REVIEW.value; await session.flush(); return analysis
    finally: await client.close()

async def _ensure_canonical(client:GitHubClient,connection:GitHubConnection,repository:Repository,analysis:CleanupAnalysis,candidates:list[CleanupCandidate])->dict[str,Any]:
    if not any(x.resource_type=="ghcr_version" for x in candidates): return {"required":False,"status":"not_required"}
    workflow=str(analysis.checkpoint.get("rebuild_workflow") or "").strip(); required_package=str(analysis.checkpoint.get("required_package") or "").strip(); required_tag=str(analysis.checkpoint.get("required_tag") or "").strip()
    if workflow:
        ref=str(analysis.checkpoint.get("rebuild_ref") or analysis.checkpoint.get("branch") or repository.default_branch); inputs={str(k):str(v) for k,v in (analysis.checkpoint.get("rebuild_inputs") or {}).items()}; await GitHubManagementService(client).dispatch_workflow(repository.full_name,workflow=workflow,ref=ref,inputs=inputs)
        import asyncio
        dispatched=datetime.now(UTC); success=False; observed=None
        for _ in range(120):
            await asyncio.sleep(10); runs=await client.list_workflow_runs(repository.full_name,limit=50)
            for run in runs:
                created=_dt(run.get("created_at")); name=str(run.get("name") or ""); path=str(run.get("path") or "")
                if created and created>=dispatched-timedelta(seconds=5) and (workflow in {name,path} or workflow in path):
                    observed=run
                    if run.get("status")=="completed": success=run.get("conclusion")=="success"; break
            if observed and observed.get("status")=="completed": break
        if not success: raise CleanupError("Rebuild canônico não concluiu com sucesso; GHCR cleanup bloqueado.")
    if required_package and required_tag:
        version=await GhcrService(client,connection.github_login).find_version_by_tag(repository.owner,required_package,required_tag)
        if not version: raise CleanupError(f"Imagem canônica {required_package}:{required_tag} não foi localizada; cleanup bloqueado.")
        return {"required":True,"status":"validated","package":required_package,"tag":required_tag,"version_id":version.get("id")}
    return {"required":bool(workflow),"status":"workflow_validated" if workflow else "preserved_by_rules"}

async def execute_cleanup(session:AsyncSession,*,user_id:uuid.UUID,analysis_id:uuid.UUID,confirmation:str,backup_snapshot_id:uuid.UUID|None=None)->CleanupAnalysis:
    analysis=await session.get(CleanupAnalysis,analysis_id)
    if not analysis or analysis.user_id!=user_id: raise CleanupError("Análise não encontrada.")
    expected=f"EXECUTAR {analysis.reference}"
    if confirmation!=expected: raise CleanupError(f"Confirmação inválida. Digite exatamente: {expected}")
    if analysis.status!=CleanupStatus.READY.value: raise CleanupError("Execute e aprove o Dry Run antes da limpeza.")
    repository=await session.get(Repository,analysis.repository_id); connection=await session.get(GitHubConnection,repository.connection_id) if repository else None
    if not repository or not connection or not connection.token_encrypted: raise CleanupError("Conexão/repositório indisponível.")
    candidates=(await session.execute(select(CleanupCandidate).where(CleanupCandidate.analysis_id==analysis.id,CleanupCandidate.selected.is_(True),CleanupCandidate.protected.is_(False)))).scalars().all(); destructive=[x for x in candidates if x.action_class==ActionClass.DESTRUCTIVE.value]
    if destructive and not backup_snapshot_id: raise CleanupError("Há ações DESTRUCTIVE selecionadas. Crie um backup concluído antes de executar.")
    token=EncryptionService().decrypt(connection.token_encrypted); client=GitHubClient(token,api_url=connection.api_url); management=GitHubManagementService(client); analysis.status=CleanupStatus.RUNNING.value; report={"reference":analysis.reference,"repository":repository.full_name,"started_at":datetime.now(UTC).isoformat(),"backup_snapshot_id":str(backup_snapshot_id) if backup_snapshot_id else None,"deleted":defaultdict(int),"failed":[],"preserved":analysis.checkpoint,"estimated_reclaimed_bytes":analysis.estimated_reclaimed_bytes}; await session.flush()
    try:
        checkpoint=await _resolve_checkpoint(client,repository,analysis.checkpoint)
        if checkpoint.get("sha")!=analysis.checkpoint.get("sha"): raise CleanupError("Checkpoint canônico mudou desde o Dry Run. Gere nova análise.")
        report["canonical"]=await _ensure_canonical(client,connection,repository,analysis,candidates); order={"artifact":1,"workflow_run":2,"release":3,"tag":4,"actions_cache":5,"ghcr_version":6,"branch":7}
        for item in sorted(candidates,key=lambda x:order.get(x.resource_type,99)):
            try:
                if item.resource_type=="artifact": await client.request("DELETE",f"/repos/{repository.full_name}/actions/artifacts/{item.resource_id}")
                elif item.resource_type=="workflow_run":
                    try: await client.request("POST",f"/repos/{repository.full_name}/actions/runs/{item.resource_id}/cancel")
                    except GitHubAPIError: pass
                    await client.request("DELETE",f"/repos/{repository.full_name}/actions/runs/{item.resource_id}")
                elif item.resource_type=="release": await client.request("DELETE",f"/repos/{repository.full_name}/releases/{item.resource_id}")
                elif item.resource_type=="tag": await client.request("DELETE",f"/repos/{repository.full_name}/git/refs/tags/{quote(item.resource_id or '',safe='')}")
                elif item.resource_type=="actions_cache": await client.request("DELETE",f"/repos/{repository.full_name}/actions/caches/{item.resource_id}")
                elif item.resource_type=="ghcr_version": await management.delete_package_version(owner=repository.owner,package_name=str(item.metadata.get("package_name") or ""),version_id=int(item.resource_id or 0),authenticated_login=connection.github_login)
                elif item.resource_type=="branch": await client.request("DELETE",f"/repos/{repository.full_name}/git/refs/heads/{quote(item.resource_id or '',safe='')}")
                report["deleted"][item.resource_type]+=1
            except Exception as exc: report["failed"].append({"candidate_id":str(item.id),"resource":item.resource_key,"error":str(exc)[:1000]})
        await _resolve_checkpoint(client,repository,analysis.checkpoint); report["deleted"]=dict(report["deleted"]); report["finished_at"]=datetime.now(UTC).isoformat(); report["space_reclaimed_estimate_bytes"]=sum(int(x.size_bytes or 0) for x in candidates if not any(f["candidate_id"]==str(x.id) for f in report["failed"])); analysis.result=report; analysis.status=CleanupStatus.COMPLETED_WITH_WARNINGS.value if report["failed"] else CleanupStatus.COMPLETED.value; analysis.completed_at=datetime.now(UTC); await session.flush(); return analysis
    except Exception as exc:
        analysis.status=CleanupStatus.FAILED.value; analysis.error=str(exc); analysis.completed_at=datetime.now(UTC); await session.flush(); raise
    finally: await client.close()
