from __future__ import annotations

import pytest

from app.main import api_root, app


EXPECTED_OPERATIONAL_PATHS = {
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


def test_operational_routes_are_registered() -> None:
    paths = set(app.openapi()["paths"])
    missing = EXPECTED_OPERATIONAL_PATHS - paths
    assert not missing, f"Rotas operacionais ausentes: {sorted(missing)}"


def test_openapi_exposes_control_center_operations() -> None:
    paths = app.openapi()["paths"]

    assert "post" in paths["/api/v1/auth/2fa/setup"]
    assert "get" in paths["/api/v1/jobs"]
    assert "get" in paths["/api/v1/jobs/overview"]
    assert "get" in paths["/api/v1/admin/users"]
    assert "post" in paths["/api/v1/admin/users"]
    assert "patch" in paths["/api/v1/repositories/{repository_id}/github"]
    assert "delete" in paths["/api/v1/repositories/{repository_id}/monitoring"]
    assert "post" in paths["/api/v1/repositories/{repository_id}/delete-github"]


@pytest.mark.asyncio
async def test_api_root_reports_current_version() -> None:
    payload = await api_root()

    assert payload["name"] == "ARGWS Git Monitor"
    assert payload["version"] == "0.3.0"
    assert payload["status"] == "operational"
    assert payload["docs"] == "/api/v1/docs"
