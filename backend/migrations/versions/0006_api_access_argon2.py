"""API access keys: Argon2id storage.

Revision ID: 0006_api_access_argon2
Revises: 0005_realtime_external_api
Create Date: 2026-08-27
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_api_access_argon2"
down_revision = "0005_realtime_external_api"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "api_access_keys" not in _tables():
        return

    op.alter_column(
        "api_access_keys",
        "token_digest",
        existing_type=sa.String(length=64),
        type_=sa.String(length=255),
        existing_nullable=False,
    )

    # Chaves criadas pela implementação anterior usavam um digest HMAC-SHA256
    # de 64 caracteres. Como a feature ainda não foi mesclada, não mantemos uma
    # verificação legada fraca: revogamos explicitamente essas credenciais e o
    # usuário poderá emitir uma chave Argon2id nova pela interface.
    op.execute(
        sa.text(
            "UPDATE api_access_keys "
            "SET enabled = false "
            "WHERE token_digest NOT LIKE '$argon2id$%'"
        )
    )


def downgrade() -> None:
    if "api_access_keys" not in _tables():
        return

    # Hashes Argon2id não cabem em VARCHAR(64). Em um downgrade, neutralizamos
    # as credenciais e preservamos somente um marcador não utilizável.
    op.execute(
        sa.text(
            "UPDATE api_access_keys "
            "SET enabled = false, token_digest = repeat('0', 64)"
        )
    )
    op.alter_column(
        "api_access_keys",
        "token_digest",
        existing_type=sa.String(length=255),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
