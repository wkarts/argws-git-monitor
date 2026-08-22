from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class StorageProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    kind: Literal["local", "s3", "minio", "google_drive", "dropbox", "sftp"]
    config: dict[str, Any] = Field(default_factory=dict)
    secret: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class StorageProviderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    config: dict[str, Any] | None = None
    secret: dict[str, Any] | None = None
    enabled: bool | None = None


class StorageProviderRead(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    config: dict[str, Any]
    secret_hint: str | None
    enabled: bool
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class StorageProviderTestResult(BaseModel):
    ok: bool
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class BackupPolicyCreate(BaseModel):
    repository_id: uuid.UUID
    provider_id: uuid.UUID
    name: str = Field(min_length=1, max_length=160)
    backup_type: Literal["full", "default_branch", "selected_branches", "all_branches", "releases_only"] = "full"
    branches: list[str] = Field(default_factory=list)
    include_releases: bool = True
    include_release_assets: bool = True
    include_lfs: bool = True
    include_submodules: bool = True
    schedule_kind: Literal["manual", "interval_hours", "daily", "weekly", "monthly", "event"] = "manual"
    schedule_value: str | None = None
    event_trigger: Literal["release", "push", "workflow_success"] | None = None
    retention: dict[str, Any] = Field(default_factory=lambda: {"keep_last": 10, "keep_days": 30})
    enabled: bool = True


class BackupPolicyRead(BaseModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    provider_id: uuid.UUID
    name: str
    backup_type: str
    branches: list[str]
    include_releases: bool
    include_release_assets: bool
    include_lfs: bool
    include_submodules: bool
    schedule_kind: str
    schedule_value: str | None
    event_trigger: str | None
    retention: dict[str, Any]
    enabled: bool
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class BackupRunRequest(BaseModel):
    repository_id: uuid.UUID | None = None
    provider_id: uuid.UUID | None = None
    backup_type: Literal["full", "default_branch", "selected_branches", "all_branches", "releases_only"] | None = None
    branches: list[str] = Field(default_factory=list)
    permanent: bool = False


class BackupSnapshotRead(BaseModel):
    id: uuid.UUID
    policy_id: uuid.UUID | None
    repository_id: uuid.UUID
    provider_id: uuid.UUID
    job_id: uuid.UUID | None
    backup_type: str
    status: str
    location: str | None
    manifest: dict[str, Any]
    checksum_sha256: str | None
    size_bytes: int | None
    object_count: int | None
    permanent: bool
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}


class RestoreRequest(BaseModel):
    destination: Literal["github_repository", "new_github_repository", "local", "sftp"]
    connection_id: uuid.UUID | None = None
    repository_full_name: str | None = Field(default=None, max_length=520)
    new_repository_name: str | None = Field(default=None, max_length=255)
    branch: str | None = Field(default=None, max_length=255)
    restore_tags: bool = True
    restore_releases: bool = True
    target_path: str | None = Field(default=None, max_length=1000)
    simulate: bool = True
    confirmation: str | None = None


class PublishingChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    kind: Literal["github_release", "github_repository", "s3", "minio", "google_drive", "dropbox", "sftp"]
    storage_provider_id: uuid.UUID | None = None
    repository_id: uuid.UUID | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    secret: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class PublishingChannelRead(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    storage_provider_id: uuid.UUID | None
    repository_id: uuid.UUID | None
    config: dict[str, Any]
    enabled: bool
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ReleaseManagerRequest(BaseModel):
    repository_id: uuid.UUID
    tag_name: str = Field(min_length=1, max_length=255)
    target_commitish: str = Field(min_length=1, max_length=255)
    name: str | None = Field(default=None, max_length=500)
    body: str | None = None
    draft: bool = False
    prerelease: bool = False
    make_latest: bool = True
    create_tag: bool = True
    assets: list[dict[str, Any]] = Field(default_factory=list)
    channel_ids: list[uuid.UUID] = Field(default_factory=list)


class DeploymentTargetCreate(BaseModel):
    repository_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=160)
    environment: str = Field(min_length=1, max_length=40)
    strategy: Literal["git", "release", "docker_compose"]
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=255)
    working_directory: str = Field(min_length=1, max_length=1000)
    domain: str | None = Field(default=None, max_length=500)
    healthcheck_url: str | None = Field(default=None, max_length=1000)
    config: dict[str, Any] = Field(default_factory=dict)
    secret: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class DeploymentTargetRead(BaseModel):
    id: uuid.UUID
    repository_id: uuid.UUID | None
    name: str
    environment: str
    strategy: str
    host: str
    port: int
    username: str
    working_directory: str
    domain: str | None
    healthcheck_url: str | None
    config: dict[str, Any]
    enabled: bool
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class DeployRequest(BaseModel):
    repository_id: uuid.UUID
    ref: str = Field(min_length=1, max_length=255)
    release_url: str | None = None
    checksum_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    confirmation: str | None = None


class DeploymentRecordRead(BaseModel):
    id: uuid.UUID
    target_id: uuid.UUID
    repository_id: uuid.UUID | None
    job_id: uuid.UUID | None
    status: str
    requested_ref: str | None
    previous_version: dict[str, Any]
    deployed_version: dict[str, Any]
    pipeline: list[dict[str, Any]]
    health_result: dict[str, Any]
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}


class ClinicRunRequest(BaseModel):
    repository_id: uuid.UUID
    include_deep_git: bool = True
    include_actions: bool = True
    include_ghcr: bool = True


class ClinicFindingRead(BaseModel):
    id: uuid.UUID
    category: str
    severity: str
    action_class: str
    code: str
    title: str
    description: str
    evidence: dict[str, Any]
    risk: str
    recommendation: str
    action_available: str | None
    model_config = {"from_attributes": True}


class ClinicAnalysisRead(BaseModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    job_id: uuid.UUID | None
    status: str
    score: int
    score_breakdown: dict[str, Any]
    metrics: dict[str, Any]
    error: str | None
    created_at: datetime
    completed_at: datetime | None
    findings: list[ClinicFindingRead] = Field(default_factory=list)
    model_config = {"from_attributes": True}


class CleanupProfileCreate(BaseModel):
    repository_id: uuid.UUID
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    criteria: dict[str, Any] = Field(default_factory=dict)
    preservation_rules: dict[str, Any] = Field(default_factory=lambda: {
        "preserve_default_branch": True,
        "preserve_latest_release": True,
        "preserve_last_releases": 5,
        "preserve_protected_branches": True,
        "preserve_deployment_refs": True,
        "preserve_latest_image": True,
    })
    canonical_checkpoint: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class CleanupProfileRead(BaseModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    name: str
    description: str | None
    criteria: dict[str, Any]
    preservation_rules: dict[str, Any]
    canonical_checkpoint: dict[str, Any]
    enabled: bool
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class CleanupAnalyzeRequest(BaseModel):
    repository_id: uuid.UUID
    profile_id: uuid.UUID | None = None
    criteria: dict[str, Any] = Field(default_factory=dict)
    preservation_rules: dict[str, Any] = Field(default_factory=dict)
    canonical_checkpoint: dict[str, Any] = Field(default_factory=dict)


class CleanupCandidateRead(BaseModel):
    id: uuid.UUID
    resource_type: str
    resource_key: str
    resource_id: str | None
    action_class: str
    reason: str
    dependencies: list[dict[str, Any]]
    protected: bool
    selected: bool
    size_bytes: int | None
    metadata: dict[str, Any]
    model_config = {"from_attributes": True}


class CleanupSelectionRequest(BaseModel):
    candidate_ids: list[uuid.UUID] = Field(default_factory=list)


class CleanupExecuteRequest(BaseModel):
    confirmation: str
    create_backup: bool = True


class CleanupAnalysisRead(BaseModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    profile_id: uuid.UUID | None
    job_id: uuid.UUID | None
    reference: str
    status: str
    checkpoint: dict[str, Any]
    preservation_rules: dict[str, Any]
    metrics: dict[str, Any]
    dependency_graph: dict[str, Any]
    plan: list[dict[str, Any]]
    dry_run: dict[str, Any]
    estimated_reclaimed_bytes: int
    result: dict[str, Any]
    error: str | None
    created_at: datetime
    completed_at: datetime | None
    candidates: list[CleanupCandidateRead] = Field(default_factory=list)
    model_config = {"from_attributes": True}


class RepositoryCreateOnlineRequest(BaseModel):
    connection_id: uuid.UUID
    owner: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9._-]+$")
    description: str | None = Field(default=None, max_length=1000)
    private: bool = True
    default_branch: str = Field(default="main", min_length=1, max_length=255)
    template: Literal["empty", "readme", "docker", "docker_ghcr", "custom"] = "readme"
    options: dict[str, Any] = Field(default_factory=dict)


class BootstrapPreviewRequest(BaseModel):
    repository_id: uuid.UUID
    branch: str
    template: Literal["readme", "docker", "docker_ghcr", "custom"]
    options: dict[str, Any] = Field(default_factory=dict)


class BranchProtectionRequest(BaseModel):
    branch: str = Field(min_length=1, max_length=255)
    require_pull_request: bool = True
    approvals: int = Field(default=0, ge=0, le=6)
    enforce_admins: bool = True
    allow_force_pushes: bool = False
    allow_deletions: bool = False
    required_status_checks: list[str] = Field(default_factory=list)


class ReplicationRequest(BaseModel):
    repository_id: uuid.UUID
    mode: Literal["mirror", "branch", "release", "artifacts"]
    destination_kind: Literal["github_repository", "storage_provider", "sftp"]
    destination_connection_id: uuid.UUID | None = None
    destination_repository: str | None = None
    provider_id: uuid.UUID | None = None
    branch: str | None = None
    release_tag: str | None = None
    overwrite: bool = False


class AuditExportFilter(BaseModel):
    repository_id: uuid.UUID | None = None
    operation_prefix: str | None = None
