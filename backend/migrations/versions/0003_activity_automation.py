"""Atividade observada, saúde explicável e automação por inatividade.

Revision ID: 0003_activity_automation
Revises: 0002_control_center
Create Date: 2026-08-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_activity_automation"
down_revision = "0002_control_center"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


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
    repository_columns = _columns("repositories")
    additions = {
        "last_activity_at": sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        "last_activity_type": sa.Column("last_activity_type", sa.String(length=60), nullable=True),
        "last_activity_summary": sa.Column("last_activity_summary", sa.String(length=1000), nullable=True),
        "activity_observed_at": sa.Column("activity_observed_at", sa.DateTime(timezone=True), nullable=True),
    }
    for name, column in additions.items():
        if name not in repository_columns:
            op.add_column("repositories", column)

    repository_indexes = _indexes("repositories")
    if "ix_repositories_last_activity" not in repository_indexes:
        op.create_index(
            "ix_repositories_last_activity",
            "repositories",
            ["last_activity_at"],
            unique=False,
        )

    if "health_score" in _columns("repositories"):
        op.alter_column("repositories", "health_score", server_default=sa.text("0"))
        op.execute(
            sa.text(
                "UPDATE repositories SET health_score = 0 "
                "WHERE last_synced_at IS NULL OR health_status = 'unknown'"
            )
        )

    tables = _tables()
    if "inactivity_policies" not in tables:
        op.create_table(
            "inactivity_policies",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("timeout_value", sa.Integer(), nullable=False, server_default="30"),
            sa.Column("timeout_unit", sa.String(length=20), nullable=False, server_default="days"),
            sa.Column("action", sa.String(length=30), nullable=False, server_default="private"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("activity_sources", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "name", name="uq_inactivity_policies_user_name"),
        )
        op.create_index("ix_inactivity_policies_user_id", "inactivity_policies", ["user_id"])
        op.create_index(
            "ix_inactivity_policies_user_enabled",
            "inactivity_policies",
            ["user_id", "enabled"],
        )

    tables = _tables()
    if "inactivity_policy_repositories" not in tables:
        op.create_table(
            "inactivity_policy_repositories",
            sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["policy_id"], ["inactivity_policies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("policy_id", "repository_id"),
        )
        op.create_index(
            "ix_inactivity_policy_repositories_repository",
            "inactivity_policy_repositories",
            ["repository_id"],
        )

    tables = _tables()
    if "inactivity_action_logs" not in tables:
        op.create_table(
            "inactivity_action_logs",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("repository_full_name", sa.String(length=520), nullable=False),
            sa.Column("action", sa.String(length=30), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("previous_private", sa.Boolean(), nullable=True),
            sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("threshold_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("result", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["policy_id"], ["inactivity_policies.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_inactivity_action_logs_policy_id", "inactivity_action_logs", ["policy_id"])
        op.create_index("ix_inactivity_action_logs_repository_id", "inactivity_action_logs", ["repository_id"])
        op.create_index(
            "ix_inactivity_action_logs_policy_created",
            "inactivity_action_logs",
            ["policy_id", "created_at"],
        )
        op.create_index(
            "ix_inactivity_action_logs_repo_created",
            "inactivity_action_logs",
            ["repository_id", "created_at"],
        )

    for table in ("inactivity_policies", "inactivity_action_logs"):
        if table in _tables():
            columns = _columns(table)
            if table == "inactivity_policies":
                if "timeout_value" in columns:
                    op.alter_column(table, "timeout_value", server_default=None)
                if "timeout_unit" in columns:
                    op.alter_column(table, "timeout_unit", server_default=None)
                if "action" in columns:
                    op.alter_column(table, "action", server_default=None)
                if "enabled" in columns:
                    op.alter_column(table, "enabled", server_default=None)
                if "activity_sources" in columns:
                    op.alter_column(table, "activity_sources", server_default=None)
            if table == "inactivity_action_logs" and "result" in columns:
                op.alter_column(table, "result", server_default=None)


def downgrade() -> None:
    tables = _tables()
    for table in (
        "inactivity_action_logs",
        "inactivity_policy_repositories",
        "inactivity_policies",
    ):
        if table in tables:
            op.drop_table(table)
    repository_indexes = _indexes("repositories")
    if "ix_repositories_last_activity" in repository_indexes:
        op.drop_index("ix_repositories_last_activity", table_name="repositories")
    repository_columns = _columns("repositories")
    for name in (
        "activity_observed_at",
        "last_activity_summary",
        "last_activity_type",
        "last_activity_at",
    ):
        if name in repository_columns:
            op.drop_column("repositories", name)
