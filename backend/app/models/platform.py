from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.github import Repository
    from app.models.user import User


class ProviderKind(str, enum.Enum):
    LOCAL = "local"
    S3 = "s3"
    MINIO = "minio"
    GOOGLE_DRIVE = "google_drive"
    DROPBOX = "dropbox"
    SFTP = "sftp"


class BackupType(str, enum.Enum):
    FULL = "full"
    DEFAULT_BRANCH = "default_branch"
    SELECTED_BRANCHES = "selected_branches"
    ALL_BRANCHES = "all_branches"
    RELEASES_ONLY = "releases_only"


class BackupStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    VALIDATING = "validating"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OperationStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    VALIDATING = "validating"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLED_BACK = "rolled_back"


class FindingSeverity(str, enum.Enum):
    INFORMATIONAL = "informational"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionClass(str, enum.Enum):
    SAFE = "safe"
    REVIEW = "review"
    DESTRUCTIVE = "destructive"


class CleanupStatus(str, enum.Enum):
    ANALYZING = "analyzing"
    PLANNED = "planned"
    DRY_RUN = "dry_run"
    REVIEW = "review"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StorageProvider(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "storage_providers"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_storage_providers_user_name"),
        Index("ix_storage_providers_user_kind", "user_id", "kind"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    secret_encrypted: Mapped[str | None] = mapped_column(Text)
    secret_hint: Mapped[str | None] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped[User] = relationship()


class BackupPolicy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "backup_policies"
    __table_args__ = (
        UniqueConstraint("repository_id", "name", name="uq_backup_policy_repository_name"),
        Index("ix_backup_policy_repository_enabled", "repository_id", "enabled"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("storage_providers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    backup_type: Mapped[str] = mapped_column(String(40), nullable=False, default=BackupType.FULL.value)
    branches: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    include_releases: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    include_release_assets: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    include_lfs: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    include_submodules: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    schedule_kind: Mapped[str] = mapped_column(String(40), default="manual", nullable=False)
    schedule_value: Mapped[str | None] = mapped_column(String(120))
    event_trigger: Mapped[str | None] = mapped_column(String(80))
    retention: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    repository: Mapped[Repository] = relationship()
    provider: Mapped[StorageProvider] = relationship()


class BackupSnapshot(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "backup_snapshots"
    __table_args__ = (
        Index("ix_backup_snapshots_repository_created", "repository_id", "created_at"),
        Index("ix_backup_snapshots_policy_status", "policy_id", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    policy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("backup_policies.id", ondelete="SET NULL"), index=True
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("storage_providers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sync_jobs.id", ondelete="SET NULL"), index=True
    )
    backup_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    location: Mapped[str | None] = mapped_column(Text)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    object_count: Mapped[int | None] = mapped_column(Integer)
    permanent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    repository: Mapped[Repository] = relationship()
    provider: Mapped[StorageProvider] = relationship()
    policy: Mapped[BackupPolicy | None] = relationship()


class PublishingChannel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "publishing_channels"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_publishing_channels_user_name"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    storage_provider_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("storage_providers.id", ondelete="SET NULL"), index=True
    )
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("repositories.id", ondelete="SET NULL"), index=True
    )
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    secret_encrypted: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DeploymentTarget(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "deployment_targets"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_deployment_targets_user_name"),
        Index("ix_deployment_targets_user_environment", "user_id", "environment"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("repositories.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    environment: Mapped[str] = mapped_column(String(40), nullable=False)
    strategy: Mapped[str] = mapped_column(String(40), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=22, nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    working_directory: Mapped[str] = mapped_column(String(1000), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(500))
    healthcheck_url: Mapped[str | None] = mapped_column(String(1000))
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    secret_encrypted: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DeploymentRecord(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "deployment_records"
    __table_args__ = (
        Index("ix_deployment_records_target_created", "target_id", "created_at"),
        Index("ix_deployment_records_repository_created", "repository_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deployment_targets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("repositories.id", ondelete="SET NULL"), index=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sync_jobs.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    requested_ref: Mapped[str | None] = mapped_column(String(255))
    previous_version: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    deployed_version: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    pipeline: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    health_result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ClinicAnalysis(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "clinic_analyses"
    __table_args__ = (
        Index("ix_clinic_analyses_repository_created", "repository_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sync_jobs.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ClinicFinding(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "clinic_findings"
    __table_args__ = (
        Index("ix_clinic_findings_analysis_severity", "analysis_id", "severity"),
    )

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinic_analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(30), nullable=False)
    action_class: Mapped[str] = mapped_column(String(30), nullable=False)
    code: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    risk: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    action_available: Mapped[str | None] = mapped_column(String(120))


class CleanupProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cleanup_profiles"
    __table_args__ = (
        UniqueConstraint("repository_id", "name", name="uq_cleanup_profiles_repository_name"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    criteria: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    preservation_rules: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    canonical_checkpoint: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CleanupAnalysis(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "cleanup_analyses"
    __table_args__ = (
        Index("ix_cleanup_analyses_repository_created", "repository_id", "created_at"),
        Index("ix_cleanup_analyses_status_created", "status", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cleanup_profiles.id", ondelete="SET NULL"), index=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sync_jobs.id", ondelete="SET NULL"), index=True
    )
    reference: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    preservation_rules: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    dependency_graph: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    plan: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    dry_run: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    estimated_reclaimed_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CleanupCandidate(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "cleanup_candidates"
    __table_args__ = (
        Index("ix_cleanup_candidates_analysis_resource", "analysis_id", "resource_type"),
        Index("ix_cleanup_candidates_analysis_selected", "analysis_id", "selected"),
    )

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cleanup_analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resource_type: Mapped[str] = mapped_column(String(60), nullable=False)
    resource_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(255))
    action_class: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    dependencies: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    protected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
