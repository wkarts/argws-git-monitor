from __future__ import annotations

import io
import json
import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Iterator

import httpx

from app.models.platform import StorageProvider
from app.services.secret_store import SecretStore
from app.services.ssh_security import configure_ssh_host_keys


class StorageProviderError(RuntimeError):
    pass


def _file_chunks(path: Path, chunk_size: int = 8 * 1024 * 1024) -> Iterator[bytes]:
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            yield chunk


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
        del minio
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
    SIMPLE_UPLOAD_LIMIT = 140 * 1024 * 1024
    CHUNK_SIZE = 8 * 1024 * 1024

    def __init__(self, config: dict[str, Any], secret: dict[str, Any]) -> None:
        self.token = str(secret.get("access_token") or "")
        self.refresh_token = str(secret.get("refresh_token") or "")
        self.client_id = str(secret.get("client_id") or config.get("client_id") or "")
        self.client_secret = str(secret.get("client_secret") or "")
        self.base = "/" + str(config.get("base_path") or "argws-git-monitor").strip("/")
        if not self.token and not (self.refresh_token and self.client_id and self.client_secret):
            raise StorageProviderError(
                "Informe access_token ou refresh_token + client_id + client_secret do Dropbox."
            )

    def _access_token(self) -> str:
        if self.refresh_token:
            response = httpx.post(
                "https://api.dropboxapi.com/oauth2/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                timeout=30,
            )
            if not response.is_success:
                raise StorageProviderError(
                    f"Dropbox não renovou a credencial: HTTP {response.status_code}."
                )
            token = str(response.json().get("access_token") or "")
            if not token:
                raise StorageProviderError("Dropbox não retornou access_token na renovação.")
            return token
        return self.token

    def _headers(self, *, api_arg: dict[str, Any] | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._access_token()}"}
        if api_arg is not None:
            headers["Content-Type"] = "application/octet-stream"
            headers["Dropbox-API-Arg"] = json.dumps(api_arg, separators=(",", ":"))
        return headers

    def test(self) -> dict[str, Any]:
        response = httpx.post(
            "https://api.dropboxapi.com/2/users/get_current_account",
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()
        return {"account_id": response.json().get("account_id"), "ok": True, "oauth_refresh": bool(self.refresh_token)}

    def _simple_upload(self, local_path: Path, path: str) -> None:
        response = httpx.post(
            "https://content.dropboxapi.com/2/files/upload",
            headers=self._headers(api_arg={"path": path, "mode": "overwrite", "autorename": False}),
            content=_file_chunks(local_path, self.CHUNK_SIZE),
            timeout=600,
        )
        response.raise_for_status()

    def _session_upload(self, local_path: Path, path: str) -> None:
        token = self._access_token()
        auth = {"Authorization": f"Bearer {token}", "Content-Type": "application/octet-stream"}
        size = local_path.stat().st_size
        with local_path.open("rb") as stream:
            first = stream.read(self.CHUNK_SIZE)
            response = httpx.post(
                "https://content.dropboxapi.com/2/files/upload_session/start",
                headers={
                    **auth,
                    "Dropbox-API-Arg": json.dumps({"close": False}, separators=(",", ":")),
                },
                content=first,
                timeout=300,
            )
            response.raise_for_status()
            session_id = str(response.json().get("session_id") or "")
            if not session_id:
                raise StorageProviderError("Dropbox não retornou upload session id.")
            offset = len(first)
            while offset < size:
                chunk = stream.read(self.CHUNK_SIZE)
                if not chunk:
                    break
                final = offset + len(chunk) >= size
                cursor = {"session_id": session_id, "offset": offset}
                if final:
                    response = httpx.post(
                        "https://content.dropboxapi.com/2/files/upload_session/finish",
                        headers={
                            **auth,
                            "Dropbox-API-Arg": json.dumps(
                                {
                                    "cursor": cursor,
                                    "commit": {
                                        "path": path,
                                        "mode": "overwrite",
                                        "autorename": False,
                                        "mute": True,
                                    },
                                },
                                separators=(",", ":"),
                            ),
                        },
                        content=chunk,
                        timeout=600,
                    )
                else:
                    response = httpx.post(
                        "https://content.dropboxapi.com/2/files/upload_session/append_v2",
                        headers={
                            **auth,
                            "Dropbox-API-Arg": json.dumps(
                                {"cursor": cursor, "close": False}, separators=(",", ":")
                            ),
                        },
                        content=chunk,
                        timeout=600,
                    )
                response.raise_for_status()
                offset += len(chunk)

    def upload(self, local_path: Path, remote_key: str) -> str:
        path = f"{self.base}/{remote_key}".replace("//", "/")
        if local_path.stat().st_size <= self.SIMPLE_UPLOAD_LIMIT:
            self._simple_upload(local_path, path)
        else:
            self._session_upload(local_path, path)
        return f"dropbox:{path}"

    def download(self, location: str, local_path: Path) -> Path:
        path = location.removeprefix("dropbox:")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream(
            "POST",
            "https://content.dropboxapi.com/2/files/download",
            headers=self._headers(api_arg={"path": path}),
            timeout=600,
        ) as response:
            response.raise_for_status()
            with local_path.open("wb") as stream:
                for chunk in response.iter_bytes(self.CHUNK_SIZE):
                    stream.write(chunk)
        return local_path

    def delete(self, location: str) -> None:
        path = location.removeprefix("dropbox:")
        response = httpx.post(
            "https://api.dropboxapi.com/2/files/delete_v2",
            headers={**self._headers(), "Content-Type": "application/json"},
            json={"path": path},
            timeout=30,
        )
        response.raise_for_status()


class GoogleDriveStorageAdapter(StorageAdapter):
    CHUNK_SIZE = 8 * 1024 * 1024

    def __init__(self, config: dict[str, Any], secret: dict[str, Any]) -> None:
        self.token = str(secret.get("access_token") or "")
        self.refresh_token = str(secret.get("refresh_token") or "")
        self.client_id = str(secret.get("client_id") or config.get("client_id") or "")
        self.client_secret = str(secret.get("client_secret") or "")
        self.folder_id = str(config.get("folder_id") or "")
        if not self.token and not (self.refresh_token and self.client_id and self.client_secret):
            raise StorageProviderError(
                "Informe access_token ou refresh_token + client_id + client_secret do Google Drive."
            )

    def _access_token(self) -> str:
        if self.refresh_token:
            response = httpx.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                timeout=30,
            )
            if not response.is_success:
                raise StorageProviderError(
                    f"Google Drive não renovou a credencial: HTTP {response.status_code}."
                )
            token = str(response.json().get("access_token") or "")
            if not token:
                raise StorageProviderError("Google Drive não retornou access_token na renovação.")
            return token
        return self.token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token()}"}

    def test(self) -> dict[str, Any]:
        response = httpx.get(
            "https://www.googleapis.com/drive/v3/about",
            headers=self._headers(),
            params={"fields": "user,storageQuota"},
            timeout=30,
        )
        response.raise_for_status()
        return {"user": response.json().get("user"), "ok": True, "oauth_refresh": bool(self.refresh_token)}

    def upload(self, local_path: Path, remote_key: str) -> str:
        metadata: dict[str, Any] = {"name": remote_key.replace("/", "__")}
        if self.folder_id:
            metadata["parents"] = [self.folder_id]
        size = local_path.stat().st_size
        token = self._access_token()
        start = httpx.post(
            "https://www.googleapis.com/upload/drive/v3/files",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": "application/octet-stream",
                "X-Upload-Content-Length": str(size),
            },
            params={"uploadType": "resumable", "fields": "id,name,size,md5Checksum"},
            json=metadata,
            timeout=60,
        )
        start.raise_for_status()
        session_url = start.headers.get("location")
        if not session_url:
            raise StorageProviderError("Google Drive não retornou URL de upload resumível.")

        result: dict[str, Any] = {}
        with local_path.open("rb") as stream:
            offset = 0
            while offset < size:
                chunk = stream.read(self.CHUNK_SIZE)
                if not chunk:
                    break
                end = offset + len(chunk) - 1
                response = httpx.put(
                    session_url,
                    headers={
                        "Content-Type": "application/octet-stream",
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {offset}-{end}/{size}",
                    },
                    content=chunk,
                    timeout=600,
                )
                if response.status_code not in {200, 201, 308}:
                    response.raise_for_status()
                if response.status_code in {200, 201}:
                    result = response.json()
                offset = end + 1
        file_id = str(result.get("id") or "")
        if not file_id:
            raise StorageProviderError("Google Drive não confirmou o arquivo após upload resumível.")
        return f"gdrive:{file_id}"

    def download(self, location: str, local_path: Path) -> Path:
        file_id = location.removeprefix("gdrive:")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream(
            "GET",
            f"https://www.googleapis.com/drive/v3/files/{file_id}",
            headers=self._headers(),
            params={"alt": "media"},
            timeout=600,
        ) as response:
            response.raise_for_status()
            with local_path.open("wb") as stream:
                for chunk in response.iter_bytes(self.CHUNK_SIZE):
                    stream.write(chunk)
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
