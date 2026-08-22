from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import subprocess
import tarfile
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import EncryptionService
from app.models.github import GitHubConnection, Repository
from app.models.platform import BackupPolicy, BackupSnapshot, BackupStatus, BackupType, StorageProvider
from app.services.github_client import GitHubClient
from app.services.storage_providers import build_storage_adapter


class BackupError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_env(token: str) -> dict[str, str]:
    import base64

    credentials = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    env = os.environ.copy()
    env.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.extraHeader",
            "GIT_CONFIG_VALUE_0": f"Authorization: Basic {credentials}",
        }
    )
    return env


def _run(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 1800,
) -> str:
    process = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    if process.returncode:
        raise BackupError(f"Comando falhou ({args[0]}): {process.stdout[-6000:]}")
    return process.stdout


def _resolve_selected_branches(mirror: Path, requested: list[str]) -> list[str]:
    output = _run(
        ["git", "for-each-ref", "--format=%(refname:short)", "refs/heads/"],
        cwd=mirror,
    )
    available = sorted({line.strip() for line in output.splitlines() if line.strip()})
    resolved: set[str] = set()
    unmatched: list[str] = []
    for raw_pattern in requested:
        pattern = raw_pattern.removeprefix("refs/heads/").strip()
        matches = [branch for branch in available if fnmatch.fnmatchcase(branch, pattern)]
        if matches:
            resolved.update(matches)
        else:
            unmatched.append(raw_pattern)
    if not resolved:
        raise BackupError(
            "Nenhuma branch corresponde aos padrões selecionados: " + ", ".join(requested)
        )
    if unmatched:
        raise BackupError(
            "Alguns padrões não correspondem a nenhuma branch: " + ", ".join(unmatched)
        )
    return sorted(resolved)


async def _connection_for_repository(
    session: AsyncSession, repository: Repository
) -> GitHubConnection:
    connection = await session.get(GitHubConnection, repository.connection_id)
    if not connection or not connection.token_encrypted:
        raise BackupError("Conexão GitHub sem token operacional.")
    return connection


def _backup_submodules(
    clone_url: str,
    default_branch: str,
    destination: Path,
    *,
    env: dict[str, str],
) -> list[dict[str, str]]:
    working = destination.parent / "submodule-worktree"
    try:
        _run(
            ["git", "clone", "--depth", "1", "--branch", default_branch, clone_url, str(working)],
            env=env,
        )
    except Exception:
        return []
    gitmodules = working / ".gitmodules"
    if not gitmodules.exists():
        return []
    output = _run(
        ["git", "config", "-f", str(gitmodules), "--get-regexp", r"^submodule\..*\.(path|url)$"],
        cwd=working,
    )
    pairs: dict[str, dict[str, str]] = {}
    for line in output.splitlines():
        try:
            key, value = line.split(None, 1)
        except ValueError:
            continue
        parts = key.split(".")
        if len(parts) < 3:
            continue
        name = ".".join(parts[1:-1])
        pairs.setdefault(name, {})[parts[-1]] = value.strip()
    destination.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, str]] = []
    for name, data in pairs.items():
        url = data.get("url", "")
        path = data.get("path", name)
        if not url:
            continue
        if url.startswith("../") or url.startswith("./"):
            owner_base = clone_url.removesuffix(".git").rstrip("/").rsplit("/", 1)[0]
            url = owner_base + "/" + url.split("/")[-1]
            if not url.endswith(".git"):
                url += ".git"
        mirror = destination.parent / f"submodule-{len(manifest)}.git"
        bundle = destination / f"{len(manifest):03d}-{Path(path).name}.bundle"
        try:
            _run(["git", "clone", "--mirror", url, str(mirror)], env=env)
            _run(["git", "bundle", "create", str(bundle), "--all"], cwd=mirror)
            _run(["git", "bundle", "verify", str(bundle)], cwd=mirror)
            manifest.append(
                {"name": name, "path": path, "url": url, "bundle": bundle.name}
            )
        except Exception as exc:
            manifest.append(
                {"name": name, "path": path, "url": url, "error": str(exc)[:1000]}
            )
    return manifest


async def _download_release_assets(
    client: GitHubClient,
    full_name: str,
    destination: Path,
    *,
    include_assets: bool,
    token: str,
) -> tuple[list[dict[str, Any]], int]:
    releases = await client.list_releases(full_name, limit=100)
    manifest: list[dict[str, Any]] = []
    object_count = 0
    destination.mkdir(parents=True, exist_ok=True)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/octet-stream"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(300), follow_redirects=True) as downloader:
        for release in releases:
            tag = str(release.get("tag_name") or "")
            entry = {
                "id": release.get("id"),
                "tag_name": tag,
                "name": release.get("name"),
                "draft": release.get("draft"),
                "prerelease": release.get("prerelease"),
                "published_at": release.get("published_at"),
                "target_commitish": release.get("target_commitish"),
                "body": release.get("body"),
                "html_url": release.get("html_url"),
                "assets": [],
            }
            if include_assets:
                tag_dir = destination / (tag.replace("/", "_") or "untagged")
                tag_dir.mkdir(parents=True, exist_ok=True)
                for asset in release.get("assets") or []:
                    asset_url = asset.get("url")
                    name = str(asset.get("name") or f"asset-{asset.get('id')}")
                    if not asset_url:
                        continue
                    response = await downloader.get(str(asset_url), headers=headers)
                    response.raise_for_status()
                    file_path = tag_dir / Path(name).name
                    file_path.write_bytes(response.content)
                    entry["assets"].append(
                        {
                            "id": asset.get("id"),
                            "name": name,
                            "size": len(response.content),
                            "sha256": sha256_file(file_path),
                            "path": str(file_path.relative_to(destination.parent)),
                        }
                    )
                    object_count += 1
            manifest.append(entry)
            object_count += 1
    return manifest, object_count


async def create_backup(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    repository_id: uuid.UUID,
    provider_id: uuid.UUID,
    backup_type: str,
    branches: list[str] | None = None,
    include_releases: bool = True,
    include_release_assets: bool = True,
    include_lfs: bool = True,
    include_submodules: bool = True,
    permanent: bool = False,
    policy_id: uuid.UUID | None = None,
    job_id: uuid.UUID | None = None,
) -> BackupSnapshot:
    repository = await session.get(Repository, repository_id)
    provider = await session.get(StorageProvider, provider_id)
    if not repository:
        raise BackupError("Repositório não encontrado.")
    connection = await _connection_for_repository(session, repository)
    if connection.user_id != user_id:
        raise BackupError("Repositório não pertence ao usuário autenticado.")
    if not provider or provider.user_id != user_id:
        raise BackupError("Provider de armazenamento não encontrado.")
    token = EncryptionService().decrypt(connection.token_encrypted or "")
    snapshot = BackupSnapshot(
        user_id=user_id,
        policy_id=policy_id,
        repository_id=repository.id,
        provider_id=provider.id,
        job_id=job_id,
        backup_type=backup_type,
        status=BackupStatus.RUNNING.value,
        permanent=permanent,
        manifest={},
        created_at=datetime.now(UTC),
        started_at=datetime.now(UTC),
    )
    session.add(snapshot)
    await session.flush()
    started = time.monotonic()
    warnings: list[str] = []
    resolved_branches: list[str] = []

    with tempfile.TemporaryDirectory(prefix="argws-backup-") as temp:
        root = Path(temp)
        mirror = root / "repository.git"
        bundle = root / "repository.bundle"
        release_dir = root / "releases"
        submodule_dir = root / "submodules"
        manifest_path = root / "manifest.json"
        archive = root / f"{repository.owner}-{repository.name}-{snapshot.id}.tar.gz"
        env = _git_env(token)
        clone_url = f"https://github.com/{repository.full_name}.git"

        if backup_type != BackupType.RELEASES_ONLY.value:
            _run(["git", "clone", "--mirror", clone_url, str(mirror)], env=env)
            if include_lfs:
                try:
                    _run(["git", "lfs", "fetch", "--all"], cwd=mirror, env=env, timeout=3600)
                except Exception as exc:
                    warnings.append(f"Git LFS: {exc}")

            refs = ["--all"]
            requested = [item.strip() for item in (branches or []) if item.strip()]
            if backup_type == BackupType.DEFAULT_BRANCH.value:
                resolved_branches = [repository.default_branch]
                refs = [f"refs/heads/{repository.default_branch}"]
            elif backup_type == BackupType.SELECTED_BRANCHES.value:
                if not requested:
                    raise BackupError("Selecione ao menos uma branch ou padrão.")
                resolved_branches = _resolve_selected_branches(mirror, requested)
                refs = [f"refs/heads/{branch}" for branch in resolved_branches]
            elif backup_type == BackupType.ALL_BRANCHES.value:
                refs = ["--branches"]
            _run(["git", "bundle", "create", str(bundle), *refs], cwd=mirror)
            _run(["git", "bundle", "verify", str(bundle)], cwd=mirror)

            submodules_manifest: list[dict[str, str]] = []
            if include_submodules:
                try:
                    submodules_manifest = _backup_submodules(
                        clone_url, repository.default_branch, submodule_dir, env=env
                    )
                    warnings.extend(
                        f"Submodule {item.get('path')}: {item['error']}"
                        for item in submodules_manifest
                        if item.get("error")
                    )
                except Exception as exc:
                    warnings.append(f"Submodules: {exc}")
        else:
            submodules_manifest = []

        client = GitHubClient(token, api_url=connection.api_url)
        try:
            branches_payload = await client.list_branches(repository.full_name, limit=300)
            tags_payload = await client.optional_paginate(
                "tags",
                f"/repos/{repository.full_name}/tags",
                limit=300,
                empty_statuses={403, 404},
            )
            releases_manifest: list[dict[str, Any]] = []
            release_objects = 0
            if include_releases or backup_type == BackupType.RELEASES_ONLY.value:
                releases_manifest, release_objects = await _download_release_assets(
                    client,
                    repository.full_name,
                    release_dir,
                    include_assets=include_release_assets,
                    token=token,
                )
        finally:
            await client.close()

        branch_names = [str(item.get("name") or "") for item in branches_payload]
        tag_names = [str(item.get("name") or "") for item in tags_payload]
        if backup_type == BackupType.ALL_BRANCHES.value:
            resolved_branches = branch_names
        object_count = len(branch_names) + len(tag_names) + release_objects
        manifest: dict[str, Any] = {
            "format": "argws-git-monitor-backup-v1",
            "snapshot_id": str(snapshot.id),
            "repository": repository.full_name,
            "owner": repository.owner,
            "github_id": repository.github_id,
            "default_branch": repository.default_branch,
            "backup_type": backup_type,
            "requested_branches": branches or [],
            "resolved_branches": resolved_branches,
            "branches": branch_names,
            "tags": tag_names,
            "latest_commit_sha": repository.latest_commit_sha,
            "include_lfs": include_lfs,
            "include_submodules": include_submodules,
            "submodules": submodules_manifest,
            "releases": releases_manifest,
            "provider": {"id": str(provider.id), "name": provider.name, "kind": provider.kind},
            "started_at": snapshot.started_at.isoformat() if snapshot.started_at else None,
            "warnings": warnings,
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(manifest_path, arcname="manifest.json")
            if bundle.exists():
                tar.add(bundle, arcname="repository.bundle")
            if release_dir.exists():
                tar.add(release_dir, arcname="releases")
            if submodule_dir.exists():
                tar.add(submodule_dir, arcname="submodules")

        snapshot.status = BackupStatus.VALIDATING.value
        await session.flush()
        checksum = sha256_file(archive)
        size = archive.stat().st_size
        remote_key = (
            f"{repository.owner}/{repository.name}/"
            f"{datetime.now(UTC).strftime('%Y/%m/%d')}/{archive.name}"
        )
        location = build_storage_adapter(provider).upload(archive, remote_key)
        completed = datetime.now(UTC)
        manifest.update(
            {
                "completed_at": completed.isoformat(),
                "duration_seconds": round(time.monotonic() - started, 3),
                "size_bytes": size,
                "object_count": object_count,
                "checksum_sha256": checksum,
                "location": location,
            }
        )
        snapshot.location = location
        snapshot.checksum_sha256 = checksum
        snapshot.size_bytes = size
        snapshot.object_count = object_count
        snapshot.manifest = manifest
        snapshot.completed_at = completed
        snapshot.status = (
            BackupStatus.COMPLETED_WITH_WARNINGS.value
            if warnings
            else BackupStatus.COMPLETED.value
        )
        if policy_id:
            policy = await session.get(BackupPolicy, policy_id)
            if policy:
                policy.last_run_at = completed
        await session.flush()
        return snapshot


async def apply_retention(session: AsyncSession, policy: BackupPolicy) -> dict[str, int]:
    snapshots = (
        await session.execute(
            select(BackupSnapshot)
            .where(BackupSnapshot.policy_id == policy.id)
            .order_by(BackupSnapshot.created_at.desc())
        )
    ).scalars().all()
    keep_last = max(0, int(policy.retention.get("keep_last") or 0))
    keep_days = max(0, int(policy.retention.get("keep_days") or 0))
    threshold = datetime.now(UTC).timestamp() - keep_days * 86400 if keep_days else None
    deleted = 0
    for index, snapshot in enumerate(snapshots):
        if snapshot.permanent:
            continue
        must_keep = index < keep_last
        if threshold and snapshot.created_at.timestamp() >= threshold:
            must_keep = True
        if must_keep or not snapshot.location:
            continue
        provider = await session.get(StorageProvider, snapshot.provider_id)
        if provider:
            try:
                build_storage_adapter(provider).delete(snapshot.location)
            except Exception:
                continue
        await session.delete(snapshot)
        deleted += 1
    return {"deleted": deleted}
