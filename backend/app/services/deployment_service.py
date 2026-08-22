from __future__ import annotations

import io
import logging
import shlex
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.github import Repository
from app.models.platform import DeploymentRecord, DeploymentTarget, OperationStatus
from app.services.secret_store import SecretStore
from app.services.ssh_security import configure_ssh_host_keys

logger = logging.getLogger(__name__)


class DeploymentError(RuntimeError):
    pass


def _require_paramiko():
    try:
        import paramiko
    except ImportError as exc:
        raise DeploymentError("paramiko não está instalado na imagem do worker.") from exc
    return paramiko


def _public_error(exc: Exception) -> str:
    if isinstance(exc, DeploymentError):
        return str(exc)[:1000]
    return "Falha interna durante o deployment. Consulte a Central de Logs pelo correlation ID."


class RemoteSession:
    def __init__(self, target: DeploymentTarget) -> None:
        self.paramiko = _require_paramiko()
        secret = SecretStore().decrypt_dict(target.secret_encrypted)
        client = self.paramiko.SSHClient()
        configure_ssh_host_keys(
            client,
            self.paramiko,
            config=target.config or {},
            secret=secret,
            error_type=DeploymentError,
        )
        kwargs: dict[str, Any] = {
            "hostname": target.host,
            "port": target.port,
            "username": target.username,
            "timeout": 20,
            "banner_timeout": 20,
            "auth_timeout": 20,
        }
        if secret.get("private_key"):
            kwargs["pkey"] = self.paramiko.RSAKey.from_private_key(
                io.StringIO(str(secret["private_key"])),
                password=secret.get("private_key_password"),
            )
        elif secret.get("password"):
            kwargs["password"] = str(secret["password"])
        else:
            raise DeploymentError("O Deployment Target não possui senha nem chave privada.")
        try:
            client.connect(**kwargs)
        except self.paramiko.BadHostKeyException as exc:
            raise DeploymentError("A chave SSH apresentada pelo servidor não corresponde ao known_hosts.") from exc
        except self.paramiko.SSHException as exc:
            raise DeploymentError("Não foi possível estabelecer uma sessão SSH validada.") from exc
        self.client = client

    def close(self) -> None:
        self.client.close()

    def run(self, command: str, *, timeout: int = 900) -> dict[str, Any]:
        _, stdout, stderr = self.client.exec_command(command, timeout=timeout)
        code = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        result = {
            "command": command,
            "exit_code": code,
            "stdout": out[-12000:],
            "stderr": err[-12000:],
        }
        if code:
            logger.warning("Comando remoto de deployment falhou com exit_code=%s", code)
            raise DeploymentError(f"Comando remoto falhou com código de saída {code}.")
        return result


def _step(name: str, status: str = "pending", **extra: Any) -> dict[str, Any]:
    return {"name": name, "status": status, **extra}


async def test_target(target: DeploymentTarget) -> dict[str, Any]:
    remote = RemoteSession(target)
    try:
        return {
            "ok": True,
            "message": "SSH conectado com chave de host validada.",
            "details": remote.run("printf 'ARGWS_OK' && uname -a", timeout=30),
        }
    finally:
        remote.close()


async def _healthcheck(url: str | None) -> dict[str, Any]:
    if not url:
        return {"configured": False, "ok": True}
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(url)
        return {
            "configured": True,
            "ok": 200 <= response.status_code < 400,
            "status_code": response.status_code,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
        }
    except Exception as exc:
        logger.warning("Healthcheck remoto falhou: %s", type(exc).__name__)
        return {
            "configured": True,
            "ok": False,
            "error": "healthcheck_request_failed",
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
        }


async def deploy(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    target_id: uuid.UUID,
    repository_id: uuid.UUID,
    ref: str,
    release_url: str | None,
    checksum_sha256: str | None,
    job_id: uuid.UUID | None = None,
) -> DeploymentRecord:
    target = await session.get(DeploymentTarget, target_id)
    repository = await session.get(Repository, repository_id)
    if not target or target.user_id != user_id or not target.enabled:
        raise DeploymentError("Deployment Target inválido ou desativado.")
    if not repository:
        raise DeploymentError("Repositório não encontrado.")
    if target.repository_id and target.repository_id != repository_id:
        raise DeploymentError("Este target está vinculado a outro repositório.")

    record = DeploymentRecord(
        user_id=user_id,
        target_id=target.id,
        repository_id=repository.id,
        job_id=job_id,
        status=OperationStatus.RUNNING.value,
        requested_ref=ref,
        previous_version={},
        deployed_version={},
        pipeline=[],
        health_result={},
        created_at=datetime.now(UTC),
        started_at=datetime.now(UTC),
    )
    session.add(record)
    await session.flush()

    pipeline = [
        _step("Connect SSH"),
        _step("Capture current version"),
        _step("Backup current release/configuration"),
        _step("Fetch/install requested version"),
        _step("Run configured commands"),
        _step("Restart/recreate application"),
        _step("Health check"),
    ]
    record.pipeline = pipeline
    await session.flush()

    remote = RemoteSession(target)
    workdir = shlex.quote(target.working_directory)
    config = target.config or {}
    try:
        pipeline[0].update(status="completed", finished_at=datetime.now(UTC).isoformat())
        if target.strategy == "git":
            current = remote.run(f"cd {workdir} && git rev-parse HEAD && git status --porcelain=v1")
            record.previous_version = {
                "git_sha": (current["stdout"].splitlines() or [""])[0].strip()
            }
        elif target.strategy == "docker_compose":
            current = remote.run(
                f"cd {workdir} && docker compose images --format json 2>/dev/null || docker compose images"
            )
            record.previous_version = {"compose_images": current["stdout"]}
        else:
            record.previous_version = {
                "directory_listing": remote.run(f"cd {workdir} && ls -la")["stdout"]
            }
        pipeline[1].update(status="completed", finished_at=datetime.now(UTC).isoformat())

        backup_command = str(config.get("backup_command") or "").strip()
        if backup_command:
            record.previous_version["backup_output"] = remote.run(
                f"cd {workdir} && {backup_command}", timeout=1800
            )["stdout"]
        pipeline[2].update(status="completed", finished_at=datetime.now(UTC).isoformat())

        if target.strategy == "git":
            remote.run(f"cd {workdir} && git fetch --all --tags --prune", timeout=900)
            remote.run(f"cd {workdir} && git checkout --force {shlex.quote(ref)}", timeout=300)
            remote.run(f"cd {workdir} && git submodule update --init --recursive", timeout=900)
            record.deployed_version = {"git_ref": ref}
        elif target.strategy == "release":
            if not release_url:
                raise DeploymentError("release_url é obrigatório para strategy=release.")
            archive = f".argws-release-{record.id}.tgz"
            remote.run(
                f"cd {workdir} && curl -fL --retry 3 {shlex.quote(release_url)} -o {shlex.quote(archive)}",
                timeout=1800,
            )
            if checksum_sha256:
                remote.run(
                    f"cd {workdir} && printf '%s  %s\n' {shlex.quote(checksum_sha256)} {shlex.quote(archive)} | sha256sum -c -"
                )
            release_dir = shlex.quote(f".argws-release-{record.id}")
            remote.run(
                f"cd {workdir} && mkdir -p {release_dir} && tar -xzf {shlex.quote(archive)} -C {release_dir}",
                timeout=900,
            )
            install_command = str(config.get("install_command") or "")
            if install_command:
                remote.run(f"cd {workdir} && {install_command}", timeout=1800)
            record.deployed_version = {
                "release_url": release_url,
                "checksum_sha256": checksum_sha256,
            }
        elif target.strategy == "docker_compose":
            compose_file = str(config.get("compose_file") or "compose.yaml")
            compose_arg = f"-f {shlex.quote(compose_file)}"
            remote.run(f"cd {workdir} && docker compose {compose_arg} pull", timeout=1800)
            remote.run(
                f"cd {workdir} && docker compose {compose_arg} up -d --no-build --force-recreate --remove-orphans",
                timeout=1800,
            )
            record.deployed_version = {"ref": ref, "compose_file": compose_file}
        else:
            raise DeploymentError(f"Estratégia de deploy não suportada: {target.strategy}")
        pipeline[3].update(status="completed", finished_at=datetime.now(UTC).isoformat())

        outputs = [
            remote.run(f"cd {workdir} && {command}", timeout=1800)
            for command in list(config.get("commands") or [])
        ]
        if outputs:
            record.deployed_version["command_outputs"] = outputs
        pipeline[4].update(status="completed", finished_at=datetime.now(UTC).isoformat())

        restart_command = str(config.get("restart_command") or "").strip()
        if restart_command:
            remote.run(f"cd {workdir} && {restart_command}", timeout=900)
        pipeline[5].update(status="completed", finished_at=datetime.now(UTC).isoformat())

        health = await _healthcheck(target.healthcheck_url)
        record.health_result = health
        if not health.get("ok"):
            pipeline[6].update(
                status="failed",
                finished_at=datetime.now(UTC).isoformat(),
                result=health,
            )
            record.status = OperationStatus.COMPLETED_WITH_WARNINGS.value
        else:
            pipeline[6].update(
                status="completed",
                finished_at=datetime.now(UTC).isoformat(),
                result=health,
            )
            record.status = OperationStatus.COMPLETED.value
        record.pipeline = pipeline
        record.completed_at = datetime.now(UTC)
        await session.flush()
        return record
    except Exception as exc:
        for item in pipeline:
            if item["status"] == "pending":
                item["status"] = "skipped"
        record.pipeline = pipeline
        record.status = OperationStatus.FAILED.value
        record.error = _public_error(exc)
        record.completed_at = datetime.now(UTC)
        await session.flush()
        raise
    finally:
        remote.close()


async def rollback(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    deployment_id: uuid.UUID,
    confirmation: str,
) -> DeploymentRecord:
    record = await session.get(DeploymentRecord, deployment_id)
    if not record or record.user_id != user_id:
        raise DeploymentError("Deployment não encontrado.")
    target = await session.get(DeploymentTarget, record.target_id)
    if not target:
        raise DeploymentError("Target não encontrado.")
    expected = f"ROLLBACK {record.id}"
    if confirmation != expected:
        raise DeploymentError(f"Confirmação inválida. Digite exatamente: {expected}")

    remote = RemoteSession(target)
    workdir = shlex.quote(target.working_directory)
    try:
        if target.strategy == "git":
            previous = str(record.previous_version.get("git_sha") or "")
            if not previous:
                raise DeploymentError("Deployment não registrou SHA anterior.")
            remote.run(f"cd {workdir} && git checkout --force {shlex.quote(previous)}")
        else:
            rollback_command = str(target.config.get("rollback_command") or "").strip()
            if not rollback_command:
                raise DeploymentError(
                    "Rollback Docker/Release exige rollback_command explícito; "
                    "rollback automático cego não é seguro."
                )
            remote.run(f"cd {workdir} && {rollback_command}", timeout=1800)
        health = await _healthcheck(target.healthcheck_url)
        record.health_result = {**record.health_result, "rollback": health}
        record.status = OperationStatus.ROLLED_BACK.value
        record.completed_at = datetime.now(UTC)
        await session.flush()
        return record
    finally:
        remote.close()
