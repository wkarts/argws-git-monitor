from __future__ import annotations

import io
import json
import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import httpx

from app.models.platform import StorageProvider
from app.services.secret_store import SecretStore
from app.services.ssh_security import configure_ssh_host_keys


class StorageProviderError(RuntimeError):
    pass


class StorageAdapter(ABC):
    @abstractmethod
    def test(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def upload(self, local_path: Path, remote_key: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def download(self, location: str, local_path: Path) -> Path:
        raise NotImplementedError

    def delete(self, location: str) -> None:
        raise StorageProviderError("Este provider não implementa remoção automática.")


class LocalStorageAdapter(StorageAdapter):
    def __init__(self, config: dict[str, Any]) -> None:
        self.base = Path(str(config.get("base_path") or "/data/backups"))

    def test(self) -> dict[str, Any]:
        self.base.mkdir(parents=True, exist_ok=True)
        probe = self.base / ".argws-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return {"path": str(self.base), "writable": True}

    def upload(self, local_path: Path, remote_key: str) -> str:
        destination = (self.base / remote_key).resolve()
        base = self.base.resolve()
        if not str(destination).startswith(str(base) + os.sep):
            raise StorageProviderError("Destino local fora da raiz permitida.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, destination)
        return str(destination)

    def download(self, location: str, local_path: Path) -> Path:
        source = Path(location)
        if not source.exists():
            raise StorageProviderError("Backup local não encontrado.")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, local_path)
        return local_path

    def delete(self, location: str) -> None:
        target = Path(location).resolve()
        base = self.base.resolve()
        if str(target).startswith(str(base) + os.sep):
            target.unlink(missing_ok=True)


class S3StorageAdapter(StorageAdapter):
    def __init__(self, config: dict[str, Any], secret: dict[str, Any], *, minio: bool = False) -> None:
        try:
            import boto3
        except ImportError as exc:
            raise StorageProviderError("boto3 não está instalado na imagem do worker.") from exc
        kwargs: dict[str, Any] = {
            "aws_access_key_id": secret.get("access_key") or secret.get("access_key_id"),
            "aws_secret_access_key": secret.get("secret_key") or secret.get("secret_access_key"),
            "region_name": config.get("region") or "us-east-1",
        }
        endpoint = config.get("endpoint_url")
        if endpoint:
            kwargs["endpoint_url"] = endpoint
        self.client = boto3.client("s3", **kwargs)
        self.bucket = str(config.get("bucket") or "")
        self.prefix = str(config.get("prefix") or "").strip("/")
        if not self.bucket:
            raise StorageProviderError("Bucket é obrigatório.")

    def _key(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def test(self) -> dict[str, Any]:
        self.client.head_bucket(Bucket=self.bucket)
        return {"bucket": self.bucket, "ok": True}

    def upload(self, local_path: Path, remote_key: str) -> str:
        key = self._key(remote_key)
        self.client.upload_file(str(local_path), self.bucket, key)
        return f"s3://{self.bucket}/{key}"

    def download(self, location: str, local_path: Path) -> Path:
        prefix = f"s3://{self.bucket}/"
        key = location[len(prefix):] if location.startswith(prefix) else self._key(location)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(self.bucket, key, str(local_path))
        return local_path

    def delete(self, location: str) -> None:
        prefix = f"s3://{self.bucket}/"
        key = location[len(prefix):] if location.startswith(prefix) else location
        self.client.delete_object(Bucket=self.bucket, Key=key)


class DropboxStorageAdapter(StorageAdapter):
    def __init__(self, config: dict[str, Any], secret: dict[str, Any]) -> None:
        self.token = str(secret.get("access_token") or "")
        self.base = "/" + str(config.get("base_path") or "argws-git-monitor").strip("/")
        if not self.token:
            raise StorageProviderError("access_token do Dropbox é obrigatório.")

    def test(self) -> dict[str, Any]:
        response = httpx.post(
            "https://api.dropboxapi.com/2/users/get_current_account",
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=30,
        )
        response.raise_for_status()
        return {"account_id": response.json().get("account_id"), "ok": True}

    def upload(self, local_path: Path, remote_key: str) -> str:
        path = f"{self.base}/{remote_key}".replace("//", "/")
        response = httpx.post(
            "https://content.dropboxapi.com/2/files/upload",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/octet-stream",
                "Dropbox-API-Arg": json.dumps({"path": path, "mode": "overwrite"}),
            },
            content=local_path.read_bytes(),
            timeout=300,
        )
        response.raise_for_status()
        return f"dropbox:{path}"

    def download(self, location: str, local_path: Path) -> Path:
        path = location.removeprefix("dropbox:")
        response = httpx.post(
            "https://content.dropboxapi.com/2/files/download",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Dropbox-API-Arg": json.dumps({"path": path}),
            },
            timeout=300,
        )
        response.raise_for_status()
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(response.content)
        return local_path

    def delete(self, location: str) -> None:
        path = location.removeprefix("dropbox:")
        response = httpx.post(
            "https://api.dropboxapi.com/2/files/delete_v2",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            json={"path": path},
            timeout=30,
        )
        response.raise_for_status()


class GoogleDriveStorageAdapter(StorageAdapter):
    def __init__(self, config: dict[str, Any], secret: dict[str, Any]) -> None:
        self.token = str(secret.get("access_token") or "")
        self.folder_id = str(config.get("folder_id") or "")
        if not self.token:
            raise StorageProviderError("access_token do Google Drive é obrigatório.")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def test(self) -> dict[str, Any]:
        response = httpx.get(
            "https://www.googleapis.com/drive/v3/about",
            headers=self._headers(),
            params={"fields": "user,storageQuota"},
            timeout=30,
        )
        response.raise_for_status()
        return {"user": response.json().get("user"), "ok": True}

    def upload(self, local_path: Path, remote_key: str) -> str:
        metadata: dict[str, Any] = {"name": remote_key.replace("/", "__")}
        if self.folder_id:
            metadata["parents"] = [self.folder_id]
        boundary = "argws_boundary_7cfc6d"
        body = io.BytesIO()
        body.write(
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode()
        )
        body.write(json.dumps(metadata).encode())
        body.write(
            f"\r\n--{boundary}\r\nContent-Type: application/octet-stream\r\n\r\n".encode()
        )
        body.write(local_path.read_bytes())
        body.write(f"\r\n--{boundary}--\r\n".encode())
        response = httpx.post(
            "https://www.googleapis.com/upload/drive/v3/files",
            headers={**self._headers(), "Content-Type": f"multipart/related; boundary={boundary}"},
            params={"uploadType": "multipart", "fields": "id,name,size,md5Checksum"},
            content=body.getvalue(),
            timeout=300,
        )
        response.raise_for_status()
        return f"gdrive:{response.json()['id']}"

    def download(self, location: str, local_path: Path) -> Path:
        file_id = location.removeprefix("gdrive:")
        response = httpx.get(
            f"https://www.googleapis.com/drive/v3/files/{file_id}",
            headers=self._headers(),
            params={"alt": "media"},
            timeout=300,
        )
        response.raise_for_status()
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(response.content)
        return local_path

    def delete(self, location: str) -> None:
        file_id = location.removeprefix("gdrive:")
        response = httpx.delete(
            f"https://www.googleapis.com/drive/v3/files/{file_id}",
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()


class SFTPStorageAdapter(StorageAdapter):
    def __init__(self, config: dict[str, Any], secret: dict[str, Any]) -> None:
        try:
            import paramiko
        except ImportError as exc:
            raise StorageProviderError("paramiko não está instalado na imagem do worker.") from exc
        self.paramiko = paramiko
        self.config = dict(config or {})
        self.secret = dict(secret or {})
        self.host = str(config.get("host") or "")
        self.port = int(config.get("port") or 22)
        self.username = str(config.get("username") or secret.get("username") or "")
        self.base = str(config.get("base_path") or "/var/backups/argws-git-monitor").rstrip("/")
        self.password = secret.get("password")
        self.private_key = secret.get("private_key")
        self.private_key_password = secret.get("private_key_password")
        if not self.host or not self.username:
            raise StorageProviderError("host e username são obrigatórios.")

    def _connect(self):
        client = self.paramiko.SSHClient()
        configure_ssh_host_keys(
            client,
            self.paramiko,
            config=self.config,
            secret=self.secret,
            error_type=StorageProviderError,
        )
        kwargs: dict[str, Any] = {
            "hostname": self.host,
            "port": self.port,
            "username": self.username,
            "timeout": 20,
            "banner_timeout": 20,
            "auth_timeout": 20,
        }
        if self.private_key:
            kwargs["pkey"] = self.paramiko.RSAKey.from_private_key(
                io.StringIO(str(self.private_key)),
                password=self.private_key_password,
            )
        else:
            kwargs["password"] = str(self.password or "")
        try:
            client.connect(**kwargs)
        except self.paramiko.BadHostKeyException as exc:
            raise StorageProviderError(
                "A chave SSH apresentada pelo servidor não corresponde ao known_hosts."
            ) from exc
        except self.paramiko.SSHException as exc:
            raise StorageProviderError("Não foi possível estabelecer uma sessão SFTP validada.") from exc
        return client

    def _mkdirs(self, sftp, path: str) -> None:
        current = ""
        for part in path.strip("/").split("/"):
            current += "/" + part
            try:
                sftp.stat(current)
            except OSError:
                sftp.mkdir(current)

    def test(self) -> dict[str, Any]:
        client = self._connect()
        try:
            sftp = client.open_sftp()
            self._mkdirs(sftp, self.base)
            sftp.close()
            return {"host": self.host, "base_path": self.base, "ok": True}
        finally:
            client.close()

    def upload(self, local_path: Path, remote_key: str) -> str:
        remote = f"{self.base}/{remote_key}".replace("//", "/")
        client = self._connect()
        try:
            sftp = client.open_sftp()
            self._mkdirs(sftp, remote.rsplit("/", 1)[0])
            sftp.put(str(local_path), remote)
            sftp.close()
            return f"sftp://{self.host}:{self.port}{remote}"
        finally:
            client.close()

    def download(self, location: str, local_path: Path) -> Path:
        remote = location.removeprefix(f"sftp://{self.host}:{self.port}")
        client = self._connect()
        try:
            sftp = client.open_sftp()
            local_path.parent.mkdir(parents=True, exist_ok=True)
            sftp.get(remote, str(local_path))
            sftp.close()
            return local_path
        finally:
            client.close()

    def delete(self, location: str) -> None:
        remote = location.removeprefix(f"sftp://{self.host}:{self.port}")
        client = self._connect()
        try:
            sftp = client.open_sftp()
            sftp.remove(remote)
            sftp.close()
        finally:
            client.close()


def build_storage_adapter(provider: StorageProvider) -> StorageAdapter:
    secret = SecretStore().decrypt_dict(provider.secret_encrypted)
    if provider.kind == "local":
        return LocalStorageAdapter(provider.config)
    if provider.kind == "s3":
        return S3StorageAdapter(provider.config, secret)
    if provider.kind == "minio":
        return S3StorageAdapter(provider.config, secret, minio=True)
    if provider.kind == "dropbox":
        return DropboxStorageAdapter(provider.config, secret)
    if provider.kind == "google_drive":
        return GoogleDriveStorageAdapter(provider.config, secret)
    if provider.kind == "sftp":
        return SFTPStorageAdapter(provider.config, secret)
    raise StorageProviderError(f"Provider não suportado: {provider.kind}")
