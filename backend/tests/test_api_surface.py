from __future__ import annotations

import pytest

from app.main import api_root, app


def test_operational_routes_are_registered() -> None:
    paths = {
        path
        for route in app.routes
        if (path := getattr(route, "path", None)) is not None
    }

    expected = {
        "/api/v1/auth/login",
        "/api/v1/auth/2fa/setup",
        "/api/v1/auth/2fa/confirm",
        "/api/v1/auth/2fa/disable",
        "/api/v1/auth/sessions",
        "/api/v1/github/connections",
        "/api/v1/github/connections/{connection_id}/sync",
        "/api/v1/github/connections/{connection_id}/remote-repositories",
        "/api/v1/github/connections/{connection_id}/import",
        "/api/v1/github/connections/{connection_id}/repositories",
        "/api/v1/repositories",
        "/api/v1/repositories/{repository_id}",
        "/api/v1/repositories/{repository_id}/github",
        "/api/v1/repositories/{repository_id}/monitoring",
        "/api/v1/repositories/{repository_id}/delete-github",
        "/api/v1/jobs",
        "/api/v1/jobs/overview",
        "/api/v1/admin/users",
    }

    missing = expected - paths
    assert not missing, f"Rotas operacionais ausentes: {sorted(missing)}"


def test_openapi_exposes_control_center_groups() -> None:
    schema = app.openapi()
    paths = schema["paths"]

    assert "/api/v1/jobs" in paths
    assert "/api/v1/admin/users" in paths
    assert "/api/v1/auth/2fa/setup" in paths
    assert "/api/v1/repositories/{repository_id}/github" in paths
    assert "/api/v1/repositories/{repository_id}/delete-github" in paths


@pytest.mark.asyncio
async def test_api_root_reports_current_version() -> None:
    payload = await api_root()

    assert payload["name"] == "ARGWS Git Monitor"
    assert payload["version"] == "0.3.0"
    assert payload["status"] == "operational"
    assert payload["docs"] == "/api/v1/docs"
