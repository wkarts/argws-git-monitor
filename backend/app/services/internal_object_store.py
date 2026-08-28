from __future__ import annotations

import re
import uuid
from typing import Any

from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import get_settings


class InternalObjectStoreError(RuntimeError):
    pass


_BUCKET_ALIAS = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


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
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _is_missing_bucket(exc: ClientError) -> bool:
    response = getattr(exc, "response", {}) or {}
    status = int((response.get("ResponseMetadata") or {}).get("HTTPStatusCode") or 0)
    code = str((response.get("Error") or {}).get("Code") or "")
    return status == 404 or code in {"404", "NoSuchBucket", "NotFound"}


def ensure_bucket(bucket: str) -> dict[str, Any]:
    client = _client()
    settings = get_settings()
    created = False
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as exc:
        if not _is_missing_bucket(exc):
            raise InternalObjectStoreError("MinIO recusou o acesso ao bucket interno.") from exc
        kwargs: dict[str, Any] = {"Bucket": bucket}
        if settings.minio_internal_region != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {
                "LocationConstraint": settings.minio_internal_region
            }
        client.create_bucket(**kwargs)
        created = True
    return {"bucket": bucket, "created": created, "endpoint": settings.minio_internal_endpoint}


def list_user_buckets(user_id: uuid.UUID) -> list[dict[str, Any]]:
    client = _client()
    prefix = user_bucket_prefix(user_id)
    payload = client.list_buckets()
    buckets: list[dict[str, Any]] = []
    for item in payload.get("Buckets") or []:
        name = str(item.get("Name") or "")
        if not name.startswith(prefix):
            continue
        buckets.append(
            {
                "name": name,
                "alias": bucket_alias_for_user(user_id, name),
                "created_at": (
                    item.get("CreationDate").isoformat()
                    if item.get("CreationDate") is not None
                    else None
                ),
            }
        )
    return sorted(buckets, key=lambda item: item["name"])


def bucket_status(bucket: str) -> dict[str, Any]:
    client = _client()
    client.head_bucket(Bucket=bucket)
    objects = client.list_objects_v2(Bucket=bucket, MaxKeys=1)
    return {
        "bucket": bucket,
        "available": True,
        "has_objects": bool(objects.get("KeyCount") or objects.get("Contents")),
    }


def delete_empty_bucket(bucket: str) -> None:
    client = _client()
    objects = client.list_objects_v2(Bucket=bucket, MaxKeys=1)
    if objects.get("KeyCount") or objects.get("Contents"):
        raise InternalObjectStoreError(
            "O bucket contém objetos. Remova os snapshots vinculados antes de excluir o bucket."
        )
    client.delete_bucket(Bucket=bucket)


def probe() -> dict[str, Any]:
    settings = get_settings()
    client = _client()
    client.list_buckets()
    return {
        "available": True,
        "endpoint": settings.minio_internal_endpoint,
        "access_key": settings.minio_internal_access_key,
    }
