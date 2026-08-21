from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
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
    from app.models.activity import Notification
    from app.models.user import User


class ConnectionStatus(str, enum.Enum):
    ACTIVE = "active"
    ERROR = "error"
    REVOKED = "revoked"
    DEMO = "demo"


class HealthStatus(str, enum.Enum):
    HEALTHY = "healthy"
    RUNNING = "running"
    ATTENTION = "attention"
    FAILING = "failing"
    UNKNOWN = "unknown"


class GitHubConnection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "github_connections"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    github_login: Mapped[str] = mapped_column(String(255), nullable=False)
    github_user_id: Mapped[int | None] = mapped_column(BigInteger)
    token_encrypted: Mapped[str | None] = mapped_column(Text)
    token_last_four: Mapped[str | None] = mapped_column(String(4))
    status: Mapped[ConnectionStatus] = mapped_column(
        Enum(ConnectionStatus, native_enum=False, length=20),
        default=ConnectionStatus.ACTIVE,
        nullable=False,
    )
    auto_import: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    api_url: Mapped[str] = mapped_column(String(500), default="https://api.github.com", nullable=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    rate_limit_remaining: Mapped[int | None] = mapped_column(Integer)
    rate_limit_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="github_connections")
    repositories: Mapped[list[Repository]] = relationship(
        back_populates="connection", cascade="all, delete-orphan"
    )


class Repository(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint("connection_id", "github_id", name="uq_repositories_connection_github"),
        Index("ix_repositories_health", "health_status", "health_score"),
        Index("ix_repositories_full_name", "full_name"),
        Index("ix_repositories_last_activity", "last_activity_at"),
    )

    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("github_connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    github_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(520), nullable=False)
    html_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    private: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fork: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    visibility: Mapped[str] = mapped_column(String(30), default="public", nullable=False)
    default_branch: Mapped[str] = mapped_column(String(255), default="main", nullable=False)
    language: Mapped[str | None] = mapped_column(String(100))
    stargazers_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    forks_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    open_issue_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    open_pr_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    branch_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    github_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    github_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    latest_commit_sha: Mapped[str | None] = mapped_column(String(64))
    latest_commit_message: Mapped[str | None] = mapped_column(Text)
    latest_commit_author: Mapped[str | None] = mapped_column(String(255))
    latest_commit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    latest_release_tag: Mapped[str | None] = mapped_column(String(255))
    latest_release_name: Mapped[str | None] = mapped_column(String(500))
    latest_release_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    latest_workflow_id: Mapped[int | None] = mapped_column(BigInteger)
    latest_workflow_name: Mapped[str | None] = mapped_column(String(500))
    latest_workflow_status: Mapped[str | None] = mapped_column(String(50))
    latest_workflow_conclusion: Mapped[str | None] = mapped_column(String(50))
    latest_workflow_url: Mapped[str | None] = mapped_column(String(1000))
    latest_workflow_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_activity_type: Mapped[str | None] = mapped_column(String(60))
    last_activity_summary: Mapped[str | None] = mapped_column(String(1000))
    activity_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    health_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    health_status: Mapped[HealthStatus] = mapped_column(
        Enum(HealthStatus, native_enum=False, length=20),
        default=HealthStatus.UNKNOWN,
        nullable=False,
    )
    monitoring_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_error: Mapped[str | None] = mapped_column(Text)
    extra_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    connection: Mapped[GitHubConnection] = relationship(back_populates="repositories")
    workflow_runs: Mapped[list[WorkflowRun]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    pull_requests: Mapped[list[PullRequest]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    releases: Mapped[list[Release]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    notifications: Mapped[list[Notification]] = relationship(back_populates="repository")


class WorkflowRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        UniqueConstraint("repository_id", "github_id", name="uq_workflow_runs_repo_github"),
        Index("ix_workflow_runs_repo_created", "repository_id", "github_created_at"),
    )

    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    github_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    display_title: Mapped[str | None] = mapped_column(String(1000))
    event: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    conclusion: Mapped[str | None] = mapped_column(String(50))
    head_branch: Mapped[str | None] = mapped_column(String(255))
    head_sha: Mapped[str | None] = mapped_column(String(64))
    run_number: Mapped[int | None] = mapped_column(Integer)
    run_attempt: Mapped[int | None] = mapped_column(Integer)
    html_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    actor_login: Mapped[str | None] = mapped_column(String(255))
    github_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    github_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    run_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)

    repository: Mapped[Repository] = relationship(back_populates="workflow_runs")


class PullRequest(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "pull_requests"
    __table_args__ = (
        UniqueConstraint("repository_id", "github_id", name="uq_pull_requests_repo_github"),
        Index("ix_pull_requests_repo_updated", "repository_id", "github_updated_at"),
    )

    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    github_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    state: Mapped[str] = mapped_column(String(30), nullable=False)
    draft: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    html_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    user_login: Mapped[str | None] = mapped_column(String(255))
    head_ref: Mapped[str | None] = mapped_column(String(255))
    base_ref: Mapped[str | None] = mapped_column(String(255))
    mergeable_state: Mapped[str | None] = mapped_column(String(50))
    github_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    github_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    repository: Mapped[Repository] = relationship(back_populates="pull_requests")


class Release(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "releases"
    __table_args__ = (
        UniqueConstraint("repository_id", "github_id", name="uq_releases_repo_github"),
        Index("ix_releases_repo_published", "repository_id", "published_at"),
    )

    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    github_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tag_name: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(500))
    draft: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    prerelease: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    html_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    target_commitish: Mapped[str | None] = mapped_column(String(255))
    github_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    repository: Mapped[Repository] = relationship(back_populates="releases")
