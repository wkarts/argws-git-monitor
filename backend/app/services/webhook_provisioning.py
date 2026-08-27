from __future__ import annotations

from typing import Any

from app.services.github_client import GitHubClient

REALTIME_EVENTS = ["push", "pull_request", "workflow_run", "release", "issues"]


async def ensure_repository_webhook(
    client: GitHubClient,
    *,
    full_name: str,
    webhook_url: str,
    secret: str,
) -> dict[str, Any]:
    """Cria ou reconcilia o webhook realtime do Git Monitor de forma idempotente."""

    hooks = await client.paginate(f"/repos/{full_name}/hooks", limit=100)
    for hook in hooks:
        config = hook.get("config") or {}
        if str(config.get("url") or "").rstrip("/") != webhook_url.rstrip("/"):
            continue
        hook_id = int(hook["id"])
        response = await client.request(
            "PATCH",
            f"/repos/{full_name}/hooks/{hook_id}",
            json={
                "active": True,
                "events": REALTIME_EVENTS,
                "config": {
                    "url": webhook_url,
                    "content_type": "json",
                    "secret": secret,
                    "insecure_ssl": "0",
                },
            },
        )
        payload = response.json()
        return {
            "id": hook_id,
            "created": False,
            "active": True,
            "events": REALTIME_EVENTS,
            "payload": payload if isinstance(payload, dict) else {},
        }

    hook = await client.create_webhook(
        full_name,
        webhook_url=webhook_url,
        secret=secret,
    )
    return {
        "id": hook.get("id"),
        "created": True,
        "active": True,
        "events": REALTIME_EVENTS,
        "payload": hook,
    }
