from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.core.database import dispose_engine, session_scope
from app.models.activity import SyncJob
from app.models.platform import (
    BackupPolicy,
    BackupSnapshot,
    CleanupAnalysis,
    DeploymentRecord,
)
from app.services.backup_service import apply_retention, create_backup
from app.services.cleanup_service import (
    build_cleanup_analysis,
    dry_run_cleanup,
    execute_cleanup,
)
from app.services.clinic_service import analyze_repository
from app.services.deployment_service import deploy, rollback
from app.services.job_queue import (
    create_job,
    mark_job_failed,
    mark_job_running,
    mark_job_success,
    update_job_progress,
)
from app.services.release_manager import create_release
from app.services.replication_service import replicate_repository
from app.services.restore_service import restore_snapshot
from app.tasks.celery_app import celery_app


def run_async(coro):
    async def runner():
        try:
            return await coro
        finally:
            await dispose_engine()

    return asyncio.run(runner())


async def _fail(job_id: str, exc: Exception) -> None:
    await mark_job_failed(job_id, error=str(exc))


@celery_app.task(name="platform.backup", bind=True, max_retries=2)
def backup_task(self, job_id: str, params: dict[str, Any]):
    async def execute():
        await mark_job_running(job_id, message="Preparando backup Git e manifesto.")
        await update_job_progress(job_id, current=1, total=5, message="Validando repositório e provider.")
        async with session_scope() as session:
            policy_id = uuid.UUID(params["policy_id"]) if params.get("policy_id") else None
            policy = await session.get(BackupPolicy, policy_id) if policy_id else None
            resolved = {
                "user_id": uuid.UUID(params["user_id"]),
                "repository_id": uuid.UUID(params.get("repository_id") or str(policy.repository_id)),
                "provider_id": uuid.UUID(params.get("provider_id") or str(policy.provider_id)),
                "backup_type": params.get("backup_type") or policy.backup_type,
                "branches": params.get("branches") or (policy.branches if policy else []),
                "include_releases": params.get("include_releases", policy.include_releases if policy else True),
                "include_release_assets": params.get("include_release_assets", policy.include_release_assets if policy else True),
                "include_lfs": params.get("include_lfs", policy.include_lfs if policy else True),
                "include_submodules": params.get("include_submodules", policy.include_submodules if policy else True),
                "permanent": bool(params.get("permanent", False)),
                "policy_id": policy_id,
                "job_id": uuid.UUID(job_id),
            }
            await update_job_progress(job_id, current=2, total=5, message="Criando mirror/bundle e coletando releases/assets.")
            snapshot = await create_backup(session, **resolved)
            await update_job_progress(job_id, current=4, total=5, message="Backup enviado; aplicando retenção com preservações.")
            retention = await apply_retention(session, policy) if policy else {"deleted": 0}
            result = {
                "snapshot_id": str(snapshot.id),
                "status": snapshot.status,
                "location": snapshot.location,
                "checksum_sha256": snapshot.checksum_sha256,
                "size_bytes": snapshot.size_bytes,
                "object_count": snapshot.object_count,
                "retention": retention,
            }
        await update_job_progress(job_id, current=5, total=5, message="Backup validado e concluído.")
        await mark_job_success(job_id, result=result, message="Backup concluído com integridade SHA-256 validada.")
        return result

    try:
        return run_async(execute())
    except Exception as exc:
        run_async(_fail(job_id, exc))
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=min(60 * (self.request.retries + 1), 180))
        raise


@celery_app.task(name="platform.restore", bind=True, max_retries=1)
def restore_task(self, job_id: str, params: dict[str, Any]):
    async def execute():
        await mark_job_running(job_id, message="Baixando backup e validando checksum.")
        await update_job_progress(job_id, current=1, total=4, message="Validando snapshot e destino.")
        async with session_scope() as session:
            await update_job_progress(job_id, current=2, total=4, message="Restaurando referências/arquivos conforme o plano aprovado.")
            result = await restore_snapshot(
                session,
                user_id=uuid.UUID(params["user_id"]),
                snapshot_id=uuid.UUID(params["snapshot_id"]),
                destination=params["destination"],
                connection_id=uuid.UUID(params["connection_id"]) if params.get("connection_id") else None,
                repository_full_name=params.get("repository_full_name"),
                new_repository_name=params.get("new_repository_name"),
                branch=params.get("branch"),
                restore_tags=bool(params.get("restore_tags", True)),
                restore_releases=bool(params.get("restore_releases", True)),
                target_path=params.get("target_path"),
                simulate=bool(params.get("simulate", False)),
                confirmation=params.get("confirmation"),
            )
        await update_job_progress(job_id, current=4, total=4, message="Restauração concluída.")
        await mark_job_success(job_id, result=result, message="Restauração executada e validada.")
        return result

    try:
        return run_async(execute())
    except Exception as exc:
        run_async(_fail(job_id, exc))
        raise


@celery_app.task(name="platform.replicate", bind=True, max_retries=2)
def replicate_task(self, job_id: str, params: dict[str, Any]):
    async def execute():
        await mark_job_running(job_id, message="Validando origem, destino e proteção contra loops.")
        await update_job_progress(job_id, current=1, total=3)
        async with session_scope() as session:
            result = await replicate_repository(
                session,
                user_id=uuid.UUID(params["user_id"]),
                repository_id=uuid.UUID(params["repository_id"]),
                mode=params["mode"],
                destination_kind=params["destination_kind"],
                destination_connection_id=uuid.UUID(params["destination_connection_id"]) if params.get("destination_connection_id") else None,
                destination_repository=params.get("destination_repository"),
                provider_id=uuid.UUID(params["provider_id"]) if params.get("provider_id") else None,
                branch=params.get("branch"),
                release_tag=params.get("release_tag"),
                overwrite=bool(params.get("overwrite", False)),
            )
        await update_job_progress(job_id, current=3, total=3, message="Replicação concluída.")
        await mark_job_success(job_id, result=result, message="Replicação concluída.")
        return result

    try:
        return run_async(execute())
    except Exception as exc:
        run_async(_fail(job_id, exc))
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=60)
        raise


@celery_app.task(name="platform.release", bind=True, max_retries=1)
def release_task(self, job_id: str, params: dict[str, Any]):
    async def execute():
        await mark_job_running(job_id, message="Criando tag/release e preparando canais de publicação.")
        await update_job_progress(job_id, current=1, total=4)
        async with session_scope() as session:
            result = await create_release(
                session,
                user_id=uuid.UUID(params["user_id"]),
                repository_id=uuid.UUID(params["repository_id"]),
                tag_name=params["tag_name"],
                target_commitish=params["target_commitish"],
                name=params.get("name"),
                body=params.get("body"),
                draft=bool(params.get("draft", False)),
                prerelease=bool(params.get("prerelease", False)),
                make_latest=bool(params.get("make_latest", True)),
                create_tag=bool(params.get("create_tag", True)),
                assets=list(params.get("assets") or []),
                channel_ids=[uuid.UUID(value) for value in params.get("channel_ids") or []],
            )
        await update_job_progress(job_id, current=4, total=4, message="Release publicada nos canais configurados.")
        await mark_job_success(job_id, result=result, message=f"Release {params['tag_name']} publicada.")
        return result

    try:
        return run_async(execute())
    except Exception as exc:
        run_async(_fail(job_id, exc))
        raise


@celery_app.task(name="platform.deploy", bind=True, max_retries=0)
def deploy_task(self, job_id: str, params: dict[str, Any]):
    async def execute():
        await mark_job_running(job_id, message="Executando pipeline remoto de deployment.")
        await update_job_progress(job_id, current=1, total=7, message="Conectando ao target e capturando estado atual.")
        async with session_scope() as session:
            record = await deploy(
                session,
                user_id=uuid.UUID(params["user_id"]),
                target_id=uuid.UUID(params["target_id"]),
                repository_id=uuid.UUID(params["repository_id"]),
                ref=params["ref"],
                release_url=params.get("release_url"),
                checksum_sha256=params.get("checksum_sha256"),
                job_id=uuid.UUID(job_id),
            )
            result = {
                "deployment_id": str(record.id),
                "status": record.status,
                "pipeline": record.pipeline,
                "health_result": record.health_result,
                "previous_version": record.previous_version,
                "deployed_version": record.deployed_version,
            }
        await update_job_progress(job_id, current=7, total=7, message="Deployment finalizado; healthcheck registrado.")
        await mark_job_success(job_id, result=result, message=f"Deployment finalizado com status {record.status}.")
        return result

    try:
        return run_async(execute())
    except Exception as exc:
        run_async(_fail(job_id, exc))
        raise


@celery_app.task(name="platform.rollback", bind=True, max_retries=0)
def rollback_task(self, job_id: str, params: dict[str, Any]):
    async def execute():
        await mark_job_running(job_id, message="Executando rollback aprovado.")
        async with session_scope() as session:
            record = await rollback(
                session,
                user_id=uuid.UUID(params["user_id"]),
                deployment_id=uuid.UUID(params["deployment_id"]),
                confirmation=params["confirmation"],
            )
            result = {"deployment_id": str(record.id), "status": record.status, "health_result": record.health_result}
        await mark_job_success(job_id, result=result, message="Rollback concluído e healthcheck registrado.")
        return result

    try:
        return run_async(execute())
    except Exception as exc:
        run_async(_fail(job_id, exc))
        raise


@celery_app.task(name="platform.clinic", bind=True, max_retries=1)
def clinic_task(self, job_id: str, params: dict[str, Any]):
    async def execute():
        await mark_job_running(job_id, message="Coletando evidências Git, Releases, Actions, GHCR e configuração.")
        await update_job_progress(job_id, current=1, total=6)
        async with session_scope() as session:
            analysis = await analyze_repository(
                session,
                user_id=uuid.UUID(params["user_id"]),
                repository_id=uuid.UUID(params["repository_id"]),
                job_id=uuid.UUID(job_id),
                include_deep_git=bool(params.get("include_deep_git", True)),
                include_actions=bool(params.get("include_actions", True)),
                include_ghcr=bool(params.get("include_ghcr", True)),
            )
            result = {"analysis_id": str(analysis.id), "score": analysis.score, "score_breakdown": analysis.score_breakdown, "metrics": analysis.metrics}
        await update_job_progress(job_id, current=6, total=6, message="Diagnóstico clínico concluído.")
        await mark_job_success(job_id, result=result, message=f"Clínica concluída: {analysis.score}/100.")
        return result

    try:
        return run_async(execute())
    except Exception as exc:
        run_async(_fail(job_id, exc))
        raise


@celery_app.task(name="platform.cleanup_analyze", bind=True, max_retries=1)
def cleanup_analyze_task(self, job_id: str, params: dict[str, Any]):
    async def execute():
        await mark_job_running(job_id, message="Mapeando dependências e construindo candidatos sem excluir nada.")
        await update_job_progress(job_id, current=1, total=5)
        async with session_scope() as session:
            analysis = await build_cleanup_analysis(
                session,
                user_id=uuid.UUID(params["user_id"]),
                repository_id=uuid.UUID(params["repository_id"]),
                profile_id=uuid.UUID(params["profile_id"]) if params.get("profile_id") else None,
                criteria=dict(params.get("criteria") or {}),
                preservation_rules=dict(params.get("preservation_rules") or {}),
                canonical_checkpoint=dict(params.get("canonical_checkpoint") or {}),
                job_id=uuid.UUID(job_id),
            )
            result = {"analysis_id": str(analysis.id), "reference": analysis.reference, "status": analysis.status, "metrics": analysis.metrics, "checkpoint": analysis.checkpoint}
        await update_job_progress(job_id, current=5, total=5, message="Plano de limpeza construído para revisão.")
        await mark_job_success(job_id, result=result, message=f"Análise {analysis.reference} concluída sem DELETE.")
        return result

    try:
        return run_async(execute())
    except Exception as exc:
        run_async(_fail(job_id, exc))
        raise


@celery_app.task(name="platform.cleanup_dry_run", bind=True, max_retries=0)
def cleanup_dry_run_task(self, job_id: str, params: dict[str, Any]):
    async def execute():
        await mark_job_running(job_id, message="Simulando exatamente o plano selecionado; nenhuma chamada DELETE será feita.")
        async with session_scope() as session:
            analysis = await dry_run_cleanup(session, user_id=uuid.UUID(params["user_id"]), analysis_id=uuid.UUID(params["analysis_id"]))
            result = {"analysis_id": str(analysis.id), "reference": analysis.reference, "status": analysis.status, "dry_run": analysis.dry_run}
        await mark_job_success(job_id, result=result, message="Dry Run concluído sem exclusões.")
        return result

    try:
        return run_async(execute())
    except Exception as exc:
        run_async(_fail(job_id, exc))
        raise


@celery_app.task(name="platform.cleanup_execute", bind=True, max_retries=0)
def cleanup_execute_task(self, job_id: str, params: dict[str, Any]):
    async def execute():
        await mark_job_running(job_id, message="Executando somente candidatos selecionados e não protegidos.")
        await update_job_progress(job_id, current=1, total=12, message="Revalidando checkpoint e recursos protegidos.")
        async with session_scope() as session:
            analysis = await execute_cleanup(
                session,
                user_id=uuid.UUID(params["user_id"]),
                analysis_id=uuid.UUID(params["analysis_id"]),
                confirmation=params["confirmation"],
                backup_snapshot_id=uuid.UUID(params["backup_snapshot_id"]) if params.get("backup_snapshot_id") else None,
            )
            result = {"analysis_id": str(analysis.id), "reference": analysis.reference, "status": analysis.status, "report": analysis.result}
        await update_job_progress(job_id, current=12, total=12, message="Cleanup executado, revalidado e auditado.")
        await mark_job_success(job_id, result=result, message=f"Cleanup {analysis.reference}: {analysis.status}.")
        return result

    try:
        return run_async(execute())
    except Exception as exc:
        run_async(_fail(job_id, exc))
        raise


def _policy_due(policy: BackupPolicy, now: datetime) -> bool:
    if not policy.enabled or policy.schedule_kind == "manual" or policy.event_trigger:
        return False
    if policy.next_run_at and policy.next_run_at > now:
        return False
    if not policy.last_run_at:
        return True
    value = str(policy.schedule_value or "").strip()
    if policy.schedule_kind == "interval_hours":
        try:
            hours = max(1, int(value or "24"))
        except ValueError:
            hours = 24
        return policy.last_run_at <= now - timedelta(hours=hours)
    if policy.schedule_kind == "daily":
        return policy.last_run_at.date() < now.date()
    if policy.schedule_kind == "weekly":
        return policy.last_run_at <= now - timedelta(days=7)
    if policy.schedule_kind == "monthly":
        return policy.last_run_at <= now - timedelta(days=28)
    return False


@celery_app.task(name="platform.schedule_backups")
def schedule_backups_task():
    async def execute():
        now = datetime.now(UTC)
        queued: list[tuple[str, dict[str, Any]]] = []
        async with session_scope() as session:
            policies = (await session.execute(select(BackupPolicy).where(BackupPolicy.enabled.is_(True)))).scalars().all()
            for policy in policies:
                if not _policy_due(policy, now):
                    continue
                job = await create_job(
                    session,
                    user_id=policy.user_id,
                    repository_id=policy.repository_id,
                    kind="repository.backup.scheduled",
                    label=f"Backup agendado · {policy.name}",
                    progress_total=5,
                    message="Política de backup venceu; aguardando worker.",
                )
                queued.append((str(job.id), {"user_id": str(policy.user_id), "policy_id": str(policy.id)}))
                policy.next_run_at = now + timedelta(minutes=10)
        for job_id, params in queued:
            task = backup_task.delay(job_id, params)
            async with session_scope() as session:
                job = await session.get(SyncJob, uuid.UUID(job_id))
                if job:
                    job.celery_task_id = task.id
        return {"queued": len(queued)}

    return run_async(execute())
