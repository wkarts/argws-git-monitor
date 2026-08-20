from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import DbSession
from app.core.config import get_settings
from app.models.activity import WebhookDelivery
from app.models.github import Repository
from app.services.webhook_security import verify_github_signature
from app.tasks.jobs import sync_repository_task

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])



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
    delivery = WebhookDelivery(
        delivery_id=delivery_id,
        event=event,
        action=payload.get("action"),
        repository_full_name=full_name,
        signature_valid=True,
        payload=payload,
        processed_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    db.add(delivery)
    await db.commit()

    queued = 0
    if full_name and event in {"push", "pull_request", "workflow_run", "release", "issues"}:
        result = await db.execute(
            select(Repository.id).where(
                Repository.full_name == full_name,
                Repository.monitoring_enabled.is_(True),
            )
        )
        for repository_id in result.scalars().all():
            sync_repository_task.delay(str(repository_id))
            queued += 1

    return {"status": "accepted", "delivery_id": delivery_id, "queued": queued}
