from __future__ import annotations

import socket
import sys
from pathlib import Path
from types import SimpleNamespace

import app.services.minio_diagnostics as diagnostics


def _settings(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        minio_internal_endpoint="http://minio:9000",
        minio_internal_access_key="argws-internal",
        internal_minio_secret="secret-with-more-than-32-characters",
        minio_internal_region="us-east-1",
        internal_object_fallback_root=str(tmp_path / "object-store"),
    )


def test_diagnose_minio_reports_missing_docker_dns(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(diagnostics, "get_settings", lambda: _settings(tmp_path))

    def fail_dns(*args, **kwargs):
        del args, kwargs
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr(diagnostics.socket, "getaddrinfo", fail_dns)
    result = diagnostics.diagnose_minio()

    assert result["ok"] is False
    assert result["dns"]["ok"] is False
    assert result["tcp"]["ok"] is False
    assert result["s3"]["ok"] is False
    assert result["fallback"]["ok"] is True
    assert "mesma rede Docker" in result["message"]


def test_diagnose_minio_validates_health_and_authenticated_s3(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(diagnostics, "get_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(
        diagnostics.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.20.0.9", 9000))],
    )

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(diagnostics.socket, "create_connection", lambda *args, **kwargs: Connection())
    monkeypatch.setattr(
        diagnostics.httpx,
        "get",
        lambda *args, **kwargs: SimpleNamespace(status_code=200),
    )

    class S3Client:
        def list_buckets(self):
            return {"Buckets": [{"Name": "one"}, {"Name": "two"}]}

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda *args, **kwargs: S3Client()))
    result = diagnostics.diagnose_minio()

    assert result["ok"] is True
    assert result["dns"]["addresses"] == ["172.20.0.9"]
    assert result["tcp"]["ok"] is True
    assert result["health"]["ok"] is True
    assert result["health"]["status"] == 200
    assert result["s3"]["authenticated"] is True
    assert result["s3"]["bucket_count"] == 2
    assert result["fallback"]["ok"] is True
