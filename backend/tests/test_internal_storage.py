from __future__ import annotations

import uuid
from pathlib import Path

import app.services.internal_storage as internal_storage
from app.models.platform import StorageProvider


def test_managed_internal_storage_uses_isolated_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(internal_storage, "INTERNAL_ROOT", tmp_path)
    user_id = uuid.UUID("11111111-2222-3333-4444-555555555555")

    object_config = internal_storage._managed_config(  # noqa: SLF001
        user_id=user_id,
        storage_class="internal_s3",
    )
    local_config = internal_storage._managed_config(  # noqa: SLF001
        user_id=user_id,
        storage_class="internal_local",
    )

    user_segment = "11111111222233334444555555555555"
    assert object_config["bucket"] == "argws-backups"
    assert object_config["role"] == "primary_backup"
    assert object_config["storage_class"] == "internal_s3"
    assert str(object_config["base_path"]).endswith(
        f"object-store/{user_segment}/argws-backups"
    )
    assert local_config["role"] == "local_staging"
    assert local_config["storage_class"] == "internal_local"
    assert str(local_config["base_path"]).endswith(f"local/{user_segment}")


def test_managed_provider_detection() -> None:
    provider = StorageProvider(
        user_id=uuid.uuid4(),
        name="ARGWS · S3 interno",
        kind="local",
        config={"managed": True, "storage_class": "internal_s3"},
        enabled=True,
    )
    external = StorageProvider(
        user_id=uuid.uuid4(),
        name="Dropbox",
        kind="dropbox",
        config={},
        enabled=True,
    )

    assert internal_storage.is_managed_internal_provider(provider) is True
    assert internal_storage.is_managed_internal_provider(external) is False
