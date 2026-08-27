from __future__ import annotations

import pytest

from app.api.routes.webhooks import _backup_trigger_for_event, _event_summary
from app.services.api_access import ApiAccessError, generate_api_token, normalize_scopes
from app.services.webhook_provisioning import REALTIME_EVENTS, ensure_repository_webhook


def test_api_access_key_generation_and_scope_normalization() -> None:
    token, prefix, digest = generate_api_token()

    assert token.startswith(f"agm_{prefix}_")
    assert len(prefix) == 12
    assert len(digest) == 64
    assert normalize_scopes(
        ["repositories:read", "monitoring:read", "repositories:read"]
    ) == ["monitoring:read", "repositories:read"]


@pytest.mark.parametrize(
    "scopes",
    [[], ["unknown:scope"]],
)
def test_api_access_rejects_empty_or_unknown_scopes(scopes: list[str]) -> None:
    with pytest.raises(ApiAccessError):
        normalize_scopes(scopes)


def test_webhook_event_summary_and_backup_triggers() -> None:
    assert _event_summary(
        "push",
        {"ref": "refs/heads/main", "commits": [{"id": "1"}, {"id": "2"}]},
    ) == "Push em main · 2 commit(s)"
    assert _backup_trigger_for_event("push", {}) == "push"
    assert _backup_trigger_for_event(
        "release", {"action": "published"}
    ) == "release"
    assert _backup_trigger_for_event(
        "workflow_run",
        {"workflow_run": {"status": "completed", "conclusion": "success"}},
    ) == "workflow_success"
    assert _backup_trigger_for_event(
        "workflow_run",
        {"workflow_run": {"status": "completed", "conclusion": "failure"}},
    ) is None


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _FakeGitHubClient:
    def __init__(self, hooks: list[dict] | None = None) -> None:
        self.hooks = hooks or []
        self.requests: list[tuple[str, str, dict]] = []
        self.created: list[tuple[str, str, str]] = []

    async def paginate(self, path: str, *, limit: int = 100) -> list[dict]:
        assert path.endswith("/hooks")
        assert limit == 100
        return self.hooks

    async def request(self, method: str, path: str, *, json: dict):
        self.requests.append((method, path, json))
        return _FakeResponse({"id": 44, "active": True})

    async def create_webhook(
        self,
        full_name: str,
        *,
        webhook_url: str,
        secret: str,
    ) -> dict:
        self.created.append((full_name, webhook_url, secret))
        return {"id": 99, "active": True}


@pytest.mark.asyncio
async def test_webhook_provisioning_updates_existing_hook_idempotently() -> None:
    client = _FakeGitHubClient(
        hooks=[
            {
                "id": 44,
                "config": {"url": "https://monitor.example/api/v1/webhooks/github"},
            }
        ]
    )

    result = await ensure_repository_webhook(
        client,  # type: ignore[arg-type]
        full_name="wkarts/project",
        webhook_url="https://monitor.example/api/v1/webhooks/github",
        secret="secret",
    )

    assert result["id"] == 44
    assert result["created"] is False
    assert result["events"] == REALTIME_EVENTS
    assert client.created == []
    method, path, payload = client.requests[0]
    assert method == "PATCH"
    assert path.endswith("/hooks/44")
    assert payload["active"] is True
    assert payload["events"] == REALTIME_EVENTS
    assert payload["config"]["content_type"] == "json"
    assert payload["config"]["insecure_ssl"] == "0"


@pytest.mark.asyncio
async def test_webhook_provisioning_creates_missing_hook() -> None:
    client = _FakeGitHubClient()

    result = await ensure_repository_webhook(
        client,  # type: ignore[arg-type]
        full_name="wkarts/project",
        webhook_url="https://monitor.example/api/v1/webhooks/github",
        secret="secret",
    )

    assert result["id"] == 99
    assert result["created"] is True
    assert client.requests == []
    assert client.created == [
        (
            "wkarts/project",
            "https://monitor.example/api/v1/webhooks/github",
            "secret",
        )
    ]
