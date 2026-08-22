from __future__ import annotations

import asyncio
import csv
import io
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.models.activity import AuditLog, SyncJobStatus
from app.models.github import Repository
from app.models.platform import (
    ActionClass,
    BackupPolicy,
    BackupSnapshot,
    BackupStatus,
    CleanupAnalysis,
    CleanupCandidate,
    CleanupProfile,
    ClinicAnalysis,
    ClinicFinding,
    DeploymentRecord,
    DeploymentTarget,
    PublishingChannel,
    StorageProvider,
)
from app.schemas.platform import (
    BackupPolicyCreate,
    BackupPolicyRead,
    BackupRunRequest,
    BackupSnapshotRead,
    CleanupAnalysisRead,
    CleanupAnalyzeRequest,
    CleanupCandidateRead,
    CleanupExecuteRequest,
    CleanupProfileCreate,
    CleanupProfileRead,
    CleanupSelectionRequest,
    ClinicAnalysisRead,
    ClinicFindingRead,
    ClinicRunRequest,
    DeployRequest,
    DeploymentRecordRead,
    DeploymentTargetCreate,
    DeploymentTargetRead,
    PublishingChannelCreate,
    PublishingChannelRead,
    ReleaseManagerRequest,
    ReplicationRequest,
    RestoreRequest,
    StorageProviderCreate,
    StorageProviderRead,
    StorageProviderTestResult,
    StorageProviderUpdate,
)
from app.services.audit import record_audit
from app.services.backup_service import apply_retention
from app.services.cleanup_service import set_cleanup_selection
from app.services.deployment_service import test_target
from app.services.job_queue import create_job
from app.services.restore_service import inspect_restore
from app.services.secret_store import SecretStore
from app.services.storage_providers import build_storage_adapter
from app.services.worker_status import require_worker
from app.tasks.platform import (
    backup_task,
    cleanup_analyze_task,
    cleanup_dry_run_task,
    cleanup_execute_task,
    clinic_task,
    deploy_task,
    release_task,
    replicate_task,
    restore_task,
    rollback_task,
)

router = APIRouter(prefix="/platform", tags=["Operations Platform"])


def _operation_allowed(user: CurrentUser, permission: str) -> bool:
    if user.is_superuser:
        return True
    permissions = (user.preferences or {}).get("permissions") or []
    return permission in permissions or "operations.*" in permissions


def _require_operation(user: CurrentUser, permission: str) -> None:
    if not _operation_allowed(user, permission):
        raise HTTPException(status_code=403, detail=f"Permissão necessária: {permission}")


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()[:64]
    return request.client.host[:64] if request.client else None


async def _repository(db: DbSession, repository_id: uuid.UUID, user_id: uuid.UUID) -> Repository:
    result = await db.execute(
        select(Repository).where(
            Repository.id == repository_id,
            Repository.connection.has(user_id=user_id),
        )
    )
    repository = result.scalar_one_or_none()
    if not repository:
        raise HTTPException(status_code=404, detail="Repositório não encontrado.")
    return repository


async def _queue_job(
    db: DbSession,
    *,
    current_user: CurrentUser,
    repository: Repository | None,
    kind: str,
    label: str,
    total: int,
    task: Any,
    params: dict[str, Any],
) -> dict[str, Any]:
    try:
        worker = await require_worker()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    job = await create_job(
        db,
        user_id=current_user.id,
        repository_id=repository.id if repository else None,
        connection_id=repository.connection_id if repository else None,
        kind=kind,
        label=label,
        progress_total=total,
        message="Worker confirmado; operação aguardando processamento.",
    )
    await db.commit()
    try:
        async_result = task.delay(str(job.id), params)
    except Exception as exc:
        job.status = SyncJobStatus.FAILED
        job.error = str(exc)[:4000]
        job.message = "Falha ao enviar operação ao worker."
        job.completed_at = datetime.now(UTC)
        await db.commit()
        raise HTTPException(status_code=503, detail=f"Falha ao enfileirar operação: {exc}") from exc
    job.celery_task_id = async_result.id
    await db.commit()
    return {"job_id": str(job.id), "celery_task_id": async_result.id, "workers": list(worker.workers), "status": "queued"}


@router.get("/storage-providers", response_model=list[StorageProviderRead])
async def list_storage_providers(current_user: CurrentUser, db: DbSession) -> list[StorageProvider]:
    return list((await db.execute(select(StorageProvider).where(StorageProvider.user_id == current_user.id).order_by(StorageProvider.name))).scalars().all())


@router.post("/storage-providers", response_model=StorageProviderRead)
async def create_storage_provider(payload: StorageProviderCreate, current_user: CurrentUser, db: DbSession, request: Request) -> StorageProvider:
    _require_operation(current_user, "backup.providers.manage")
    secret_store = SecretStore()
    provider = StorageProvider(user_id=current_user.id, name=payload.name, kind=payload.kind, config=payload.config, secret_encrypted=secret_store.encrypt_dict(payload.secret), secret_hint=secret_store.hint(payload.secret), enabled=payload.enabled)
    db.add(provider)
    await db.flush()
    await record_audit(db, action="storage_provider.created", user_id=current_user.id, entity_type="storage_provider", entity_id=str(provider.id), details={"name": provider.name, "kind": provider.kind, "secret_hint": provider.secret_hint}, ip_address=_client_ip(request))
    await db.commit()
    await db.refresh(provider)
    return provider


@router.patch("/storage-providers/{provider_id}", response_model=StorageProviderRead)
async def update_storage_provider(provider_id: uuid.UUID, payload: StorageProviderUpdate, current_user: CurrentUser, db: DbSession, request: Request) -> StorageProvider:
    _require_operation(current_user, "backup.providers.manage")
    provider = await db.get(StorageProvider, provider_id)
    if not provider or provider.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Provider não encontrado.")
    if payload.name is not None: provider.name = payload.name
    if payload.config is not None: provider.config = payload.config
    if payload.secret is not None:
        store = SecretStore(); provider.secret_encrypted = store.encrypt_dict(payload.secret); provider.secret_hint = store.hint(payload.secret)
    if payload.enabled is not None: provider.enabled = payload.enabled
    await record_audit(db, action="storage_provider.updated", user_id=current_user.id, entity_type="storage_provider", entity_id=str(provider.id), details={"name": provider.name, "kind": provider.kind, "secret_changed": payload.secret is not None}, ip_address=_client_ip(request))
    await db.commit(); await db.refresh(provider); return provider


@router.delete("/storage-providers/{provider_id}", status_code=204)
async def delete_storage_provider(provider_id: uuid.UUID, current_user: CurrentUser, db: DbSession, request: Request) -> Response:
    _require_operation(current_user, "backup.providers.manage")
    provider = await db.get(StorageProvider, provider_id)
    if not provider or provider.user_id != current_user.id: raise HTTPException(status_code=404, detail="Provider não encontrado.")
    usage = await db.scalar(select(func.count()).select_from(BackupPolicy).where(BackupPolicy.provider_id == provider.id))
    if usage: raise HTTPException(status_code=409, detail="Provider possui políticas de backup vinculadas; remova/reassocie as políticas primeiro.")
    await record_audit(db, action="storage_provider.deleted", user_id=current_user.id, entity_type="storage_provider", entity_id=str(provider.id), details={"name": provider.name, "kind": provider.kind}, ip_address=_client_ip(request)); await db.delete(provider); await db.commit(); return Response(status_code=204)


@router.post("/storage-providers/{provider_id}/test", response_model=StorageProviderTestResult)
async def test_storage_provider(provider_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> StorageProviderTestResult:
    provider = await db.get(StorageProvider, provider_id)
    if not provider or provider.user_id != current_user.id: raise HTTPException(status_code=404, detail="Provider não encontrado.")
    try:
        details = await asyncio.to_thread(build_storage_adapter(provider).test)
        return StorageProviderTestResult(ok=True, message="Provider validado com sucesso.", details=details)
    except Exception as exc:
        return StorageProviderTestResult(ok=False, message=str(exc), details={})


@router.get("/backup-policies", response_model=list[BackupPolicyRead])
async def list_backup_policies(current_user: CurrentUser, db: DbSession, repository_id: uuid.UUID | None = None) -> list[BackupPolicy]:
    query = select(BackupPolicy).where(BackupPolicy.user_id == current_user.id)
    if repository_id: query = query.where(BackupPolicy.repository_id == repository_id)
    return list((await db.execute(query.order_by(BackupPolicy.name))).scalars().all())


@router.post("/backup-policies", response_model=BackupPolicyRead)
async def create_backup_policy(payload: BackupPolicyCreate, current_user: CurrentUser, db: DbSession, request: Request) -> BackupPolicy:
    _require_operation(current_user, "backup.policy.manage")
    repository = await _repository(db, payload.repository_id, current_user.id)
    provider = await db.get(StorageProvider, payload.provider_id)
    if not provider or provider.user_id != current_user.id: raise HTTPException(status_code=404, detail="Provider não encontrado.")
    policy = BackupPolicy(user_id=current_user.id, **payload.model_dump())
    db.add(policy); await db.flush(); await record_audit(db, action="backup.policy.created", user_id=current_user.id, entity_type="backup_policy", entity_id=str(policy.id), details={"repository": repository.full_name, "provider": provider.name, "backup_type": policy.backup_type, "schedule_kind": policy.schedule_kind}, ip_address=_client_ip(request)); await db.commit(); await db.refresh(policy); return policy


@router.post("/backup-policies/{policy_id}/run")
async def run_backup_policy(policy_id: uuid.UUID, current_user: CurrentUser, db: DbSession, request: Request) -> dict[str, Any]:
    _require_operation(current_user, "backup.execute")
    policy = await db.get(BackupPolicy, policy_id)
    if not policy or policy.user_id != current_user.id: raise HTTPException(status_code=404, detail="Política não encontrada.")
    repository = await _repository(db, policy.repository_id, current_user.id)
    queued = await _queue_job(db, current_user=current_user, repository=repository, kind="repository.backup", label=f"Backup · {repository.full_name} · {policy.name}", total=5, task=backup_task, params={"user_id": str(current_user.id), "policy_id": str(policy.id)})
    await record_audit(db, action="backup.queued", user_id=current_user.id, entity_type="backup_policy", entity_id=str(policy.id), details={"repository": repository.full_name, "job_id": queued["job_id"]}, ip_address=_client_ip(request)); await db.commit(); return queued


@router.post("/backups/run")
async def run_backup(payload: BackupRunRequest, current_user: CurrentUser, db: DbSession, request: Request) -> dict[str, Any]:
    _require_operation(current_user, "backup.execute")
    if not payload.repository_id or not payload.provider_id or not payload.backup_type: raise HTTPException(status_code=422, detail="repository_id, provider_id e backup_type são obrigatórios no backup manual.")
    repository = await _repository(db, payload.repository_id, current_user.id); provider = await db.get(StorageProvider, payload.provider_id)
    if not provider or provider.user_id != current_user.id: raise HTTPException(status_code=404, detail="Provider não encontrado.")
    queued = await _queue_job(db, current_user=current_user, repository=repository, kind="repository.backup.manual", label=f"Backup manual · {repository.full_name}", total=5, task=backup_task, params={"user_id":str(current_user.id),"repository_id":str(repository.id),"provider_id":str(provider.id),"backup_type":payload.backup_type,"branches":payload.branches,"permanent":payload.permanent})
    await record_audit(db, action="backup.manual_queued", user_id=current_user.id, entity_type="repository", entity_id=str(repository.id), details={"provider": provider.name, "backup_type": payload.backup_type, "job_id": queued["job_id"]}, ip_address=_client_ip(request)); await db.commit(); return queued


@router.get("/backups", response_model=list[BackupSnapshotRead])
async def list_backups(current_user: CurrentUser, db: DbSession, repository_id: uuid.UUID | None = None, limit: int = Query(default=100, ge=1, le=500)) -> list[BackupSnapshot]:
    query = select(BackupSnapshot).where(BackupSnapshot.user_id == current_user.id)
    if repository_id: query = query.where(BackupSnapshot.repository_id == repository_id)
    return list((await db.execute(query.order_by(BackupSnapshot.created_at.desc()).limit(limit))).scalars().all())


@router.post("/backup-policies/{policy_id}/apply-retention")
async def apply_policy_retention(policy_id: uuid.UUID, current_user: CurrentUser, db: DbSession, request: Request) -> dict[str, int]:
    _require_operation(current_user, "backup.policy.manage")
    policy = await db.get(BackupPolicy, policy_id)
    if not policy or policy.user_id != current_user.id: raise HTTPException(status_code=404, detail="Política não encontrada.")
    result = await apply_retention(db, policy); await record_audit(db, action="backup.retention_applied", user_id=current_user.id, entity_type="backup_policy", entity_id=str(policy.id), details=result, ip_address=_client_ip(request)); await db.commit(); return result


@router.get("/backups/{snapshot_id}/restore-preview")
async def restore_preview(snapshot_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> dict[str, Any]:
    snapshot = await db.get(BackupSnapshot, snapshot_id)
    if not snapshot or snapshot.user_id != current_user.id: raise HTTPException(status_code=404, detail="Backup não encontrado.")
    return await inspect_restore(db, snapshot_id=snapshot_id)


@router.post("/backups/{snapshot_id}/restore")
async def queue_restore(snapshot_id: uuid.UUID, payload: RestoreRequest, current_user: CurrentUser, db: DbSession, request: Request) -> dict[str, Any]:
    _require_operation(current_user, "backup.restore")
    snapshot = await db.get(BackupSnapshot, snapshot_id)
    if not snapshot or snapshot.user_id != current_user.id: raise HTTPException(status_code=404, detail="Backup não encontrado.")
    repository = await _repository(db, snapshot.repository_id, current_user.id)
    if payload.simulate:
        return await inspect_restore(db, snapshot_id=snapshot_id)
    queued = await _queue_job(db, current_user=current_user, repository=repository, kind="repository.restore", label=f"Restore · {repository.full_name}", total=4, task=restore_task, params={"user_id":str(current_user.id),"snapshot_id":str(snapshot.id),**payload.model_dump(mode="json")})
    await record_audit(db, action="restore.queued", user_id=current_user.id, entity_type="backup_snapshot", entity_id=str(snapshot.id), details={"repository":repository.full_name,"destination":payload.destination,"job_id":queued["job_id"]}, ip_address=_client_ip(request)); await db.commit(); return queued


@router.get("/publishing-channels", response_model=list[PublishingChannelRead])
async def list_publishing_channels(current_user: CurrentUser, db: DbSession) -> list[PublishingChannel]:
    return list((await db.execute(select(PublishingChannel).where(PublishingChannel.user_id == current_user.id).order_by(PublishingChannel.name))).scalars().all())


@router.post("/publishing-channels", response_model=PublishingChannelRead)
async def create_publishing_channel(payload: PublishingChannelCreate, current_user: CurrentUser, db: DbSession, request: Request) -> PublishingChannel:
    _require_operation(current_user, "release.channels.manage")
    store=SecretStore(); data=payload.model_dump(exclude={"secret"}); channel=PublishingChannel(user_id=current_user.id,secret_encrypted=store.encrypt_dict(payload.secret),**data); db.add(channel); await db.flush(); await record_audit(db,action="publishing_channel.created",user_id=current_user.id,entity_type="publishing_channel",entity_id=str(channel.id),details={"name":channel.name,"kind":channel.kind},ip_address=_client_ip(request)); await db.commit(); await db.refresh(channel); return channel


@router.post("/releases")
async def queue_release(payload: ReleaseManagerRequest, current_user: CurrentUser, db: DbSession, request: Request) -> dict[str, Any]:
    _require_operation(current_user, "release.publish")
    repository=await _repository(db,payload.repository_id,current_user.id); params={**payload.model_dump(mode="json"),"user_id":str(current_user.id)}; queued=await _queue_job(db,current_user=current_user,repository=repository,kind="release.publish",label=f"Release {payload.tag_name} · {repository.full_name}",total=4,task=release_task,params=params); await record_audit(db,action="release.queued",user_id=current_user.id,entity_type="repository",entity_id=str(repository.id),details={"tag":payload.tag_name,"channels":[str(x) for x in payload.channel_ids],"job_id":queued["job_id"]},ip_address=_client_ip(request)); await db.commit(); return queued


@router.post("/replications")
async def queue_replication(payload: ReplicationRequest, current_user: CurrentUser, db: DbSession, request: Request) -> dict[str, Any]:
    _require_operation(current_user,"repository.replicate"); repository=await _repository(db,payload.repository_id,current_user.id); queued=await _queue_job(db,current_user=current_user,repository=repository,kind="repository.replicate",label=f"Replicação · {repository.full_name}",total=3,task=replicate_task,params={**payload.model_dump(mode="json"),"user_id":str(current_user.id)}); await record_audit(db,action="repository.replication_queued",user_id=current_user.id,entity_type="repository",entity_id=str(repository.id),details={"mode":payload.mode,"destination_kind":payload.destination_kind,"job_id":queued["job_id"]},ip_address=_client_ip(request)); await db.commit(); return queued


@router.get("/deployment-targets", response_model=list[DeploymentTargetRead])
async def list_deployment_targets(current_user: CurrentUser, db: DbSession) -> list[DeploymentTarget]:
    return list((await db.execute(select(DeploymentTarget).where(DeploymentTarget.user_id==current_user.id).order_by(DeploymentTarget.environment,DeploymentTarget.name))).scalars().all())


@router.post("/deployment-targets", response_model=DeploymentTargetRead)
async def create_deployment_target(payload: DeploymentTargetCreate,current_user:CurrentUser,db:DbSession,request:Request)->DeploymentTarget:
    _require_operation(current_user,"deploy.targets.manage")
    if payload.repository_id: await _repository(db,payload.repository_id,current_user.id)
    store=SecretStore(); data=payload.model_dump(exclude={"secret"}); target=DeploymentTarget(user_id=current_user.id,secret_encrypted=store.encrypt_dict(payload.secret),**data); db.add(target); await db.flush(); await record_audit(db,action="deployment_target.created",user_id=current_user.id,entity_type="deployment_target",entity_id=str(target.id),details={"name":target.name,"environment":target.environment,"strategy":target.strategy,"host":target.host},ip_address=_client_ip(request)); await db.commit(); await db.refresh(target); return target


@router.post("/deployment-targets/{target_id}/test")
async def test_deployment_target(target_id:uuid.UUID,current_user:CurrentUser,db:DbSession)->dict[str,Any]:
    target=await db.get(DeploymentTarget,target_id)
    if not target or target.user_id!=current_user.id: raise HTTPException(status_code=404,detail="Target não encontrado.")
    try: return await asyncio.to_thread(lambda: asyncio.run(test_target(target)))
    except Exception as exc: return {"ok":False,"message":str(exc),"details":{}}


@router.post("/deployment-targets/{target_id}/deploy")
async def queue_deploy(target_id:uuid.UUID,payload:DeployRequest,current_user:CurrentUser,db:DbSession,request:Request)->dict[str,Any]:
    _require_operation(current_user,"deploy.execute"); target=await db.get(DeploymentTarget,target_id)
    if not target or target.user_id!=current_user.id: raise HTTPException(status_code=404,detail="Target não encontrado.")
    repository=await _repository(db,payload.repository_id,current_user.id); expected=f"DEPLOY {target.name} {payload.ref}"
    if payload.confirmation!=expected: raise HTTPException(status_code=400,detail=f"Digite exatamente: {expected}")
    queued=await _queue_job(db,current_user=current_user,repository=repository,kind="deployment.execute",label=f"Deploy {target.environment} · {repository.full_name} · {payload.ref}",total=7,task=deploy_task,params={**payload.model_dump(mode="json"),"user_id":str(current_user.id),"target_id":str(target.id)}); await record_audit(db,action="deployment.queued",user_id=current_user.id,entity_type="deployment_target",entity_id=str(target.id),details={"repository":repository.full_name,"ref":payload.ref,"job_id":queued["job_id"]},ip_address=_client_ip(request)); await db.commit(); return queued


@router.get("/deployments", response_model=list[DeploymentRecordRead])
async def list_deployments(current_user:CurrentUser,db:DbSession,limit:int=Query(default=100,ge=1,le=500))->list[DeploymentRecord]:
    return list((await db.execute(select(DeploymentRecord).where(DeploymentRecord.user_id==current_user.id).order_by(DeploymentRecord.created_at.desc()).limit(limit))).scalars().all())


@router.post("/deployments/{deployment_id}/rollback")
async def queue_rollback(deployment_id:uuid.UUID,payload:dict[str,str],current_user:CurrentUser,db:DbSession,request:Request)->dict[str,Any]:
    _require_operation(current_user,"deploy.rollback"); record=await db.get(DeploymentRecord,deployment_id)
    if not record or record.user_id!=current_user.id: raise HTTPException(status_code=404,detail="Deployment não encontrado.")
    repository=await _repository(db,record.repository_id,current_user.id) if record.repository_id else None; confirmation=str(payload.get("confirmation") or ""); expected=f"ROLLBACK {record.id}"
    if confirmation!=expected: raise HTTPException(status_code=400,detail=f"Digite exatamente: {expected}")
    queued=await _queue_job(db,current_user=current_user,repository=repository,kind="deployment.rollback",label=f"Rollback · {record.id}",total=3,task=rollback_task,params={"user_id":str(current_user.id),"deployment_id":str(record.id),"confirmation":confirmation}); await record_audit(db,action="deployment.rollback_queued",user_id=current_user.id,entity_type="deployment_record",entity_id=str(record.id),details={"job_id":queued["job_id"]},ip_address=_client_ip(request)); await db.commit(); return queued


@router.post("/clinic/analyze")
async def queue_clinic(payload:ClinicRunRequest,current_user:CurrentUser,db:DbSession)->dict[str,Any]:
    repository=await _repository(db,payload.repository_id,current_user.id); return await _queue_job(db,current_user=current_user,repository=repository,kind="repository.clinic",label=f"Clínica · {repository.full_name}",total=6,task=clinic_task,params={**payload.model_dump(mode="json"),"user_id":str(current_user.id)})


async def _clinic_payload(db:DbSession,analysis:ClinicAnalysis)->ClinicAnalysisRead:
    findings=list((await db.execute(select(ClinicFinding).where(ClinicFinding.analysis_id==analysis.id).order_by(ClinicFinding.severity.desc()))).scalars().all()); payload=ClinicAnalysisRead.model_validate(analysis); payload.findings=[ClinicFindingRead.model_validate(x) for x in findings]; return payload


@router.get("/clinic", response_model=list[ClinicAnalysisRead])
async def list_clinic(current_user:CurrentUser,db:DbSession,repository_id:uuid.UUID|None=None,limit:int=Query(default=30,ge=1,le=100))->list[ClinicAnalysisRead]:
    query=select(ClinicAnalysis).where(ClinicAnalysis.user_id==current_user.id)
    if repository_id: query=query.where(ClinicAnalysis.repository_id==repository_id)
    analyses=list((await db.execute(query.order_by(ClinicAnalysis.created_at.desc()).limit(limit))).scalars().all()); return [await _clinic_payload(db,x) for x in analyses]


@router.get("/clinic/{analysis_id}",response_model=ClinicAnalysisRead)
async def get_clinic(analysis_id:uuid.UUID,current_user:CurrentUser,db:DbSession)->ClinicAnalysisRead:
    analysis=await db.get(ClinicAnalysis,analysis_id)
    if not analysis or analysis.user_id!=current_user.id: raise HTTPException(status_code=404,detail="Análise não encontrada.")
    return await _clinic_payload(db,analysis)


@router.get("/cleanup/profiles",response_model=list[CleanupProfileRead])
async def list_cleanup_profiles(current_user:CurrentUser,db:DbSession,repository_id:uuid.UUID|None=None)->list[CleanupProfile]:
    query=select(CleanupProfile).where(CleanupProfile.user_id==current_user.id)
    if repository_id: query=query.where(CleanupProfile.repository_id==repository_id)
    return list((await db.execute(query.order_by(CleanupProfile.name))).scalars().all())


@router.post("/cleanup/profiles",response_model=CleanupProfileRead)
async def create_cleanup_profile(payload:CleanupProfileCreate,current_user:CurrentUser,db:DbSession,request:Request)->CleanupProfile:
    _require_operation(current_user,"cleanup.profile.manage"); repository=await _repository(db,payload.repository_id,current_user.id); profile=CleanupProfile(user_id=current_user.id,**payload.model_dump()); db.add(profile); await db.flush(); await record_audit(db,action="cleanup.profile.created",user_id=current_user.id,entity_type="cleanup_profile",entity_id=str(profile.id),details={"repository":repository.full_name,"name":profile.name},ip_address=_client_ip(request)); await db.commit(); await db.refresh(profile); return profile


@router.post("/cleanup/analyze")
async def queue_cleanup_analysis(payload:CleanupAnalyzeRequest,current_user:CurrentUser,db:DbSession)->dict[str,Any]:
    repository=await _repository(db,payload.repository_id,current_user.id); return await _queue_job(db,current_user=current_user,repository=repository,kind="repository.cleanup.analyze",label=f"Cleanup Analyze · {repository.full_name}",total=5,task=cleanup_analyze_task,params={**payload.model_dump(mode="json"),"user_id":str(current_user.id)})


async def _cleanup_payload(db:DbSession,analysis:CleanupAnalysis)->CleanupAnalysisRead:
    candidates=list((await db.execute(select(CleanupCandidate).where(CleanupCandidate.analysis_id==analysis.id).order_by(CleanupCandidate.resource_type,CleanupCandidate.resource_key))).scalars().all()); payload=CleanupAnalysisRead.model_validate(analysis); payload.candidates=[CleanupCandidateRead.model_validate(x) for x in candidates]; return payload


@router.get("/cleanup",response_model=list[CleanupAnalysisRead])
async def list_cleanup(current_user:CurrentUser,db:DbSession,repository_id:uuid.UUID|None=None,limit:int=Query(default=30,ge=1,le=100))->list[CleanupAnalysisRead]:
    query=select(CleanupAnalysis).where(CleanupAnalysis.user_id==current_user.id)
    if repository_id: query=query.where(CleanupAnalysis.repository_id==repository_id)
    analyses=list((await db.execute(query.order_by(CleanupAnalysis.created_at.desc()).limit(limit))).scalars().all()); return [await _cleanup_payload(db,x) for x in analyses]


@router.get("/cleanup/{analysis_id}",response_model=CleanupAnalysisRead)
async def get_cleanup(analysis_id:uuid.UUID,current_user:CurrentUser,db:DbSession)->CleanupAnalysisRead:
    analysis=await db.get(CleanupAnalysis,analysis_id)
    if not analysis or analysis.user_id!=current_user.id: raise HTTPException(status_code=404,detail="Análise não encontrada.")
    return await _cleanup_payload(db,analysis)


@router.put("/cleanup/{analysis_id}/selection",response_model=CleanupAnalysisRead)
async def cleanup_selection(analysis_id:uuid.UUID,payload:CleanupSelectionRequest,current_user:CurrentUser,db:DbSession)->CleanupAnalysisRead:
    analysis=await set_cleanup_selection(db,user_id=current_user.id,analysis_id=analysis_id,candidate_ids=payload.candidate_ids); await db.commit(); return await _cleanup_payload(db,analysis)


@router.post("/cleanup/{analysis_id}/dry-run")
async def queue_cleanup_dry_run(analysis_id:uuid.UUID,current_user:CurrentUser,db:DbSession)->dict[str,Any]:
    analysis=await db.get(CleanupAnalysis,analysis_id)
    if not analysis or analysis.user_id!=current_user.id: raise HTTPException(status_code=404,detail="Análise não encontrada.")
    repository=await _repository(db,analysis.repository_id,current_user.id); return await _queue_job(db,current_user=current_user,repository=repository,kind="repository.cleanup.dry_run",label=f"Dry Run · {analysis.reference}",total=4,task=cleanup_dry_run_task,params={"user_id":str(current_user.id),"analysis_id":str(analysis.id)})


@router.post("/cleanup/{analysis_id}/execute")
async def queue_cleanup_execute(analysis_id:uuid.UUID,payload:CleanupExecuteRequest,current_user:CurrentUser,db:DbSession,request:Request)->dict[str,Any]:
    _require_operation(current_user,"cleanup.execute"); analysis=await db.get(CleanupAnalysis,analysis_id)
    if not analysis or analysis.user_id!=current_user.id: raise HTTPException(status_code=404,detail="Análise não encontrada.")
    repository=await _repository(db,analysis.repository_id,current_user.id); selected=list((await db.execute(select(CleanupCandidate).where(CleanupCandidate.analysis_id==analysis.id,CleanupCandidate.selected.is_(True),CleanupCandidate.protected.is_(False)))).scalars().all()); destructive=any(x.action_class==ActionClass.DESTRUCTIVE.value for x in selected); backup_snapshot_id=None
    if destructive:
        if not payload.create_backup: raise HTTPException(status_code=409,detail="Ações DESTRUCTIVE exigem backup prévio; create_backup=false foi recusado.")
        snapshot=(await db.execute(select(BackupSnapshot).where(BackupSnapshot.repository_id==repository.id,BackupSnapshot.status.in_([BackupStatus.COMPLETED.value,BackupStatus.COMPLETED_WITH_WARNINGS.value])).order_by(BackupSnapshot.created_at.desc()).limit(1))).scalar_one_or_none()
        if not snapshot: raise HTTPException(status_code=409,detail="Nenhum backup concluído existe para este repositório. Execute Backup Now e repita o Dry Run antes da limpeza destrutiva.")
        backup_snapshot_id=str(snapshot.id)
    queued=await _queue_job(db,current_user=current_user,repository=repository,kind="repository.cleanup.execute",label=f"Cleanup Execute · {analysis.reference}",total=12,task=cleanup_execute_task,params={"user_id":str(current_user.id),"analysis_id":str(analysis.id),"confirmation":payload.confirmation,"backup_snapshot_id":backup_snapshot_id}); await record_audit(db,action="cleanup.execution_queued",user_id=current_user.id,entity_type="cleanup_analysis",entity_id=str(analysis.id),details={"reference":analysis.reference,"selected":len(selected),"destructive":destructive,"backup_snapshot_id":backup_snapshot_id,"job_id":queued["job_id"]},ip_address=_client_ip(request)); await db.commit(); return queued


@router.get("/cleanup/{analysis_id}/report.json")
async def cleanup_report(analysis_id:uuid.UUID,current_user:CurrentUser,db:DbSession)->Response:
    analysis=await db.get(CleanupAnalysis,analysis_id)
    if not analysis or analysis.user_id!=current_user.id: raise HTTPException(status_code=404,detail="Análise não encontrada.")
    payload=(await _cleanup_payload(db,analysis)).model_dump(mode="json"); return Response(content=json.dumps(payload,ensure_ascii=False,indent=2),media_type="application/json",headers={"Content-Disposition":f'attachment; filename="{analysis.reference}.json"'})


@router.get("/audit")
async def list_audit(current_user:CurrentUser,db:DbSession,limit:int=Query(default=200,ge=1,le=1000),operation_prefix:str|None=None)->list[dict[str,Any]]:
    query=select(AuditLog).where(AuditLog.user_id==current_user.id)
    if operation_prefix: query=query.where(AuditLog.action.startswith(operation_prefix))
    rows=(await db.execute(query.order_by(AuditLog.created_at.desc()).limit(limit))).scalars().all(); return [{"id":str(x.id),"user_id":str(x.user_id) if x.user_id else None,"action":x.action,"entity_type":x.entity_type,"entity_id":x.entity_id,"details":x.details,"ip_address":x.ip_address,"created_at":x.created_at.isoformat()} for x in rows]


@router.get("/audit.csv")
async def export_audit(current_user:CurrentUser,db:DbSession,limit:int=Query(default=1000,ge=1,le=10000))->Response:
    rows=(await db.execute(select(AuditLog).where(AuditLog.user_id==current_user.id).order_by(AuditLog.created_at.desc()).limit(limit))).scalars().all(); output=io.StringIO(); writer=csv.writer(output); writer.writerow(["id","user_id","created_at","action","entity_type","entity_id","ip_address","details_json"])
    for x in rows: writer.writerow([str(x.id),str(x.user_id or ""),x.created_at.isoformat(),x.action,x.entity_type or "",x.entity_id or "",x.ip_address or "",json.dumps(x.details or {},ensure_ascii=False,separators=(",",":"))])
    return Response(content=output.getvalue(),media_type="text/csv; charset=utf-8",headers={"Content-Disposition":'attachment; filename="argws-git-monitor-audit.csv"'})


@router.get("/dashboard")
async def operations_dashboard(current_user:CurrentUser,db:DbSession)->dict[str,Any]:
    repositories=await db.scalar(select(func.count()).select_from(Repository).where(Repository.connection.has(user_id=current_user.id))) or 0
    backups_success=await db.scalar(select(func.count()).select_from(BackupSnapshot).where(BackupSnapshot.user_id==current_user.id,BackupSnapshot.status.in_([BackupStatus.COMPLETED.value,BackupStatus.COMPLETED_WITH_WARNINGS.value]))) or 0
    backups_failed=await db.scalar(select(func.count()).select_from(BackupSnapshot).where(BackupSnapshot.user_id==current_user.id,BackupSnapshot.status==BackupStatus.FAILED.value)) or 0
    storage=await db.scalar(select(func.coalesce(func.sum(BackupSnapshot.size_bytes),0)).where(BackupSnapshot.user_id==current_user.id)) or 0
    deployments_pending=await db.scalar(select(func.count()).select_from(DeploymentRecord).where(DeploymentRecord.user_id==current_user.id,DeploymentRecord.status.in_(["queued","running","validating"]))) or 0
    deployments_failed=await db.scalar(select(func.count()).select_from(DeploymentRecord).where(DeploymentRecord.user_id==current_user.id,DeploymentRecord.status=="failed")) or 0
    critical=await db.scalar(select(func.count()).select_from(ClinicFinding).join(ClinicAnalysis,ClinicFinding.analysis_id==ClinicAnalysis.id).where(ClinicAnalysis.user_id==current_user.id,ClinicFinding.severity=="critical")) or 0
    latest_backup=(await db.execute(select(BackupSnapshot).where(BackupSnapshot.user_id==current_user.id).order_by(BackupSnapshot.created_at.desc()).limit(5))).scalars().all(); latest_deploy=(await db.execute(select(DeploymentRecord).where(DeploymentRecord.user_id==current_user.id).order_by(DeploymentRecord.created_at.desc()).limit(5))).scalars().all()
    return {"repositories_monitored":repositories,"backups_successful":backups_success,"backups_failed":backups_failed,"storage_consumption_bytes":int(storage),"pending_deployments":deployments_pending,"failed_deployments":deployments_failed,"critical_recommendations":critical,"latest_backups":[{"id":str(x.id),"repository_id":str(x.repository_id),"status":x.status,"size_bytes":x.size_bytes,"created_at":x.created_at.isoformat()} for x in latest_backup],"latest_deployments":[{"id":str(x.id),"repository_id":str(x.repository_id) if x.repository_id else None,"target_id":str(x.target_id),"status":x.status,"ref":x.requested_ref,"created_at":x.created_at.isoformat()} for x in latest_deploy]}
