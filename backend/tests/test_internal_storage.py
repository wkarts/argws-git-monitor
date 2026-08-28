from __future__ import annotations

import uuid
from pathlib import Path

import pytest

import app.services.internal_storage as internal_storage
from app.models.platform import StorageProvider
from app.services.internal_object_store import (
    InternalObjectStoreError,
    bucket_alias_for_user,
    bucket_name_for_user,
    normalize_bucket_alias,
)
from app.services.storage_providers import LocalStorageAdapter


def test_managed_internal_storage_uses_real_minio_and_isolated_local_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
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
    assert object_config["bucket"] == "argws-111111112222-backups"
    assert object_config["bucket_alias"] == "backups"
    assert object_config["role"] == "primary_backup"
    assert object_config["storage_class"] == "internal_s3"
    assert object_config["endpoint_url"] == "http://minio:9000"
    assert "base_path" not in object_config
    assert local_config["role"] == "local_staging"
    assert local_config["storage_class"] == "internal_local"
    assert str(local_config["base_path"]).endswith(f"local/{user_segment}")


def test_internal_bucket_names_are_scoped_and_validated() -> None:
    user_id = uuid.UUID("11111111-2222-3333-4444-555555555555")
    bucket = bucket_name_for_user(user_id, "Projetos ERP")

    assert bucket == "argws-111111112222-projetos-erp"
    assert bucket_alias_for_user(user_id, bucket) == "projetos-erp"
    assert normalize_bucket_alias("  Meu__Bucket  ") == "meu-bucket"
    with pytest.raises(InternalObjectStoreError):
        normalize_bucket_alias("x")
    with pytest.raises(InternalObjectStoreError):
        normalize_bucket_alias("Bucket@Inválido")


def test_managed_provider_detection() -> None:
    provider = StorageProvider(
        user_id=uuid.uuid4(),
        name="ARGWS · S3 interno",
        kind="minio",
        config={
            "managed": True,
            "storage_class": "internal_s3",
            "system_default": True,
        },
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
    assert internal_storage.is_system_internal_provider(provider) is True
    assert internal_storage.is_managed_internal_provider(external) is False


def test_internal_local_staging_can_write_copy_read_and_delete(tmp_path: Path) -> None:
    root = tmp_path / "local" / "user"
    adapter = LocalStorageAdapter({"base_path": str(root)})
    adapter.test()

    source = tmp_path / "snapshot.tar.gz"
    source.write_bytes(b"ARGWS-backup-payload")
    location = adapter.upload(source, "repositories/wkarts/project/snapshot.tar.gz")

    stored = Path(location.removeprefix("file://"))
    assert stored.is_file()
    assert stored.read_bytes() == source.read_bytes()

    downloaded = tmp_path / "downloaded.tar.gz"
    adapter.download(location, downloaded)
    assert downloaded.read_bytes() == source.read_bytes()

    adapter.delete(location)
    assert stored.exists() is False
