from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class InactivityPolicy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "inactivity_policies"
    __table_args__ = (
        Index("ix_inactivity_policies_user_enabled", "user_id", "enabled"),
        UniqueConstraint("user_id", "name", name="uq_inactivity_policies_user_name"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    timeout_value: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    timeout_unit: Mapped[str] = mapped_column(String(20), nullable=False, default="days")
    action: Mapped[str] = mapped_column(String(30), nullable=False, default="private")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    activity_sources: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InactivityPolicyRepository(Base):
    __tablename__ = "inactivity_policy_repositories"
    __table_args__ = (
        Index("ix_inactivity_policy_repositories_repository", "repository_id"),
    )

    policy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inactivity_policies.id", ondelete="CASCADE"), primary_key=True
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), primary_key=True
    )
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InactivityActionLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "inactivity_action_logs"
    __table_args__ = (
        Index("ix_inactivity_action_logs_policy_created", "policy_id", "created_at"),
        Index("ix_inactivity_action_logs_repo_created", "repository_id", "created_at"),
    )

    policy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("inactivity_policies.id", ondelete="SET NULL"), index=True
    )
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("repositories.id", ondelete="SET NULL"), index=True
    )
    repository_full_name: Mapped[str] = mapped_column(String(520), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    previous_private: Mapped[bool | None] = mapped_column(Boolean)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    threshold_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
