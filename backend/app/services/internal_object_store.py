from __future__ import annotations

import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import get_settings


class InternalObjectStoreError(RuntimeError):
    pass


_BUCKET_ALIAS = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
_LOCAL_SCHEME = "argws-local-bucket://"


def user_bucket_prefix(user_id: uuid.UUID) -> str:
    return f"argws-{user_id.hex[:12]}-"


def normalize_bucket_alias(value: str) -> str:
    alias = value.strip().lower().replace("_", "-").replace(" ", "-")
    alias = re.sub(r"-+", "-", alias).strip("-")
    if not 3 <= len(alias) <= 32 or not _BUCKET_ALIAS.fullmatch(alias):
        raise InternalObjectStoreError(
            "Nome do bucket deve ter 3 a 32 caracteres, usando apenas letras minúsculas, números e hífen."
        )
    return alias


def bucket_name_for_user(user_id: uuid.UUID, alias: str) -> str:
    return f"{user_bucket_prefix(user_id)}{normalize_bucket_alias(alias)}"


def bucket_alias_for_user(user_id: uuid.UUID, bucket: str) -> str:
    prefix = user_bucket_prefix(user_id)
    return bucket[len(prefix) :] if bucket.startswith(prefix) else bucket


def _client():
    import boto3

    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.minio_internal_endpoint,
        aws_access_key_id=settings.minio_internal_access_key,
        aws_secret_access_key=settings.internal_minio_secret,
        region_name=settings.minio_internal_region,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=2,
            read_timeout=4,
            retries={"max_attempts": 1},
        ),
    )


def _fallback_root() -> Path:
    root = Path(get_settings().internal_object_fallback_root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _bucket_dir(bucket: str) -> Path:
    if not bucket or "/" in bucket or "\\" in bucket or bucket in {".", ".."}:
        raise InternalObjectStoreError("Nome de bucket interno inválido.")
    root = _fallback_root().resolve()
    target = (root / bucket).resolve()
    if not str(target).startswith(str(root) + os.sep):
        raise InternalObjectStoreError("Bucket fora da raiz interna permitida.")
    return target


def _object_path(bucket: str, key: str) -> Path:
    base = _bucket_dir(bucket).resolve()
    target = (base / key.lstrip("/")).resolve()
    if not str(target).startswith(str(base) + os.sep):
        raise InternalObjectStoreError("Objeto fora do bucket interno permitido.")
    return target


def _fallback_probe() -> dict[str, Any]:
    root = _fallback_root()
    probe_file = root / ".argws-object-store-write-test"
    probe_file.write_text("ok", encoding="utf-8")
    probe_file.unlink(missing_ok=True)
    return {"available": True, "path": str(root)}


def _is_missing_bucket(exc: ClientError) -> bool:
    response = getattr(exc, "response", {}) or {}
    status = int((response.get("ResponseMetadata") or {}).get("HTTPStatusCode") or 0)
    code = str((response.get("Error") or {}).get("Code") or "")
    return status == 404 or code in {"404", "NoSuchBucket", "NotFound"}


def _minio_error(exc: Exception) -> str:
    if isinstance(exc, ClientError):
        response = getattr(exc, "response", {}) or {}
        code = str((response.get("Error") or {}).get("Code") or "")
        if code in {"AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch"}:
            return "MinIO respondeu, mas recusou a credencial interna."
    return "MinIO não respondeu; o storage local de contingência foi ativado."


def _fallback_has_objects(bucket: str) -> bool:
    directory = _bucket_dir(bucket)
    if not directory.exists():
        return False
    return any(item.is_file() for item in directory.rglob("*"))


def _ensure_fallback_bucket(bucket: str) -> tuple[Path, bool]:
    directory = _bucket_dir(bucket)
    created = not directory.exists()
    directory.mkdir(parents=True, exist_ok=True)
    return directory, created


def ensure_bucket(bucket: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        client = _client()
        created = False
        try:
            client.head_bucket(Bucket=bucket)
        except ClientError as exc:
            if not _is_missing_bucket(exc):
                raise
            kwargs: dict[str, Any] = {"Bucket": bucket}
            if settings.minio_internal_region != "us-east-1":
                kwargs["CreateBucketConfiguration"] = {
                    "LocationConstraint": settings.minio_internal_region
                }
            client.create_bucket(**kwargs)
            created = True
        return {
            "bucket": bucket,
            "created": created,
            "available": True,
            "engine": "minio",
            "degraded": False,
            "minio_available": True,
            "fallback_available": True,
            "endpoint": settings.minio_internal_endpoint,
        }
    except Exception as exc:
        directory, created = _ensure_fallback_bucket(bucket)
        _fallback_probe()
        return {
            "bucket": bucket,
            "created": created,
            "available": True,
            "engine": "local_fallback",
            "degraded": True,
            "minio_available": False,
            "fallback_available": True,
            "endpoint": f"file://{directory}",
            "error": _minio_error(exc),
        }


def list_user_buckets(user_id: uuid.UUID) -> list[dict[str, Any]]:
    prefix = user_bucket_prefix(user_id)
    found: dict[str, dict[str, Any]] = {}
    try:
        payload = _client().list_buckets()
        for item in payload.get("Buckets") or []:
            name = str(item.get("Name") or "")
            if not name.startswith(prefix):
                continue
            found[name] = {
                "name": name,
                "alias": bucket_alias_for_user(user_id, name),
                "created_at": (
                    item.get("CreationDate").isoformat()
                    if item.get("CreationDate") is not None
                    else None
                ),
                "engine": "minio",
            }
    except Exception:
        pass

    root = _fallback_root()
    for directory in root.glob(f"{prefix}*"):
        if not directory.is_dir():
            continue
        name = directory.name
        found.setdefault(
            name,
            {
                "name": name,
                "alias": bucket_alias_for_user(user_id, name),
                "created_at": None,
                "engine": "local_fallback",
            },
        )
    return sorted(found.values(), key=lambda item: item["name"])


def bucket_status(bucket: str) -> dict[str, Any]:
    local_has_objects = _fallback_has_objects(bucket)
    try:
        client = _client()
        client.head_bucket(Bucket=bucket)
        objects = client.list_objects_v2(Bucket=bucket, MaxKeys=1)
        remote_has_objects = bool(objects.get("KeyCount") or objects.get("Contents"))
        return {
            "bucket": bucket,
            "available": True,
            "engine": "minio",
            "degraded": False,
            "minio_available": True,
            "fallback_available": True,
            "has_objects": remote_has_objects or local_has_objects,
            "remote_has_objects": remote_has_objects,
            "local_fallback_has_objects": local_has_objects,
        }
    except Exception as exc:
        _ensure_fallback_bucket(bucket)
        _fallback_probe()
        return {
            "bucket": bucket,
            "available": True,
            "engine": "local_fallback",
            "degraded": True,
            "minio_available": False,
            "fallback_available": True,
            "has_objects": local_has_objects,
            "remote_has_objects": None,
            "local_fallback_has_objects": local_has_objects,
            "error": _minio_error(exc),
        }


def delete_empty_bucket(bucket: str) -> dict[str, Any]:
    directory = _bucket_dir(bucket)
    if _fallback_has_objects(bucket):
        raise InternalObjectStoreError(
            "O bucket contém objetos no storage local. Remova os snapshots vinculados antes de excluir."
        )

    minio_deleted = False
    minio_available = False
    try:
        client = _client()
        client.head_bucket(Bucket=bucket)
        objects = client.list_objects_v2(Bucket=bucket, MaxKeys=1)
        if objects.get("KeyCount") or objects.get("Contents"):
            raise InternalObjectStoreError(
                "O bucket contém objetos no MinIO. Remova os snapshots vinculados antes de excluir."
            )
        client.delete_bucket(Bucket=bucket)
        minio_deleted = True
        minio_available = True
    except InternalObjectStoreError:
        raise
    except ClientError as exc:
        if not _is_missing_bucket(exc):
            minio_available = False
    except Exception:
        minio_available = False

    if directory.exists():
        shutil.rmtree(directory)
    return {
        "deleted": True,
        "minio_deleted": minio_deleted,
        "minio_available": minio_available,
    }


def upload_file(bucket: str, local_path: Path, remote_key: str) -> str:
    ensure = ensure_bucket(bucket)
    if ensure.get("engine") == "minio":
        try:
            client = _client()
            client.upload_file(str(local_path), bucket, remote_key)
            return f"s3://{bucket}/{remote_key}"
        except Exception:
            pass

    destination = _object_path(bucket, remote_key)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(local_path, destination)
    return f"{_LOCAL_SCHEME}{quote(bucket, safe='')}/{quote(remote_key, safe='/')}"


def download_file(bucket: str, location: str, local_path: Path) -> Path:
    local_path.parent.mkdir(parents=True, exist_ok=True)
    if location.startswith(_LOCAL_SCHEME):
        encoded = location.removeprefix(_LOCAL_SCHEME)
        encoded_bucket, _, encoded_key = encoded.partition("/")
        source_bucket = unquote(encoded_bucket)
        source_key = unquote(encoded_key)
        source = _object_path(source_bucket, source_key)
        if not source.exists():
            raise InternalObjectStoreError("Objeto do backup local não foi encontrado.")
        shutil.copy2(source, local_path)
        return local_path

    prefix = f"s3://{bucket}/"
    key = location[len(prefix) :] if location.startswith(prefix) else location
    try:
        _client().download_file(bucket, key, str(local_path))
        return local_path
    except Exception as exc:
        source = _object_path(bucket, key)
        if source.exists():
            shutil.copy2(source, local_path)
            return local_path
        raise InternalObjectStoreError(
            "Snapshot não pôde ser lido do MinIO nem do storage local de contingência."
        ) from exc


def delete_object(bucket: str, location: str) -> None:
    if location.startswith(_LOCAL_SCHEME):
        encoded = location.removeprefix(_LOCAL_SCHEME)
        encoded_bucket, _, encoded_key = encoded.partition("/")
        target = _object_path(unquote(encoded_bucket), unquote(encoded_key))
        target.unlink(missing_ok=True)
        return

    prefix = f"s3://{bucket}/"
    key = location[len(prefix) :] if location.startswith(prefix) else location
    try:
        _client().delete_object(Bucket=bucket, Key=key)
    except Exception:
        target = _object_path(bucket, key)
        target.unlink(missing_ok=True)


def probe() -> dict[str, Any]:
    settings = get_settings()
    fallback = _fallback_probe()
    try:
        _client().list_buckets()
        return {
            "available": True,
            "engine": "minio",
            "degraded": False,
            "minio_available": True,
            "fallback_available": True,
            "endpoint": settings.minio_internal_endpoint,
            "access_key": settings.minio_internal_access_key,
            "fallback_path": fallback["path"],
        }
    except Exception as exc:
        return {
            "available": True,
            "engine": "local_fallback",
            "degraded": True,
            "minio_available": False,
            "fallback_available": True,
            "endpoint": settings.minio_internal_endpoint,
            "access_key": settings.minio_internal_access_key,
            "fallback_path": fallback["path"],
            "error": _minio_error(exc),
        }
