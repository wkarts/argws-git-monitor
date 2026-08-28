from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import DbSession
from app.core.config import get_settings
from app.models.activity import NotificationSeverity, SyncJobStatus, WebhookDelivery
from app.models.github import GitHubConnection, Repository
from app.models.platform import BackupPolicy
from app.services.github_mapping import parse_github_datetime
from app.services.health import FAILURE_CONCLUSIONS
from app.services.job_queue import create_job
from app.services.notifications import create_notification
from app.services.realtime import publish_event
from app.services.webhook_materializer import materialize_operational_event
from app.services.webhook_security import verify_github_signature
from app.tasks.jobs import sync_repository_task
from app.tasks.platform import backup_task

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

EVENT_SOURCE = {
    "push": "push",
    "pull_request": "pull_request",
    "workflow_run": "actions",
    "release": "release",
    "issues": "issue",
}


def _event_summary(event: str, payload: dict) -> str:
    action = payload.get("action")
    if event == "push":
        ref = str(payload.get("ref") or "").removeprefix("refs/heads/")
        commits = len(payload.get("commits") or [])
        return f"Push em {ref or 'branch'} · {commits} commit(s)"
    if event == "pull_request":
        pull = payload.get("pull_request") or {}
        return f"PR #{pull.get('number') or payload.get('number')} · {action or 'atualizada'}"
    if event == "workflow_run":
        run = payload.get("workflow_run") or {}
        return (
            f"Actions · {run.get('name') or 'workflow'} · "
            f"{run.get('conclusion') or run.get('status') or action or 'atualizado'}"
        )
    if event == "release":
        release = payload.get("release") or {}
        return f"Release {release.get('tag_name') or ''} · {action or 'atualizada'}".strip()
    if event == "issues":
        issue = payload.get("issue") or {}
        return f"Issue #{issue.get('number') or payload.get('number')} · {action or 'atualizada'}"
    return f"Evento GitHub {event} · {action or 'recebido'}"


def _backup_trigger_for_event(event: str, payload: dict) -> str | None:
    if event == "push":
        return "push"
    if event == "release" and payload.get("action") in {
        "published",
        "released",
        "created",
    }:
        return "release"
    if event == "workflow_run":
        run = payload.get("workflow_run") or {}
        if run.get("status") == "completed" and run.get("conclusion") == "success":
            return "workflow_success"
    return None


def _apply_webhook_delta(repository: Repository, event: str, payload: dict, now: datetime) -> None:
    """Aplica apenas informações confiáveis já presentes no webhook.

    A reconciliação REST continua acontecendo no worker, mas a interface deixa de
    depender dela para refletir o evento recém-recebido.
    """

    if event == "push":
        head = payload.get("head_commit") or {}
        repository.pushed_at = parse_github_datetime(head.get("timestamp")) or now
        repository.latest_commit_sha = (
            str(payload.get("after") or head.get("id") or "")
            or repository.latest_commit_sha
        )
        repository.latest_commit_message = head.get("message") or repository.latest_commit_message
        author = head.get("author") or {}
        repository.latest_commit_author = (
            author.get("username") or author.get("name") or repository.latest_commit_author
        )
        repository.latest_commit_at = parse_github_datetime(head.get("timestamp")) or now
        return

    if event == "workflow_run":
        run = payload.get("workflow_run") or {}
        if run.get("id"):
            repository.latest_workflow_id = int(run["id"])
        repository.latest_workflow_name = run.get("name") or repository.latest_workflow_name
        repository.latest_workflow_status = run.get("status") or repository.latest_workflow_status
        repository.latest_workflow_conclusion = run.get("conclusion")
        repository.latest_workflow_url = run.get("html_url") or repository.latest_workflow_url
        repository.latest_workflow_at = (
            parse_github_datetime(run.get("updated_at"))
            or parse_github_datetime(run.get("run_started_at"))
            or now
        )
        return

    if event == "release":
        release = payload.get("release") or {}
        repository.latest_release_tag = release.get("tag_name") or repository.latest_release_tag
        repository.latest_release_name = release.get("name") or repository.latest_release_name
        repository.latest_release_at = (
            parse_github_datetime(release.get("published_at"))
            or parse_github_datetime(release.get("created_at"))
            or now
        )
        return

    action = str(payload.get("action") or "")
    if event == "pull_request":
        if action in {"opened", "reopened"}:
            repository.open_pr_count += 1
        elif action == "closed":
            repository.open_pr_count = max(repository.open_pr_count - 1, 0)
        return

    if event == "issues":
        if action in {"opened", "reopened"}:
            repository.open_issue_count += 1
        elif action == "closed":
            repository.open_issue_count = max(repository.open_issue_count - 1, 0)


async def _create_critical_notification(
    db: DbSession,
    *,
    user_id,
    repository: Repository,
    event: str,
    payload: dict[str, Any],
    delivery_id: str,
    previous_workflow_conclusion: str | None,
) -> dict[str, object] | None:
    """Persiste alertas que não podem esperar a reconciliação Celery.

    O webhook delivery id já é idempotente, e o delta é aplicado antes do full-sync.
    Assim a reconciliação posterior enxerga o mesmo workflow/release e não replica o
    alerta de transição.
    """

    notification = None
    if event == "workflow_run":
        run = payload.get("workflow_run") or {}
        conclusion = str(run.get("conclusion") or "").lower()
        if run.get("status") != "completed":
            return None
        if conclusion in FAILURE_CONCLUSIONS:
            notification = await create_notification(
                db,
                user_id=user_id,
                repository_id=repository.id,
                event_type="workflow.failed",
                severity=NotificationSeverity.ERROR,
                title=f"Build falhou: {repository.full_name}",
                message=(
                    f"{run.get('name') or repository.latest_workflow_name or 'Workflow'} "
                    f"terminou como {conclusion}."
                ),
                url=run.get("html_url") or repository.latest_workflow_url,
                payload={
                    "run_id": run.get("id"),
                    "conclusion": conclusion,
                    "delivery_id": delivery_id,
                    "source": "github_webhook",
                },
            )
        elif conclusion == "success" and previous_workflow_conclusion in FAILURE_CONCLUSIONS:
            notification = await create_notification(
                db,
                user_id=user_id,
                repository_id=repository.id,
                event_type="workflow.recovered",
                severity=NotificationSeverity.SUCCESS,
                title=f"Build recuperada: {repository.full_name}",
                message=(
                    f"{run.get('name') or repository.latest_workflow_name or 'Workflow'} "
                    "voltou a concluir com sucesso."
                ),
                url=run.get("html_url") or repository.latest_workflow_url,
                payload={
                    "run_id": run.get("id"),
                    "delivery_id": delivery_id,
                    "source": "github_webhook",
                },
            )

    elif event == "release" and payload.get("action") in {"published", "released"}:
        release = payload.get("release") or {}
        tag = str(release.get("tag_name") or repository.latest_release_tag or "").strip()
        notification = await create_notification(
            db,
            user_id=user_id,
            repository_id=repository.id,
            event_type="release.published",
            severity=NotificationSeverity.SUCCESS,
            title=f"Nova release: {repository.full_name}",
            message=f"A versão {tag or 'sem tag'} foi publicada.",
            url=release.get("html_url"),
            payload={
                "tag": tag or None,
                "release_id": release.get("id"),
                "delivery_id": delivery_id,
                "source": "github_webhook",
            },
        )

    if notification is None:
        return None
    return {
        "notification_id": str(notification.id),
        "event_type": notification.event_type,
        "severity": notification.severity,
        "title": notification.title,
        "message": notification.message,
        "url": notification.url,
    }


@router.post("/github", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(request: Request, db: DbSession):
    settings = get_settings()
    body = await request.body()
    signature = request.headers.get("x-hub-signature-256")
    if not verify_github_signature(body, signature, settings.github_webhook_secret):
        raise HTTPException(status_code=401, detail="Assinatura do webhook inválida.")

    delivery_id = request.headers.get("x-github-delivery") or hashlib.sha256(body).hexdigest()
    event = request.headers.get("x-github-event") or "unknown"
    existing = await db.execute(
        select(WebhookDelivery).where(WebhookDelivery.delivery_id == delivery_id)
    )
    if existing.scalar_one_or_none():
        return {"status": "duplicate", "delivery_id": delivery_id}

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Payload JSON inválido.") from exc

    full_name = (payload.get("repository") or {}).get("full_name")
    now = datetime.now(UTC)
    delivery = WebhookDelivery(
        delivery_id=delivery_id,
        event=event,
        action=payload.get("action"),
        repository_full_name=full_name,
        signature_valid=True,
        payload=payload,
        processed_at=now,
        created_at=now,
    )
    db.add(delivery)

    sync_jobs: list[tuple[Repository, object]] = []
    backup_jobs: list[tuple[BackupPolicy, Repository, object]] = []
    realtime_events: list[tuple[object, Repository, str, dict[str, object]]] = []
    notification_events: list[tuple[object, Repository, dict[str, object]]] = []
    if full_name and event in EVENT_SOURCE:
        result = await db.execute(
            select(Repository, GitHubConnection.user_id)
            .join(GitHubConnection, Repository.connection_id == GitHubConnection.id)
            .where(
                Repository.full_name == full_name,
                Repository.monitoring_enabled.is_(True),
            )
        )
        source = EVENT_SOURCE[event]
        summary = _event_summary(event, payload)
        backup_trigger = _backup_trigger_for_event(event, payload)

        for repository, user_id in result.all():
            previous_workflow_conclusion = repository.latest_workflow_conclusion
            _apply_webhook_delta(repository, event, payload, now)
            evidence = dict((repository.extra_data or {}).get("activity_sources") or {})
            item = {"at": now.isoformat(), "summary": summary}
            evidence[source] = item
            evidence["repository_event"] = {
                "at": now.isoformat(),
                "summary": f"{event}: {summary}",
            }
            repository.last_activity_at = now
            repository.last_activity_type = source
            repository.last_activity_summary = summary
            repository.activity_observed_at = now
            repository.extra_data = {
                **(repository.extra_data or {}),
                "activity_sources": evidence,
                "activity_observed_at": now.isoformat(),
                "last_webhook_delivery": delivery_id,
            }

            # Materializa Actions/PRs/Releases/Issues no mesmo transaction commit
            # do webhook. Quando o WebSocket notificar a UI, /operations/* já lê
            # o estado novo; o worker é apenas reconciliação e enriquecimento.
            await materialize_operational_event(
                db,
                repository=repository,
                event=event,
                payload=payload,
                observed_at=now,
            )

            notification_data = await _create_critical_notification(
                db,
                user_id=user_id,
                repository=repository,
                event=event,
                payload=payload,
                delivery_id=delivery_id,
                previous_workflow_conclusion=previous_workflow_conclusion,
            )
            if notification_data:
                notification_events.append((user_id, repository, notification_data))

            realtime_events.append(
                (
                    user_id,
                    repository,
                    f"github.{event}",
                    {
                        "delivery_id": delivery_id,
                        "event": event,
                        "action": payload.get("action"),
                        "full_name": repository.full_name,
                        "summary": summary,
                        "materialized": event in {"workflow_run", "pull_request", "release", "issues"},
                    },
                )
            )
            job = await create_job(
                db,
                user_id=user_id,
                connection_id=repository.connection_id,
                repository_id=repository.id,
                kind=f"webhook.{event}",
                label=f"Webhook {event} · {repository.full_name}",
                progress_total=1,
                message="Estado visível aplicado imediatamente; reconciliação detalhada em segundo plano.",
            )
            sync_jobs.append((repository, job))

            if backup_trigger:
                policies = (
                    await db.execute(
                        select(BackupPolicy).where(
                            BackupPolicy.user_id == user_id,
                            BackupPolicy.repository_id == repository.id,
                            BackupPolicy.enabled.is_(True),
                            BackupPolicy.schedule_kind == "event",
                            BackupPolicy.event_trigger == backup_trigger,
                        )
                    )
                ).scalars().all()
                for policy in policies:
                    backup_job = await create_job(
                        db,
                        user_id=user_id,
                        connection_id=repository.connection_id,
                        repository_id=repository.id,
                        kind=f"repository.backup.event.{backup_trigger}",
                        label=f"Backup por evento · {policy.name} · {repository.full_name}",
                        progress_total=5,
                        message=f"Evento {backup_trigger} recebido; backup aguardando worker.",
                    )
                    backup_jobs.append((policy, repository, backup_job))

    # Persiste primeiro entrega, deltas, linhas operacionais, notificações e jobs.
    # O realtime só sai depois do commit para eliminar a janela em que a interface
    # recebia o evento e ainda relia dados antigos das tabelas operacionais.
    await db.commit()

    for user_id, repository, notification_data in notification_events:
        try:
            await publish_event(
                user_id,
                "notification.created",
                notification_data,
                repository_id=repository.id,
                correlation_id=delivery_id,
            )
        except Exception as exc:
            logger.debug("Falha ao publicar notificação %s em realtime: %s", delivery_id, exc)

    for user_id, repository, event_type, event_data in realtime_events:
        try:
            await publish_event(
                user_id,
                event_type,
                event_data,
                repository_id=repository.id,
                correlation_id=delivery_id,
            )
        except Exception as exc:
            logger.debug("Falha ao publicar webhook %s em realtime: %s", delivery_id, exc)

    queued = 0
    failed = 0
    backup_queued = 0
    backup_failed = 0
    for repository, job in sync_jobs:
        try:
            task = sync_repository_task.delay(str(repository.id), str(job.id))
            job.celery_task_id = task.id
            queued += 1
        except Exception as exc:
            job.status = SyncJobStatus.FAILED
            job.error = f"Falha ao enviar webhook ao worker: {exc}"[:4000]
            job.message = "Evento aplicado em tempo real; apenas a reconciliação detalhada falhou."
            job.completed_at = datetime.now(UTC)
            failed += 1

    for policy, repository, job in backup_jobs:
        try:
            task = backup_task.delay(
                str(job.id),
                {
                    "user_id": str(policy.user_id),
                    "policy_id": str(policy.id),
                    "event_delivery_id": delivery_id,
                    "event_repository": repository.full_name,
                },
            )
            job.celery_task_id = task.id
            backup_queued += 1
        except Exception as exc:
            job.status = SyncJobStatus.FAILED
            job.error = f"Falha ao enviar backup por evento ao worker: {exc}"[:4000]
            job.message = "Evento registrado, mas o backup automático não iniciou."
            job.completed_at = datetime.now(UTC)
            backup_failed += 1

    if sync_jobs or backup_jobs:
        await db.commit()

    return {
        "status": "accepted",
        "delivery_id": delivery_id,
        "realtime": len(realtime_events),
        "notifications": len(notification_events),
        "queued": queued,
        "failed": failed,
        "backup_queued": backup_queued,
        "backup_failed": backup_failed,
    }
