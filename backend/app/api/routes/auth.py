from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select, update

from app.api.deps import CurrentUser, DbSession
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.user import RefreshToken, User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenPair,
    UserRead,
)
from app.schemas.common import MessageResponse
from app.services.audit import record_audit

router = APIRouter(prefix="/auth", tags=["Autenticação"])


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else None


def _is_expired(value: datetime) -> bool:
    candidate = value if value.tzinfo else value.replace(tzinfo=UTC)
    return candidate <= datetime.now(UTC)


async def _issue_token_pair(db: DbSession, user: User, request: Request) -> TokenPair:
    access_token, access_expires_at = create_access_token(
        str(user.id), is_superuser=user.is_superuser
    )
    raw_refresh, refresh_hash, refresh_expires_at = create_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=refresh_hash,
            expires_at=refresh_expires_at,
            revoked_at=None,
            user_agent=request.headers.get("user-agent", "")[:500],
            ip_address=_client_ip(request),
            created_at=datetime.now(UTC),
        )
    )
    return TokenPair(
        access_token=access_token,
        refresh_token=raw_refresh,
        access_expires_at=access_expires_at,
        refresh_expires_at=refresh_expires_at,
        user=UserRead.model_validate(user),
    )


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, request: Request, db: DbSession) -> TokenPair:
    result = await db.execute(select(User).where(User.email == str(payload.email).lower()))
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha inválidos.",
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Usuário inativo.")

    user.last_login_at = datetime.now(UTC)
    token_pair = await _issue_token_pair(db, user, request)
    await record_audit(
        db,
        action="auth.login",
        user_id=user.id,
        ip_address=_client_ip(request),
    )
    await db.commit()
    await db.refresh(user)
    token_pair.user = UserRead.model_validate(user)
    return token_pair


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, request: Request, db: DbSession) -> TokenPair:
    token_hash = hash_refresh_token(payload.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    stored = result.scalar_one_or_none()
    if not stored or stored.revoked_at or _is_expired(stored.expires_at):
        raise HTTPException(status_code=401, detail="Refresh token inválido ou expirado.")

    user = await db.get(User, stored.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Usuário inválido ou inativo.")

    stored.revoked_at = datetime.now(UTC)
    token_pair = await _issue_token_pair(db, user, request)
    await db.commit()
    return token_pair


@router.post("/logout", response_model=MessageResponse)
async def logout(payload: LogoutRequest, db: DbSession) -> MessageResponse:
    token_hash = hash_refresh_token(payload.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    stored = result.scalar_one_or_none()
    if stored and not stored.revoked_at:
        stored.revoked_at = datetime.now(UTC)
        await db.commit()
    return MessageResponse(message="Sessão encerrada.")


@router.get("/me", response_model=UserRead)
async def me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> MessageResponse:
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Senha atual incorreta.")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="A nova senha deve ser diferente.")

    current_user.password_hash = hash_password(payload.new_password)
    current_user.must_change_password = False
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == current_user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await record_audit(
        db,
        action="auth.password_changed",
        user_id=current_user.id,
        ip_address=_client_ip(request),
    )
    await db.commit()
    return MessageResponse(message="Senha alterada. Entre novamente com a nova senha.")
