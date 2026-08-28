from __future__ import annotations

import socket
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import get_settings


def _safe_error(exc: Exception) -> dict[str, str | None]:
    error_code: str | None = None
    if isinstance(exc, ClientError):
        payload = getattr(exc, "response", {}) or {}
        error_code = str((payload.get("Error") or {}).get("Code") or "") or None
    return {
        "type": type(exc).__name__,
        "code": error_code,
        "message": str(exc)[:600] or type(exc).__name__,
    }


def _fallback_probe() -> dict[str, Any]:
    settings = get_settings()
    root = Path(settings.internal_object_fallback_root)
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".argws-minio-diagnostics-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return {"ok": True, "path": str(root)}
    except Exception as exc:
        return {"ok": False, "path": str(root), "error": _safe_error(exc)}


def diagnose_minio() -> dict[str, Any]:
    """Testa a cadeia real API -> DNS -> TCP -> health HTTP -> S3 autenticado.

    Nunca retorna segredos. O resultado existe para diagnóstico operacional dentro
    da própria interface do Git Monitor e diferencia topologia ausente de erro de
    credencial S3.
    """

    settings = get_settings()
    endpoint = settings.minio_internal_endpoint.rstrip("/")
    parsed = urlparse(endpoint)
    host = parsed.hostname or "minio"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    result: dict[str, Any] = {
        "ok": False,
        "endpoint": endpoint,
        "host": host,
        "port": port,
        "dns": {"ok": False, "addresses": []},
        "tcp": {"ok": False},
        "health": {"ok": False, "status": None},
        "s3": {"ok": False, "authenticated": False, "bucket_count": None},
        "fallback": _fallback_probe(),
    }

    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        addresses = sorted({str(item[4][0]) for item in infos if item[4]})
        result["dns"] = {"ok": True, "addresses": addresses}
    except Exception as exc:
        result["dns"]["error"] = _safe_error(exc)
        result["message"] = (
            f"O hostname interno '{host}' não foi resolvido. O container MinIO pode não "
            "estar presente na mesma rede Docker da API."
        )
        return result

    try:
        with socket.create_connection((host, port), timeout=2):
            pass
        result["tcp"] = {"ok": True}
    except Exception as exc:
        result["tcp"]["error"] = _safe_error(exc)
        result["message"] = (
            f"O DNS resolveu '{host}', mas não foi possível abrir TCP {host}:{port}. "
            "Verifique se o serviço MinIO está iniciado e conectado à rede da aplicação."
        )
        return result

    health_url = f"{endpoint}/minio/health/live"
    try:
        response = httpx.get(health_url, timeout=4)
        result["health"] = {
            "ok": response.status_code == 200,
            "status": response.status_code,
            "url": health_url,
        }
    except Exception as exc:
        result["health"] = {
            "ok": False,
            "status": None,
            "url": health_url,
            "error": _safe_error(exc),
        }

    try:
        import boto3

        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
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
        payload = client.list_buckets()
        result["s3"] = {
            "ok": True,
            "authenticated": True,
            "bucket_count": len(payload.get("Buckets") or []),
        }
        result["ok"] = True
        result["message"] = "MinIO respondeu, passou no healthcheck e autenticou via S3."
        return result
    except Exception as exc:
        safe = _safe_error(exc)
        result["s3"] = {
            "ok": False,
            "authenticated": False,
            "bucket_count": None,
            "error": safe,
        }
        if safe.get("code") in {"AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch"}:
            result["message"] = (
                "O MinIO está acessível pela rede, mas recusou a credencial S3 interna. "
                "Ajuste a credencial do serviço e da API para o mesmo valor."
            )
        elif result["health"].get("ok"):
            result["message"] = (
                "O healthcheck do MinIO respondeu, mas a API S3 não completou a autenticação."
            )
        else:
            result["message"] = "O endpoint foi alcançado, mas o protocolo S3 não respondeu corretamente."
        return result
