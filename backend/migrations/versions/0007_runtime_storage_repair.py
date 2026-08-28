"""Repara defaults de timestamps do storage operacional.

Revision ID: 0007_runtime_storage_repair
Revises: 0006_api_access_argon2
Create Date: 2026-08-28

A migration 0004 criava as tabelas somente quando elas não existiam. Instalações
que já possuíam storage_providers puderam manter created_at/updated_at NOT NULL
sem server default, fazendo INSERTs válidos do ORM falharem em produção.
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_runtime_storage_repair"
down_revision = "0006_api_access_argon2"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table not in set(inspector.get_table_names()):
        return set()
    return {str(item["name"]) for item in inspector.get_columns(table)}


def _repair_timestamps(table: str) -> None:
    columns = _columns(table)
    if "created_at" in columns:
        op.execute(sa.text(f'UPDATE "{table}" SET created_at = now() WHERE created_at IS NULL'))
        op.alter_column(
            table,
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=sa.text("now()"),
        )
    if "updated_at" in columns:
        op.execute(sa.text(f'UPDATE "{table}" SET updated_at = now() WHERE updated_at IS NULL'))
        op.alter_column(
            table,
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=sa.text("now()"),
        )


def upgrade() -> None:
    # Estas tabelas usam TimestampMixin e são criadas/administradas pela plataforma
    # operacional. Corrigir todas evita repetir o mesmo schema drift em outro fluxo.
    for table in (
        "storage_providers",
        "backup_policies",
        "publishing_channels",
        "deployment_targets",
    ):
        _repair_timestamps(table)


def downgrade() -> None:
    # Não removemos defaults no downgrade: eles fazem parte da invariável de
    # integridade das colunas NOT NULL e removê-los reintroduziria a falha.
    pass
