from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.main import api_root, app


EXPECTED_OPERATIONAL_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/2fa/setup",
    "/api/v1/auth/2fa/confirm",
    "/api/v1/auth/2fa/disable",
    "/api/v1/auth/sessions",
    "/api/v1/auth/profile",
    "/api/v1/auth/avatar",
    "/api/v1/github/connections",
    "/api/v1/github/connections/{connection_id}/sync",
    "/api/v1/github/connections/{connection_id}/remote-repositories",
    "/api/v1/github/connections/{connection_id}/import",
    "/api/v1/github/connections/{connection_id}/repositories",
    "/api/v1/github/connections/{connection_id}/diagnostics",
    "/api/v1/repositories",
    "/api/v1/repositories/{repository_id}",
    "/api/v1/repositories/{repository_id}/github",
    "/api/v1/repositories/{repository_id}/monitoring",
    "/api/v1/repositories/{repository_id}/delete-github",
    "/api/v1/repository-controls/blacklist",
    "/api/v1/repository-controls/{repository_id}/blacklist",
    "/api/v1/repository-controls/{repository_id}/actions",
    "/api/v1/realtime/ticket",
    "/api/v1/monitoring/overview",
    "/api/v1/monitoring/runtime",
    "/api/v1/api-access/scopes",
    "/api/v1/api-access/keys",
    "/api/v1/api-access/keys/{key_id}",
    "/api/v1/external/v1/status",
    "/api/v1/external/v1/repositories",
    "/api/v1/external/v1/repositories/{repository_id}/actions",
    "/api/v1/backup-lifecycle/{repository_id}/complete",
    "/api/v1/operations/status",
    "/api/v1/operations/actions",
    "/api/v1/operations/pull-requests",
    "/api/v1/operations/releases",
    "/api/v1/operations/issues",
    "/api/v1/inactivity-policies",
    "/api/v1/inactivity-policies/evaluate-all",
    "/api/v1/jobs",
    "/api/v1/jobs/overview",
    "/api/v1/notifications",
    "/api/v1/admin/users",
    "/api/v1/admin/logs/sources",
    "/api/v1/admin/logs/audit",
    "/api/v1/admin/logs/download",
}


def test_operational_routes_are_registered() -> None:
    paths = set(app.openapi()["paths"])
    missing = EXPECTED_OPERATIONAL_PATHS - paths
    assert not missing, f"Rotas operacionais ausentes: {sorted(missing)}"


def test_openapi_exposes_v060_realtime_and_control_operations() -> None:
    paths = app.openapi()["paths"]

    assert "post" in paths["/api/v1/auth/2fa/setup"]
    assert "patch" in paths["/api/v1/auth/profile"]
    assert "post" in paths["/api/v1/auth/avatar"]
    assert "get" in paths["/api/v1/github/connections/{connection_id}/diagnostics"]
    assert "get" in paths["/api/v1/operations/status"]
    assert "get" in paths["/api/v1/operations/actions"]
    assert "get" in paths["/api/v1/operations/pull-requests"]
    assert "get" in paths["/api/v1/operations/releases"]
    assert "get" in paths["/api/v1/operations/issues"]
    assert "post" in paths["/api/v1/operations/issues"]
    assert "get" in paths["/api/v1/inactivity-policies"]
    assert "post" in paths["/api/v1/inactivity-policies/evaluate-all"]
    assert "get" in paths["/api/v1/jobs"]
    assert "get" in paths["/api/v1/jobs/overview"]
    assert "get" in paths["/api/v1/admin/users"]
    assert "post" in paths["/api/v1/admin/users"]
    assert "get" in paths["/api/v1/admin/logs/sources"]
    assert "get" in paths["/api/v1/admin/logs/download"]
    assert "patch" in paths["/api/v1/repositories/{repository_id}/github"]
    assert "delete" in paths["/api/v1/repositories/{repository_id}/monitoring"]
    assert "post" in paths["/api/v1/repositories/{repository_id}/delete-github"]

    assert "get" in paths["/api/v1/repository-controls/blacklist"]
    assert "post" in paths["/api/v1/repository-controls/{repository_id}/blacklist"]
    assert "delete" in paths["/api/v1/repository-controls/{repository_id}/blacklist"]
    assert "get" in paths["/api/v1/repository-controls/{repository_id}/actions"]
    assert "put" in paths["/api/v1/repository-controls/{repository_id}/actions"]
    assert "post" in paths["/api/v1/realtime/ticket"]
    assert "get" in paths["/api/v1/monitoring/overview"]
    assert "get" in paths["/api/v1/monitoring/runtime"]
    assert "post" in paths["/api/v1/api-access/keys"]
    assert "delete" in paths["/api/v1/api-access/keys/{key_id}"]
    assert "get" in paths["/api/v1/external/v1/status"]
    assert "get" in paths["/api/v1/external/v1/repositories"]
    assert "put" in paths["/api/v1/external/v1/repositories/{repository_id}/actions"]
    assert "post" in paths["/api/v1/backup-lifecycle/{repository_id}/complete"]


def test_websocket_route_is_registered_outside_openapi() -> None:
    websocket_paths = {
        getattr(route, "path", "")
        for route in app.routes
        if route.__class__.__name__ == "APIWebSocketRoute"
    }
    assert "/api/v1/realtime/ws" in websocket_paths


@pytest.mark.asyncio
async def test_api_root_reports_its_internal_version() -> None:
    payload = await api_root()

    assert payload["name"] == "ARGWS Git Monitor"
    assert payload["version"] == get_settings().app_version
    assert payload["status"] == "operational"
    assert payload["docs"] == "/api/v1/docs"
