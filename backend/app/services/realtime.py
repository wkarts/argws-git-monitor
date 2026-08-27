from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis

from app.core.config import get_settings

_EVENT_PREFIX = "argws:realtime:user:"
_TICKET_PREFIX = "argws:realtime:ticket:"
_TICKET_TTL_SECONDS = 45


def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


def _ticket_key(ticket: str) -> str:
    digest = hashlib.sha256(ticket.encode("utf-8")).hexdigest()
    return f"{_TICKET_PREFIX}{digest}"


def user_channel(user_id: uuid.UUID | str) -> str:
    return f"{_EVENT_PREFIX}{user_id}"


async def issue_websocket_ticket(user_id: uuid.UUID | str) -> dict[str, Any]:
    ticket = secrets.token_urlsafe(32)
    client = _redis()
    try:
        await client.set(
            _ticket_key(ticket),
            str(user_id),
            ex=_TICKET_TTL_SECONDS,
            nx=True,
        )
    finally:
        await client.aclose()
    return {
        "ticket": ticket,
        "expires_in": _TICKET_TTL_SECONDS,
        "websocket_path": f"{get_settings().api_v1_prefix}/realtime/ws",
    }


async def consume_websocket_ticket(ticket: str) -> uuid.UUID | None:
    if not ticket or len(ticket) > 256:
        return None
    client = _redis()
    try:
        value = await client.getdel(_ticket_key(ticket))
    finally:
        await client.aclose()
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


async def publish_event(
    user_id: uuid.UUID | str,
    event_type: str,
    data: dict[str, Any] | None = None,
    *,
    repository_id: uuid.UUID | str | None = None,
    correlation_id: str | None = None,
) -> None:
    payload = {
        "type": event_type,
        "occurred_at": datetime.now(UTC).isoformat(),
        "repository_id": str(repository_id) if repository_id else None,
        "correlation_id": correlation_id,
        "data": data or {},
    }
    client = _redis()
    try:
        await client.publish(
            user_channel(user_id),
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        )
    finally:
        await client.aclose()


async def open_user_pubsub(user_id: uuid.UUID | str):
    client = _redis()
    pubsub = client.pubsub(ignore_subscribe_messages=True)
    await pubsub.subscribe(user_channel(user_id))
    return client, pubsub
