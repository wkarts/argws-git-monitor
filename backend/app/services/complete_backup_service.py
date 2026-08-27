from __future__ import annotations

import json
import tarfile
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import EncryptionService
from app.models.github import GitHubConnection, Repository
from app.models.platform import BackupSnapshot, BackupStatus, BackupType, StorageProvider
from app.services.backup_service import create_backup, sha256_file
from app.services.github_client import GitHubAPIError, GitHubClient
from app.services.storage_providers import build_storage_adapter


class CompleteBackupError(RuntimeError):
    pass


def _write_json(root: Path, relative: str, payload: Any) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


async def _safe_json(
    client: GitHubClient,
    path: str,
    *,
    warnings: list[str],
    label: str,
) -> Any:
    try:
        return await client.get_json(path)
    except GitHubAPIError as exc:
        if exc.status_code in {403, 404, 410, 451}:
            warnings.append(f"{label}: {exc}")
            return None
        raise


async def _safe_paginate(
    client: GitHubClient,
    path: str,
    *,
    warnings: list[str],
    label: str,
    params: dict[str, Any] | None = None,
    limit: int = 5000,
) -> list[dict[str, Any]]:
    try:
        return await client.paginate(path, params=params, limit=limit)
    except GitHubAPIError as exc:
        if exc.status_code in {403, 404, 410, 451}:
            warnings.append(f"{label}: {exc}")
            return []
        raise


async def _stream_download(
    http: httpx.AsyncClient,
    path: str,
    destination: Path,
    *,
    warnings: list[str],
    label: str,
) -> int:
    try:
        async with http.stream("GET", path) as response:
            if response.status_code in {403, 404, 410, 451}:
                warnings.append(f"{label}: HTTP {response.status_code}")
                return 0
            response.raise_for_status()
            destination.parent.mkdir(parents=True, exist_ok=True)
            size = 0
            with destination.open("wb") as stream:
                async for chunk in response.aiter_bytes(1024 * 1024):
                    stream.write(chunk)
                    size += len(chunk)
            return size
    except httpx.HTTPError as exc:
        warnings.append(f"{label}: {type(exc).__name__}")
        return 0


async def _export_github_sidecar(
    *,
    repository: Repository,
    connection: GitHubConnection,
    token: str,
    root: Path,
) -> tuple[Path, dict[str, Any]]:
    export = root / "github-export"
    metadata = export / "metadata"
    actions = export / "actions"
    warnings: list[str] = []
    object_count = 0
    downloaded_bytes = 0
    full_name = repository.full_name

    async with GitHubClient(token, api_url=connection.api_url) as client:
        repository_payload = await _safe_json(
            client,
            f"/repos/{full_name}",
            warnings=warnings,
            label="repository",
        )
        _write_json(metadata, "repository.json", repository_payload)
        object_count += 1 if repository_payload else 0

        collections: list[tuple[str, str, dict[str, Any] | None]] = [
            ("branches", f"/repos/{full_name}/branches", None),
            ("tags", f"/repos/{full_name}/tags", None),
            ("pull_requests", f"/repos/{full_name}/pulls", {"state": "all", "sort": "updated", "direction": "desc"}),
            ("issues_raw", f"/repos/{full_name}/issues", {"state": "all", "sort": "updated", "direction": "desc"}),
            ("issue_comments", f"/repos/{full_name}/issues/comments", {"sort": "updated", "direction": "desc"}),
            ("review_comments", f"/repos/{full_name}/pulls/comments", {"sort": "updated", "direction": "desc"}),
            ("labels", f"/repos/{full_name}/labels", None),
            ("milestones", f"/repos/{full_name}/milestones", {"state": "all"}),
            ("workflows", f"/repos/{full_name}/actions/workflows", None),
            ("workflow_runs", f"/repos/{full_name}/actions/runs", None),
            ("artifacts", f"/repos/{full_name}/actions/artifacts", None),
        ]
        collected: dict[str, list[dict[str, Any]]] = {}
        for name, path, params in collections:
            items = await _safe_paginate(
                client,
                path,
                warnings=warnings,
                label=name,
                params=params,
            )
            collected[name] = items
            _write_json(metadata, f"{name}.json", items)
            object_count += len(items)

        pulls = collected.get("pull_requests", [])
        reviews: dict[str, list[dict[str, Any]]] = {}
        for pull in pulls:
            number = pull.get("number")
            if not number:
                continue
            items = await _safe_paginate(
                client,
                f"/repos/{full_name}/pulls/{number}/reviews",
                warnings=warnings,
                label=f"reviews PR #{number}",
                limit=1000,
            )
            reviews[str(number)] = items
            object_count += len(items)
        _write_json(metadata, "pull_request_reviews.json", reviews)

        issues = [item for item in collected.get("issues_raw", []) if not item.get("pull_request")]
        _write_json(metadata, "issues.json", issues)

        settings_payload: dict[str, Any] = {}
        for name, path in (
            ("actions_permissions", f"/repos/{full_name}/actions/permissions"),
            ("rulesets", f"/repos/{full_name}/rulesets"),
            ("environments", f"/repos/{full_name}/environments"),
            ("actions_secrets", f"/repos/{full_name}/actions/secrets"),
            ("actions_variables", f"/repos/{full_name}/actions/variables"),
            ("hooks", f"/repos/{full_name}/hooks"),
        ):
            settings_payload[name] = await _safe_json(
                client,
                path,
                warnings=warnings,
                label=name,
            )
        protection = await _safe_json(
            client,
            f"/repos/{full_name}/branches/{repository.default_branch}/protection",
            warnings=warnings,
            label=f"branch protection {repository.default_branch}",
        )
        settings_payload["default_branch_protection"] = protection
        _write_json(metadata, "repository_settings.json", settings_payload)

        runs = collected.get("workflow_runs", [])
        jobs_by_run: dict[str, list[dict[str, Any]]] = {}
        for run in runs:
            run_id = run.get("id")
            if not run_id:
                continue
            jobs = await _safe_paginate(
                client,
                f"/repos/{full_name}/actions/runs/{run_id}/jobs",
                warnings=warnings,
                label=f"jobs run {run_id}",
                limit=1000,
            )
            jobs_by_run[str(run_id)] = jobs
            object_count += len(jobs)
        _write_json(metadata, "workflow_jobs.json", jobs_by_run)

        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ARGWS-Git-Monitor/complete-backup",
        }
        async with httpx.AsyncClient(
            base_url=connection.api_url.rstrip("/"),
            headers=headers,
            follow_redirects=True,
            timeout=httpx.Timeout(600),
        ) as http:
            artifact_manifest: list[dict[str, Any]] = []
            for artifact in collected.get("artifacts", []):
                artifact_id = artifact.get("id")
                name = str(artifact.get("name") or f"artifact-{artifact_id}")
                entry = {
                    "id": artifact_id,
                    "name": name,
                    "expired": bool(artifact.get("expired")),
                    "size_in_bytes": artifact.get("size_in_bytes"),
                    "workflow_run": artifact.get("workflow_run"),
                    "archive": None,
                }
                if artifact_id and not entry["expired"]:
                    filename = f"{artifact_id}-{Path(name).name}.zip"
                    destination = actions / "artifacts" / filename
                    size = await _stream_download(
                        http,
                        f"/repos/{full_name}/actions/artifacts/{artifact_id}/zip",
                        destination,
                        warnings=warnings,
                        label=f"artifact {artifact_id}",
                    )
                    if size:
                        downloaded_bytes += size
                        entry["archive"] = {
                            "path": str(destination.relative_to(export)),
                            "size_bytes": size,
                            "sha256": sha256_file(destination),
                        }
                artifact_manifest.append(entry)
            _write_json(metadata, "artifact_manifest.json", artifact_manifest)

            log_manifest: list[dict[str, Any]] = []
            for run in runs:
                run_id = run.get("id")
                if not run_id:
                    continue
                destination = actions / "run-logs" / f"{run_id}.zip"
                size = await _stream_download(
                    http,
                    f"/repos/{full_name}/actions/runs/{run_id}/logs",
                    destination,
                    warnings=warnings,
                    label=f"logs run {run_id}",
                )
                if size:
                    downloaded_bytes += size
                    log_manifest.append(
                        {
                            "run_id": run_id,
                            "path": str(destination.relative_to(export)),
                            "size_bytes": size,
                            "sha256": sha256_file(destination),
                        }
                    )
            _write_json(metadata, "workflow_log_manifest.json", log_manifest)

    export_manifest = {
        "format": "argws-git-monitor-github-export-v2",
        "repository": full_name,
        "github_id": repository.github_id,
        "created_at": datetime.now(UTC).isoformat(),
        "object_count": object_count,
        "downloaded_bytes": downloaded_bytes,
        "warnings": warnings,
        "coverage": {
            "git_objects": "stored_in_primary_snapshot",
            "branches_tags": True,
            "pull_requests": True,
            "pull_request_reviews": True,
            "issues": True,
            "issue_comments": True,
            "review_comments": True,
            "labels_milestones": True,
            "repository_settings": True,
            "workflow_definitions": "stored_in_git_plus_metadata",
            "workflow_runs_jobs": True,
            "workflow_logs_available_at_backup_time": True,
            "workflow_artifacts_available_at_backup_time": True,
            "releases_assets": "stored_in_primary_snapshot",
            "secret_names": True,
            "secret_values": False,
        },
        "restore_capabilities": {
            "exact": ["git refs", "branches", "tags", "release assets archived"],
            "recreatable": ["repository", "releases", "issues", "pull requests", "labels", "milestones"],
            "archive_only": ["historical workflow run ids", "historical logs", "historical artifacts"],
            "unavailable_by_github_api": ["secret values"],
        },
    }
    _write_json(export, "manifest.json", export_manifest)

    archive = root / f"github-export-{repository.owner}-{repository.name}-{uuid.uuid4()}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(export, arcname="github-export")
    return archive, export_manifest


async def create_complete_backup(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    repository_id: uuid.UUID,
    provider_id: uuid.UUID,
    permanent: bool = True,
    job_id: uuid.UUID | None = None,
) -> BackupSnapshot:
    repository = await session.get(Repository, repository_id)
    provider = await session.get(StorageProvider, provider_id)
    if not repository:
        raise CompleteBackupError("Repositório não encontrado.")
    if not provider or provider.user_id != user_id or not provider.enabled:
        raise CompleteBackupError("Provider de armazenamento inválido ou desativado.")
    connection = await session.get(GitHubConnection, repository.connection_id)
    if not connection or connection.user_id != user_id or not connection.token_encrypted:
        raise CompleteBackupError("Conexão GitHub inválida para o backup completo.")

    snapshot = await create_backup(
        session,
        user_id=user_id,
        repository_id=repository_id,
        provider_id=provider_id,
        backup_type=BackupType.FULL.value,
        branches=[],
        include_releases=True,
        include_release_assets=True,
        include_lfs=True,
        include_submodules=True,
        permanent=permanent,
        policy_id=None,
        job_id=job_id,
    )

    token = EncryptionService().decrypt(connection.token_encrypted)
    try:
        with tempfile.TemporaryDirectory(prefix="argws-complete-export-") as temp:
            root = Path(temp)
            archive, export_manifest = await _export_github_sidecar(
                repository=repository,
                connection=connection,
                token=token,
                root=root,
            )
            checksum = sha256_file(archive)
            remote_key = (
                f"{repository.owner}/{repository.name}/"
                f"{datetime.now(UTC).strftime('%Y/%m/%d')}/complete/{archive.name}"
            )
            location = build_storage_adapter(provider).upload(archive, remote_key)
            manifest = dict(snapshot.manifest or {})
            warnings = list(manifest.get("warnings") or [])
            warnings.extend(export_manifest.get("warnings") or [])
            manifest["format"] = "argws-git-monitor-backup-v2"
            manifest["warnings"] = warnings
            manifest["github_complete_export"] = {
                **export_manifest,
                "location": location,
                "size_bytes": archive.stat().st_size,
                "checksum_sha256": checksum,
            }
            snapshot.manifest = manifest
            snapshot.object_count = int(snapshot.object_count or 0) + int(
                export_manifest.get("object_count") or 0
            )
            snapshot.status = (
                BackupStatus.COMPLETED_WITH_WARNINGS.value
                if warnings
                else BackupStatus.COMPLETED.value
            )
            await session.flush()
    except Exception as exc:
        manifest = dict(snapshot.manifest or {})
        warnings = list(manifest.get("warnings") or [])
        warnings.append(f"Exportação GitHub completa falhou: {type(exc).__name__}: {exc}")
        manifest["warnings"] = warnings
        manifest["github_complete_export"] = {"status": "failed"}
        snapshot.manifest = manifest
        snapshot.status = BackupStatus.COMPLETED_WITH_WARNINGS.value
        await session.flush()
        raise CompleteBackupError(
            "O snapshot Git foi criado, mas a exportação completa de metadados falhou."
        ) from exc

    return snapshot
