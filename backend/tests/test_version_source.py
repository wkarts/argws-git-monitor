from __future__ import annotations

import os

from app.core.config import get_settings, resolve_app_version


def test_app_version_comes_from_package_not_environment(monkeypatch) -> None:
    monkeypatch.setenv("APP_VERSION", "999.999.999")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.app_version == resolve_app_version()
        assert settings.app_version != os.environ["APP_VERSION"]
    finally:
        get_settings.cache_clear()
