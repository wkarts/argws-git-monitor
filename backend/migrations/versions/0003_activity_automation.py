"""Atividade observada, saúde explicável, perfil e automação por inatividade.

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
    user_columns = _columns("users")
    user_additions = {
        "job_title": sa.Column("job_title", sa.String(length=160), nullable=True),
        "bio": sa.Column("bio", sa.Text(), nullable=True),
        "timezone": sa.Column(
            "timezone",
            sa.String(length=80),
            nullable=False,
            server_default="America/Bahia",
        ),
        "locale": sa.Column(
            "locale", sa.String(length=20), nullable=False, server_default="pt-BR"
        ),
        "preferences": sa.Column(
            "preferences", sa.JSON(), nullable=False, server_default=sa.text("'{}'")
        ),
        "avatar_mime": sa.Column("avatar_mime", sa.String(length=100), nullable=True),
        "avatar_blob": sa.Column("avatar_blob", sa.LargeBinary(), nullable=True),
        "avatar_updated_at": sa.Column(
            "avatar_updated_at", sa.DateTime(timezone=True), nullable=True
        ),
    }
    for name, column in user_additions.items():
        if name not in user_columns:
            op.add_column("users", column)

    repository_columns = _columns("repositories")
    repository_additions = {
        "last_activity_at": sa.Column(
            "last_activity_at", sa.DateTime(timezone=True), nullable=True
        ),
        "last_activity_type": sa.Column(
            "last_activity_type", sa.String(length=60), nullable=True
        ),
        "last_activity_summary": sa.Column(
            "last_activity_summary", sa.String(length=1000), nullable=True
        ),
        "activity_observed_at": sa.Column(
            "activity_observed_at", sa.DateTime(timezone=True), nullable=True
        ),
    }
    for name, column in repository_additions.items():
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

    # Versões anteriores podiam registrar jobs QUEUED/RUNNING mesmo sem worker
    # Celery disponível. No upgrade, jobs antigos não podem continuar parecendo
    # processamento vivo indefinidamente. Só reconciliamos os que já estão parados
    # há pelo menos 15 minutos; nada é removido e o histórico permanece visível.
    if "sync_jobs" in _tables():
        op.execute(
            sa.text(
                "UPDATE sync_jobs "
                "SET status = 'failed', "
                "message = 'Job antigo reconciliado durante upgrade da fila operacional.', "
                "error = COALESCE(error, 'Job abandonado: não houve confirmação de worker. Use Repetir após validar a stack.'), "
                "completed_at = COALESCE(completed_at, now()) "
                "WHERE status IN ('queued', 'running') "
                "AND created_at < now() - interval '15 minutes'"
            )
        )

    tables = _tables()
    if "issues" not in tables:
        op.create_table(
            "issues",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("github_id", sa.BigInteger(), nullable=False),
            sa.Column("number", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=1000), nullable=False),
            sa.Column("state", sa.String(length=30), nullable=False),
            sa.Column("html_url", sa.String(length=1000), nullable=False),
            sa.Column("user_login", sa.String(length=255), nullable=True),
            sa.Column("comments", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("labels_text", sa.Text(), nullable=True),
            sa.Column("github_created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("github_updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(
                ["repository_id"], ["repositories.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "repository_id", "github_id", name="uq_issues_repo_github"
            ),
        )
        op.create_index("ix_issues_repository_id", "issues", ["repository_id"])
        op.create_index(
            "ix_issues_repo_updated", "issues", ["repository_id", "github_updated_at"]
        )
        op.create_index(
            "ix_issues_repo_state", "issues", ["repository_id", "state"]
        )

    tables = _tables()
    if "inactivity_policies" not in tables:
        op.create_table(
            "inactivity_policies",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column(
                "timeout_value", sa.Integer(), nullable=False, server_default="30"
            ),
            sa.Column(
                "timeout_unit",
                sa.String(length=20),
                nullable=False,
                server_default="days",
            ),
            sa.Column(
                "action",
                sa.String(length=30),
                nullable=False,
                server_default="private",
            ),
            sa.Column(
                "enabled", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.Column(
                "activity_sources",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "user_id", "name", name="uq_inactivity_policies_user_name"
            ),
        )
        op.create_index(
            "ix_inactivity_policies_user_id", "inactivity_policies", ["user_id"]
        )
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
            sa.ForeignKeyConstraint(
                ["policy_id"], ["inactivity_policies.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["repository_id"], ["repositories.id"], ondelete="CASCADE"
            ),
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
            sa.Column(
                "result", sa.JSON(), nullable=False, server_default=sa.text("'{}'")
            ),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["policy_id"], ["inactivity_policies.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["repository_id"], ["repositories.id"], ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_inactivity_action_logs_policy_id",
            "inactivity_action_logs",
            ["policy_id"],
        )
        op.create_index(
            "ix_inactivity_action_logs_repository_id",
            "inactivity_action_logs",
            ["repository_id"],
        )
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

    current_user_columns = _columns("users")
    if "timezone" in current_user_columns:
        op.alter_column("users", "timezone", server_default=None)
    if "locale" in current_user_columns:
        op.alter_column("users", "locale", server_default=None)
    if "preferences" in current_user_columns:
        op.alter_column("users", "preferences", server_default=None)

    current_issue_columns = _columns("issues")
    if "comments" in current_issue_columns:
        op.alter_column("issues", "comments", server_default=None)
    if "locked" in current_issue_columns:
        op.alter_column("issues", "locked", server_default=None)

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
        "issues",
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

    user_columns = _columns("users")
    for name in (
        "avatar_updated_at",
        "avatar_blob",
        "avatar_mime",
        "preferences",
        "locale",
        "timezone",
        "bio",
        "job_title",
    ):
        if name in user_columns:
            op.drop_column("users", name)
