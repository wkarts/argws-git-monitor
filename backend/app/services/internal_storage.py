from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.platform import StorageProvider
from app.services.internal_object_store import bucket_name_for_user, normalize_bucket_alias
from app.services.secret_store import SecretStore

INTERNAL_OBJECT_NAME = "ARGWS · S3 interno"
INTERNAL_LOCAL_NAME = "ARGWS · Local interno"
INTERNAL_ROOT = Path("/data/backups")
DEFAULT_BUCKET_ALIAS = "backups"


def _safe_user_segment(user_id: uuid.UUID) -> str:
    return user_id.hex


def _minio_secret() -> dict[str, str]:
    settings = get_settings()
    return {
        "access_key": settings.minio_internal_access_key,
        "secret_key": settings.internal_minio_secret,
    }


def _managed_config(
    *,
    user_id: uuid.UUID,
    storage_class: str,
    bucket_alias: str = DEFAULT_BUCKET_ALIAS,
    system_default: bool = True,
) -> dict[str, object]:
    user_segment = _safe_user_segment(user_id)
    if storage_class == "internal_s3":
        settings = get_settings()
        alias = normalize_bucket_alias(bucket_alias)
        return {
            "endpoint_url": settings.minio_internal_endpoint,
            "region": settings.minio_internal_region,
            "prefix": "",
            "managed": True,
            "role": "primary_backup" if system_default else "backup_bucket",
            "storage_class": "internal_s3",
            "bucket": bucket_name_for_user(user_id, alias),
            "bucket_alias": alias,
            "system_default": system_default,
            "description": "Bucket S3 interno real gerenciado pelo ARGWS Git Monitor.",
        }
    base_path = INTERNAL_ROOT / "local" / user_segment
    return {
        "base_path": str(base_path),
        "managed": True,
        "role": "local_staging",
        "storage_class": "internal_local",
        "system_default": True,
        "description": "Armazenamento local interno usado como staging e recuperação.",
    }


def _is_system_provider(provider: StorageProvider, storage_class: str) -> bool:
    config = provider.config or {}
    if config.get("managed") is not True:
        return False
    if str(config.get("storage_class") or "") != storage_class:
        return False
    if config.get("system_default") is True:
        return True
    # Migra transparentemente os providers criados pela v0.7.0, que ainda não
    # tinham a marca system_default e usavam estes nomes canônicos.
    return provider.name in {INTERNAL_OBJECT_NAME, INTERNAL_LOCAL_NAME}


async def ensure_internal_storage_providers(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> list[StorageProvider]:
    """Garante o bucket MinIO principal e o staging local.

    A v0.7.0 criava um falso "S3 interno" em filesystem e dependia do default
    de timestamp do banco. Esta rotina migra esse registro para MinIO real e
    também informa created_at/updated_at explicitamente, permanecendo funcional
    mesmo antes de a migration de reparo corrigir instalações com schema drift.
    """
    existing = list(
        (
            await session.execute(
                select(StorageProvider).where(StorageProvider.user_id == user_id)
            )
        ).scalars().all()
    )
    object_provider = next(
        (item for item in existing if _is_system_provider(item, "internal_s3")),
        None,
    )
    local_provider = next(
        (item for item in existing if _is_system_provider(item, "internal_local")),
        None,
    )
    now = datetime.now(UTC)
    store = SecretStore()

    object_config = _managed_config(user_id=user_id, storage_class="internal_s3")
    if object_provider is None:
        object_provider = StorageProvider(
            user_id=user_id,
            name=INTERNAL_OBJECT_NAME,
            kind="minio",
            config=object_config,
            secret_encrypted=store.encrypt_dict(_minio_secret()),
            secret_hint="credencial interna gerenciada",
            enabled=True,
            created_at=now,
            updated_at=now,
        )
        session.add(object_provider)
    else:
        object_provider.name = INTERNAL_OBJECT_NAME
        object_provider.kind = "minio"
        object_provider.config = object_config
        if not object_provider.secret_encrypted:
            object_provider.secret_encrypted = store.encrypt_dict(_minio_secret())
            object_provider.secret_hint = "credencial interna gerenciada"
        object_provider.enabled = True
        object_provider.updated_at = now

    local_config = _managed_config(user_id=user_id, storage_class="internal_local")
    if local_provider is None:
        local_provider = StorageProvider(
            user_id=user_id,
            name=INTERNAL_LOCAL_NAME,
            kind="local",
            config=local_config,
            secret_encrypted=None,
            secret_hint=None,
            enabled=True,
            created_at=now,
            updated_at=now,
        )
        session.add(local_provider)
    else:
        local_provider.name = INTERNAL_LOCAL_NAME
        local_provider.kind = "local"
        local_provider.config = local_config
        local_provider.enabled = True
        local_provider.updated_at = now

    Path(str(local_config["base_path"])).mkdir(parents=True, exist_ok=True)
    await session.flush()
    return [object_provider, local_provider]


async def create_internal_bucket_provider(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    alias: str,
) -> StorageProvider:
    normalized = normalize_bucket_alias(alias)
    bucket = bucket_name_for_user(user_id, normalized)
    providers = list(
        (
            await session.execute(
                select(StorageProvider).where(StorageProvider.user_id == user_id)
            )
        ).scalars().all()
    )
    for provider in providers:
        config = provider.config or {}
        if config.get("managed") is True and config.get("bucket") == bucket:
            return provider

    now = datetime.now(UTC)
    provider = StorageProvider(
        user_id=user_id,
        name=f"ARGWS · Bucket {normalized}",
        kind="minio",
        config=_managed_config(
            user_id=user_id,
            storage_class="internal_s3",
            bucket_alias=normalized,
            system_default=False,
        ),
        secret_encrypted=SecretStore().encrypt_dict(_minio_secret()),
        secret_hint="credencial interna gerenciada",
        enabled=True,
        created_at=now,
        updated_at=now,
    )
    session.add(provider)
    await session.flush()
    return provider


async def default_backup_provider(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> StorageProvider:
    providers = await ensure_internal_storage_providers(session, user_id=user_id)
    return next(
        provider
        for provider in providers
        if (provider.config or {}).get("storage_class") == "internal_s3"
    )


def is_managed_internal_provider(provider: StorageProvider) -> bool:
    config = provider.config or {}
    return bool(config.get("managed")) and str(config.get("storage_class") or "").startswith(
        "internal_"
    )


def is_system_internal_provider(provider: StorageProvider) -> bool:
    return is_managed_internal_provider(provider) and bool(
        (provider.config or {}).get("system_default")
    )
