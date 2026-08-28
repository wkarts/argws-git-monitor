from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform import StorageProvider

INTERNAL_OBJECT_NAME = "ARGWS · S3 interno"
INTERNAL_LOCAL_NAME = "ARGWS · Local interno"
INTERNAL_ROOT = Path("/data/backups")


def _safe_user_segment(user_id: uuid.UUID) -> str:
    return str(user_id).replace("-", "")


def _managed_config(*, user_id: uuid.UUID, storage_class: str) -> dict[str, object]:
    user_segment = _safe_user_segment(user_id)
    if storage_class == "internal_s3":
        base_path = INTERNAL_ROOT / "object-store" / user_segment / "argws-backups"
        return {
            "base_path": str(base_path),
            "managed": True,
            "role": "primary_backup",
            "storage_class": "internal_s3",
            "bucket": "argws-backups",
            "description": "Object storage interno, isolado por usuário e persistido em /data/backups.",
        }
    base_path = INTERNAL_ROOT / "local" / user_segment
    return {
        "base_path": str(base_path),
        "managed": True,
        "role": "local_staging",
        "storage_class": "internal_local",
        "description": "Armazenamento local interno usado como staging e recuperação.",
    }


async def ensure_internal_storage_providers(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> list[StorageProvider]:
    """Garante dois destinos internos sem depender de manifests de deployment.

    Ambos usam o volume persistente já montado em /data/backups. O provider
    `internal_s3` aplica semântica bucket/key sobre filesystem local; ele não
    expõe um endpoint S3 público e serve como object storage primário interno.
    """
    existing = list(
        (
            await session.execute(
                select(StorageProvider).where(StorageProvider.user_id == user_id)
            )
        ).scalars().all()
    )
    by_class = {
        str((provider.config or {}).get("storage_class") or ""): provider
        for provider in existing
        if (provider.config or {}).get("managed") is True
    }

    desired = [
        ("internal_s3", INTERNAL_OBJECT_NAME),
        ("internal_local", INTERNAL_LOCAL_NAME),
    ]
    result: list[StorageProvider] = []
    for storage_class, name in desired:
        provider = by_class.get(storage_class)
        config = _managed_config(user_id=user_id, storage_class=storage_class)
        if provider is None:
            provider = StorageProvider(
                user_id=user_id,
                name=name,
                kind="local",
                config=config,
                secret_encrypted=None,
                secret_hint=None,
                enabled=True,
            )
            session.add(provider)
        else:
            provider.name = name
            provider.kind = "local"
            provider.config = config
            provider.enabled = True
        Path(str(config["base_path"])).mkdir(parents=True, exist_ok=True)
        result.append(provider)

    await session.flush()
    return result


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
