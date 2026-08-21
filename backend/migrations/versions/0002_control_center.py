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


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    user_columns = _columns("users")
    if "totp_secret_encrypted" not in user_columns:
        op.add_column("users", sa.Column("totp_secret_encrypted", sa.Text(), nullable=True))
    if "totp_enabled" not in user_columns:
        op.add_column("users", sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "totp_confirmed_at" not in user_columns:
        op.add_column("users", sa.Column("totp_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    if "recovery_codes_hashes" not in user_columns:
        op.add_column("users", sa.Column("recovery_codes_hashes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))

    inspector = sa.inspect(op.get_bind())
    if "sync_jobs" not in inspector.get_table_names():
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

    indexes = _indexes("sync_jobs")
    desired_indexes = {
        "ix_sync_jobs_user_id": ["user_id"],
        "ix_sync_jobs_connection_id": ["connection_id"],
        "ix_sync_jobs_repository_id": ["repository_id"],
        "ix_sync_jobs_celery_task": ["celery_task_id"],
        "ix_sync_jobs_user_created": ["user_id", "created_at"],
        "ix_sync_jobs_status_created": ["status", "created_at"],
    }
    for index_name, columns in desired_indexes.items():
        if index_name not in indexes:
            op.create_index(index_name, "sync_jobs", columns, unique=False)

    current_user_columns = _columns("users")
    if "totp_enabled" in current_user_columns:
        op.alter_column("users", "totp_enabled", server_default=None)
    if "recovery_codes_hashes" in current_user_columns:
        op.alter_column("users", "recovery_codes_hashes", server_default=None)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "sync_jobs" in inspector.get_table_names():
        op.drop_table("sync_jobs")

    user_columns = _columns("users")
    for column_name in ("recovery_codes_hashes", "totp_confirmed_at", "totp_enabled", "totp_secret_encrypted"):
        if column_name in user_columns:
            op.drop_column("users", column_name)
