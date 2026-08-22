"""Backup, release, deploy, clinic e cleanup operacional.

Revision ID: 0004_operations_platform
Revises: 0003_activity_automation
Create Date: 2026-08-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_operations_platform"
down_revision = "0003_activity_automation"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()

    if "storage_providers" not in tables:
        op.create_table(
            "storage_providers",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("kind", sa.String(length=40), nullable=False),
            sa.Column("config", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("secret_encrypted", sa.Text(), nullable=True),
            sa.Column("secret_hint", sa.String(length=120), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "name", name="uq_storage_providers_user_name"),
        )
        op.create_index("ix_storage_providers_user_id", "storage_providers", ["user_id"])
        op.create_index("ix_storage_providers_user_kind", "storage_providers", ["user_id", "kind"])

    if "backup_policies" not in tables:
        op.create_table(
            "backup_policies",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("backup_type", sa.String(length=40), nullable=False, server_default="full"),
            sa.Column("branches", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("include_releases", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("include_release_assets", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("include_lfs", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("include_submodules", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("schedule_kind", sa.String(length=40), nullable=False, server_default="manual"),
            sa.Column("schedule_value", sa.String(length=120), nullable=True),
            sa.Column("event_trigger", sa.String(length=80), nullable=True),
            sa.Column("retention", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["provider_id"], ["storage_providers.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("repository_id", "name", name="uq_backup_policy_repository_name"),
        )
        op.create_index("ix_backup_policies_user_id", "backup_policies", ["user_id"])
        op.create_index("ix_backup_policies_repository_id", "backup_policies", ["repository_id"])
        op.create_index("ix_backup_policies_provider_id", "backup_policies", ["provider_id"])
        op.create_index("ix_backup_policy_repository_enabled", "backup_policies", ["repository_id", "enabled"])

    if "backup_snapshots" not in tables:
        op.create_table(
            "backup_snapshots",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("backup_type", sa.String(length=40), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("location", sa.Text(), nullable=True),
            sa.Column("manifest", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
            sa.Column("size_bytes", sa.BigInteger(), nullable=True),
            sa.Column("object_count", sa.Integer(), nullable=True),
            sa.Column("permanent", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["policy_id"], ["backup_policies.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["provider_id"], ["storage_providers.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["job_id"], ["sync_jobs.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_backup_snapshots_user_id", "backup_snapshots", ["user_id"])
        op.create_index("ix_backup_snapshots_policy_id", "backup_snapshots", ["policy_id"])
        op.create_index("ix_backup_snapshots_repository_id", "backup_snapshots", ["repository_id"])
        op.create_index("ix_backup_snapshots_provider_id", "backup_snapshots", ["provider_id"])
        op.create_index("ix_backup_snapshots_job_id", "backup_snapshots", ["job_id"])
        op.create_index("ix_backup_snapshots_repository_created", "backup_snapshots", ["repository_id", "created_at"])
        op.create_index("ix_backup_snapshots_policy_status", "backup_snapshots", ["policy_id", "status"])

    if "publishing_channels" not in tables:
        op.create_table(
            "publishing_channels",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("kind", sa.String(length=40), nullable=False),
            sa.Column("storage_provider_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("config", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("secret_encrypted", sa.Text(), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["storage_provider_id"], ["storage_providers.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "name", name="uq_publishing_channels_user_name"),
        )
        op.create_index("ix_publishing_channels_user_id", "publishing_channels", ["user_id"])
        op.create_index("ix_publishing_channels_storage_provider_id", "publishing_channels", ["storage_provider_id"])
        op.create_index("ix_publishing_channels_repository_id", "publishing_channels", ["repository_id"])

    if "deployment_targets" not in tables:
        op.create_table(
            "deployment_targets",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("environment", sa.String(length=40), nullable=False),
            sa.Column("strategy", sa.String(length=40), nullable=False),
            sa.Column("host", sa.String(length=255), nullable=False),
            sa.Column("port", sa.Integer(), nullable=False, server_default="22"),
            sa.Column("username", sa.String(length=255), nullable=False),
            sa.Column("working_directory", sa.String(length=1000), nullable=False),
            sa.Column("domain", sa.String(length=500), nullable=True),
            sa.Column("healthcheck_url", sa.String(length=1000), nullable=True),
            sa.Column("config", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("secret_encrypted", sa.Text(), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "name", name="uq_deployment_targets_user_name"),
        )
        op.create_index("ix_deployment_targets_user_id", "deployment_targets", ["user_id"])
        op.create_index("ix_deployment_targets_repository_id", "deployment_targets", ["repository_id"])
        op.create_index("ix_deployment_targets_user_environment", "deployment_targets", ["user_id", "environment"])

    if "deployment_records" not in tables:
        op.create_table(
            "deployment_records",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("requested_ref", sa.String(length=255), nullable=True),
            sa.Column("previous_version", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("deployed_version", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("pipeline", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("health_result", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["target_id"], ["deployment_targets.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["job_id"], ["sync_jobs.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_deployment_records_user_id", "deployment_records", ["user_id"])
        op.create_index("ix_deployment_records_target_id", "deployment_records", ["target_id"])
        op.create_index("ix_deployment_records_repository_id", "deployment_records", ["repository_id"])
        op.create_index("ix_deployment_records_job_id", "deployment_records", ["job_id"])
        op.create_index("ix_deployment_records_target_created", "deployment_records", ["target_id", "created_at"])
        op.create_index("ix_deployment_records_repository_created", "deployment_records", ["repository_id", "created_at"])

    if "clinic_analyses" not in tables:
        op.create_table(
            "clinic_analyses",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("score_breakdown", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("metrics", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["job_id"], ["sync_jobs.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_clinic_analyses_user_id", "clinic_analyses", ["user_id"])
        op.create_index("ix_clinic_analyses_repository_id", "clinic_analyses", ["repository_id"])
        op.create_index("ix_clinic_analyses_job_id", "clinic_analyses", ["job_id"])
        op.create_index("ix_clinic_analyses_repository_created", "clinic_analyses", ["repository_id", "created_at"])

    if "clinic_findings" not in tables:
        op.create_table(
            "clinic_findings",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("analysis_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("category", sa.String(length=80), nullable=False),
            sa.Column("severity", sa.String(length=30), nullable=False),
            sa.Column("action_class", sa.String(length=30), nullable=False),
            sa.Column("code", sa.String(length=120), nullable=False),
            sa.Column("title", sa.String(length=500), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("evidence", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("risk", sa.Text(), nullable=False),
            sa.Column("recommendation", sa.Text(), nullable=False),
            sa.Column("action_available", sa.String(length=120), nullable=True),
            sa.ForeignKeyConstraint(["analysis_id"], ["clinic_analyses.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_clinic_findings_analysis_id", "clinic_findings", ["analysis_id"])
        op.create_index("ix_clinic_findings_analysis_severity", "clinic_findings", ["analysis_id", "severity"])

    if "cleanup_profiles" not in tables:
        op.create_table(
            "cleanup_profiles",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("criteria", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("preservation_rules", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("canonical_checkpoint", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("repository_id", "name", name="uq_cleanup_profiles_repository_name"),
        )
        op.create_index("ix_cleanup_profiles_user_id", "cleanup_profiles", ["user_id"])
        op.create_index("ix_cleanup_profiles_repository_id", "cleanup_profiles", ["repository_id"])

    if "cleanup_analyses" not in tables:
        op.create_table(
            "cleanup_analyses",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("reference", sa.String(length=40), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("checkpoint", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("preservation_rules", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("metrics", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("dependency_graph", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("plan", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("dry_run", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("estimated_reclaimed_bytes", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("result", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["profile_id"], ["cleanup_profiles.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["job_id"], ["sync_jobs.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("reference"),
        )
        op.create_index("ix_cleanup_analyses_user_id", "cleanup_analyses", ["user_id"])
        op.create_index("ix_cleanup_analyses_repository_id", "cleanup_analyses", ["repository_id"])
        op.create_index("ix_cleanup_analyses_profile_id", "cleanup_analyses", ["profile_id"])
        op.create_index("ix_cleanup_analyses_job_id", "cleanup_analyses", ["job_id"])
        op.create_index("ix_cleanup_analyses_repository_created", "cleanup_analyses", ["repository_id", "created_at"])
        op.create_index("ix_cleanup_analyses_status_created", "cleanup_analyses", ["status", "created_at"])

    if "cleanup_candidates" not in tables:
        op.create_table(
            "cleanup_candidates",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("analysis_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("resource_type", sa.String(length=60), nullable=False),
            sa.Column("resource_key", sa.String(length=1000), nullable=False),
            sa.Column("resource_id", sa.String(length=255), nullable=True),
            sa.Column("action_class", sa.String(length=30), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("dependencies", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("protected", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("size_bytes", sa.BigInteger(), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.ForeignKeyConstraint(["analysis_id"], ["cleanup_analyses.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_cleanup_candidates_analysis_id", "cleanup_candidates", ["analysis_id"])
        op.create_index("ix_cleanup_candidates_analysis_resource", "cleanup_candidates", ["analysis_id", "resource_type"])
        op.create_index("ix_cleanup_candidates_analysis_selected", "cleanup_candidates", ["analysis_id", "selected"])

    # Retira defaults transitórios após a criação para manter o contrato ORM como fonte.
    for table, columns in {
        "storage_providers": ["config", "enabled", "created_at", "updated_at"],
        "backup_policies": ["backup_type", "branches", "include_releases", "include_release_assets", "include_lfs", "include_submodules", "schedule_kind", "retention", "enabled", "created_at", "updated_at"],
        "backup_snapshots": ["manifest", "permanent", "created_at"],
        "publishing_channels": ["config", "enabled", "created_at", "updated_at"],
        "deployment_targets": ["port", "config", "enabled", "created_at", "updated_at"],
        "deployment_records": ["previous_version", "deployed_version", "pipeline", "health_result", "created_at"],
        "clinic_analyses": ["score", "score_breakdown", "metrics", "created_at"],
        "clinic_findings": ["evidence"],
        "cleanup_profiles": ["criteria", "preservation_rules", "canonical_checkpoint", "enabled", "created_at", "updated_at"],
        "cleanup_analyses": ["checkpoint", "preservation_rules", "metrics", "dependency_graph", "plan", "dry_run", "estimated_reclaimed_bytes", "result", "created_at"],
        "cleanup_candidates": ["dependencies", "protected", "selected", "metadata"],
    }.items():
        if table in _tables():
            for column in columns:
                op.alter_column(table, column, server_default=None)


def downgrade() -> None:
    for table in (
        "cleanup_candidates",
        "cleanup_analyses",
        "cleanup_profiles",
        "clinic_findings",
        "clinic_analyses",
        "deployment_records",
        "deployment_targets",
        "publishing_channels",
        "backup_snapshots",
        "backup_policies",
        "storage_providers",
    ):
        if table in _tables():
            op.drop_table(table)
