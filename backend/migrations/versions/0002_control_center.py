"""2FA, fila persistente e centro de controle.

Revision ID: 0002_control_center
Revises: 0001_initial
Create Date: 2026-08-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_control_center"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_secret_encrypted", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("users", sa.Column("totp_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column("recovery_codes_hashes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )

    op.create_table(
        "sync_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("celery_task_id", sa.String(length=255), nullable=True),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="queued"),
        sa.Column("progress_current", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connection_id"], ["github_connections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sync_jobs_user_id", "sync_jobs", ["user_id"], unique=False)
    op.create_index("ix_sync_jobs_connection_id", "sync_jobs", ["connection_id"], unique=False)
    op.create_index("ix_sync_jobs_repository_id", "sync_jobs", ["repository_id"], unique=False)
    op.create_index("ix_sync_jobs_celery_task", "sync_jobs", ["celery_task_id"], unique=False)
    op.create_index("ix_sync_jobs_user_created", "sync_jobs", ["user_id", "created_at"], unique=False)
    op.create_index("ix_sync_jobs_status_created", "sync_jobs", ["status", "created_at"], unique=False)

    op.alter_column("users", "totp_enabled", server_default=None)
    op.alter_column("users", "recovery_codes_hashes", server_default=None)
    op.alter_column("sync_jobs", "status", server_default=None)
    op.alter_column("sync_jobs", "progress_current", server_default=None)
    op.alter_column("sync_jobs", "progress_total", server_default=None)
    op.alter_column("sync_jobs", "result", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_sync_jobs_status_created", table_name="sync_jobs")
    op.drop_index("ix_sync_jobs_user_created", table_name="sync_jobs")
    op.drop_index("ix_sync_jobs_celery_task", table_name="sync_jobs")
    op.drop_index("ix_sync_jobs_repository_id", table_name="sync_jobs")
    op.drop_index("ix_sync_jobs_connection_id", table_name="sync_jobs")
    op.drop_index("ix_sync_jobs_user_id", table_name="sync_jobs")
    op.drop_table("sync_jobs")
    op.drop_column("users", "recovery_codes_hashes")
    op.drop_column("users", "totp_confirmed_at")
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_secret_encrypted")
