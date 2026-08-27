from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.api_access import ApiAccessKey

API_SCOPES = {
    "monitoring:read": "Consultar saúde e visão operacional.",
    "repositories:read": "Consultar repositórios monitorados.",
    "actions:write": "Ativar ou desativar GitHub Actions.",
    "backups:read": "Consultar backups e snapshots.",
    "backups:write": "Solicitar backups e restaurações autorizadas.",
}


class ApiAccessError(RuntimeError):
    pass


def normalize_scopes(scopes: list[str]) -> list[str]:
    normalized = sorted({str(item).strip() for item in scopes if str(item).strip()})
    unknown = [item for item in normalized if item not in API_SCOPES]
    if unknown:
        raise ApiAccessError(f"Escopo(s) desconhecido(s): {', '.join(unknown)}")
    if not normalized:
        raise ApiAccessError("Informe ao menos um escopo para a chave de API.")
    return normalized


def _digest(token: str) -> str:
    key = get_settings().app_secret_key.encode("utf-8")
    return hmac.new(key, token.encode("utf-8"), hashlib.sha256).hexdigest()


def generate_api_token() -> tuple[str, str, str]:
    prefix = secrets.token_hex(6)
    secret = secrets.token_urlsafe(32)
    token = f"agm_{prefix}_{secret}"
    return token, prefix, _digest(token)


async def authenticate_api_token(session: AsyncSession, token: str) -> ApiAccessKey:
    token = token.strip()
    if not token.startswith("agm_") or len(token) > 256:
        raise ApiAccessError("Chave de API inválida.")
    parts = token.split("_", 2)
    if len(parts) != 3 or not parts[1]:
        raise ApiAccessError("Chave de API inválida.")
    prefix = parts[1]
    key = (
        await session.execute(select(ApiAccessKey).where(ApiAccessKey.prefix == prefix))
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if not key or not key.enabled:
        raise ApiAccessError("Chave de API inválida ou revogada.")
    if key.expires_at:
        expires_at = key.expires_at if key.expires_at.tzinfo else key.expires_at.replace(tzinfo=UTC)
        if expires_at <= now:
            raise ApiAccessError("Chave de API expirada.")
    if not hmac.compare_digest(key.token_digest, _digest(token)):
        raise ApiAccessError("Chave de API inválida.")
    key.last_used_at = now
    await session.flush()
    return key


def require_scope(key: ApiAccessKey, scope: str) -> None:
    if scope not in (key.scopes or []):
        raise ApiAccessError(f"A chave de API não possui o escopo necessário: {scope}")


async def revoke_user_api_key(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    key_id: uuid.UUID,
) -> ApiAccessKey:
    key = await session.get(ApiAccessKey, key_id)
    if not key or key.user_id != user_id:
        raise ApiAccessError("Chave de API não encontrada.")
    key.enabled = False
    await session.flush()
    return key
