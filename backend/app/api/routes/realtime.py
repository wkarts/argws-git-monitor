from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.services.realtime import (
    consume_websocket_ticket,
    issue_websocket_ticket,
    open_user_pubsub,
)

router = APIRouter(prefix="/realtime", tags=["Realtime"])


@router.post("/ticket")
async def create_realtime_ticket(current_user: CurrentUser) -> dict[str, object]:
    """Emite um ticket efêmero e de uso único para abrir o WebSocket.

    O JWT não é colocado na URL do WebSocket, evitando exposição em logs de proxy,
    histórico e ferramentas de observabilidade.
    """

    return await issue_websocket_ticket(current_user.id)


@router.websocket("/ws")
async def websocket_events(
    websocket: WebSocket,
    ticket: str = Query(min_length=20, max_length=256),
) -> None:
    settings = get_settings()
    origin = websocket.headers.get("origin")
    if origin and origin not in settings.cors_origin_list:
        await websocket.close(code=1008, reason="Origem não autorizada")
        return

    user_id = await consume_websocket_ticket(ticket)
    if user_id is None:
        await websocket.close(code=1008, reason="Ticket inválido ou expirado")
        return

    await websocket.accept()
    redis_client, pubsub = await open_user_pubsub(user_id)
    try:
        await websocket.send_json(
            {
                "type": "realtime.connected",
                "occurred_at": datetime.now(UTC).isoformat(),
                "repository_id": None,
                "correlation_id": None,
                "data": {"transport": "websocket", "mode": "redis-pubsub"},
            }
        )
        while True:
            message = await pubsub.get_message(timeout=20.0)
            if message and message.get("type") == "message":
                raw = message.get("data")
                if isinstance(raw, str):
                    try:
                        await websocket.send_text(raw)
                    except WebSocketDisconnect:
                        break
            else:
                try:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "realtime.heartbeat",
                                "occurred_at": datetime.now(UTC).isoformat(),
                                "repository_id": None,
                                "correlation_id": None,
                                "data": {},
                            },
                            separators=(",", ":"),
                        )
                    )
                except WebSocketDisconnect:
                    break
            await asyncio.sleep(0)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        try:
            await pubsub.unsubscribe()
            await pubsub.aclose()
        finally:
            await redis_client.aclose()
