from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import DbSession
from app.core.config import get_settings
from app.models.activity import SyncJobStatus, WebhookDelivery
from app.models.github import GitHubConnection, Repository
from app.services.job_queue import create_job
from app.services.webhook_security import verify_github_signature
from app.tasks.jobs import sync_repository_task

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
        return f"Actions · {run.get('name') or 'workflow'} · {run.get('conclusion') or run.get('status') or action or 'atualizado'}"
    if event == "release":
        release = payload.get("release") or {}
        return f"Release {release.get('tag_name') or ''} · {action or 'atualizada'}".strip()
    if event == "issues":
        issue = payload.get("issue") or {}
        return f"Issue #{issue.get('number') or payload.get('number')} · {action or 'atualizada'}"
    return f"Evento GitHub {event} · {action or 'recebido'}"


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

    full_name = ((payload.get("repository") or {}).get("full_name"))
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

    queued_jobs: list[tuple[Repository, object]] = []
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
        for repository, user_id in result.all():
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
            job = await create_job(
                db,
                user_id=user_id,
                connection_id=repository.connection_id,
                repository_id=repository.id,
                kind=f"webhook.{event}",
                label=f"Webhook {event} · {repository.full_name}",
                progress_total=1,
                message="Evento recebido; aguardando atualização detalhada.",
            )
            queued_jobs.append((repository, job))

    # Persiste primeiro a entrega e a atividade. Se o broker estiver indisponível,
    # o evento não é perdido e o job fica visível para retry/reconciliação.
    await db.commit()

    queued = 0
    failed = 0
    for repository, job in queued_jobs:
        try:
            task = sync_repository_task.delay(str(repository.id), str(job.id))
            job.celery_task_id = task.id
            queued += 1
        except Exception as exc:
            job.status = SyncJobStatus.FAILED
            job.error = f"Falha ao enviar webhook ao worker: {exc}"[:4000]
            job.message = "Evento registrado, mas o processamento detalhado não iniciou."
            job.completed_at = datetime.now(UTC)
            failed += 1
    if queued_jobs:
        await db.commit()

    return {
        "status": "accepted",
        "delivery_id": delivery_id,
        "queued": queued,
        "failed": failed,
    }
