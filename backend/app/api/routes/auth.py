from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile, status
from sqlalchemy import select, update

from app.api.deps import CurrentUser, DbSession
from app.core.encryption import EncryptionService
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
    ProfileUpdate,
    RefreshRequest,
    SessionRead,
    TokenPair,
    TwoFactorConfirmRequest,
    TwoFactorDisableRequest,
    TwoFactorRecoveryCodesResponse,
    TwoFactorRegenerateRecoveryRequest,
    TwoFactorSetupRequest,
    TwoFactorSetupResponse,
    TwoFactorStatus,
    UserRead,
)
from app.schemas.common import MessageResponse
from app.services.audit import record_audit
from app.services.totp import (
    build_otpauth_uri,
    build_qr_data_uri,
    generate_recovery_codes,
    generate_totp_secret,
    hash_recovery_code,
    recovery_code_index,
    verify_totp,
)

router = APIRouter(prefix="/auth", tags=["Autenticação"])

ALLOWED_AVATAR_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_AVATAR_BYTES = 2 * 1024 * 1024


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


def _second_factor_secret(user: User) -> str | None:
    if not user.totp_secret_encrypted:
        return None
    return EncryptionService().decrypt(user.totp_secret_encrypted)


def _validate_second_factor(user: User, code: str | None) -> bool:
    if not user.totp_enabled:
        return True
    if not code:
        raise HTTPException(status_code=401, detail="2FA_REQUIRED")

    secret = _second_factor_secret(user)
    if secret and verify_totp(secret, code):
        return True

    hashes = list(user.recovery_codes_hashes or [])
    recovery_index = recovery_code_index(code, hashes)
    if recovery_index is not None:
        hashes.pop(recovery_index)
        user.recovery_codes_hashes = hashes
        return True

    raise HTTPException(status_code=401, detail="Código de autenticação em duas etapas inválido.")


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

    _validate_second_factor(user, payload.otp_code)
    user.last_login_at = datetime.now(UTC)
    token_pair = await _issue_token_pair(db, user, request)
    await record_audit(
        db,
        action="auth.login",
        user_id=user.id,
        ip_address=_client_ip(request),
        details={"two_factor": user.totp_enabled},
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


@router.patch("/profile", response_model=UserRead)
async def update_profile(
    payload: ProfileUpdate,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> UserRead:
    current_user.name = payload.name.strip()
    current_user.job_title = payload.job_title.strip() if payload.job_title else None
    current_user.bio = payload.bio.strip() if payload.bio else None
    current_user.timezone = payload.timezone.strip()
    current_user.locale = payload.locale.strip()
    current_user.preferences = payload.preferences
    await record_audit(
        db,
        action="auth.profile_updated",
        user_id=current_user.id,
        details={"timezone": current_user.timezone, "locale": current_user.locale},
        ip_address=_client_ip(request),
    )
    await db.commit()
    await db.refresh(current_user)
    return UserRead.model_validate(current_user)


@router.post("/avatar", response_model=UserRead)
async def upload_avatar(
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
    avatar: UploadFile = File(...),
) -> UserRead:
    content_type = (avatar.content_type or "").lower()
    if content_type not in ALLOWED_AVATAR_TYPES:
        raise HTTPException(status_code=400, detail="Avatar deve ser JPEG, PNG ou WEBP.")
    payload = await avatar.read(MAX_AVATAR_BYTES + 1)
    if not payload:
        raise HTTPException(status_code=400, detail="Arquivo de avatar vazio.")
    if len(payload) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=413, detail="Avatar excede o limite de 2 MB.")
    current_user.avatar_blob = payload
    current_user.avatar_mime = content_type
    current_user.avatar_updated_at = datetime.now(UTC)
    await record_audit(
        db,
        action="auth.avatar_updated",
        user_id=current_user.id,
        details={"mime": content_type, "size": len(payload)},
        ip_address=_client_ip(request),
    )
    await db.commit()
    await db.refresh(current_user)
    return UserRead.model_validate(current_user)


@router.delete("/avatar", response_model=UserRead)
async def delete_avatar(
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> UserRead:
    current_user.avatar_blob = None
    current_user.avatar_mime = None
    current_user.avatar_updated_at = None
    await record_audit(
        db,
        action="auth.avatar_removed",
        user_id=current_user.id,
        ip_address=_client_ip(request),
    )
    await db.commit()
    await db.refresh(current_user)
    return UserRead.model_validate(current_user)


@router.get("/users/{user_id}/avatar", include_in_schema=False)
async def avatar(user_id: uuid.UUID, db: DbSession) -> Response:
    user = await db.get(User, user_id)
    if not user or not user.avatar_blob or not user.avatar_mime:
        raise HTTPException(status_code=404, detail="Avatar não encontrado.")
    return Response(
        content=user.avatar_blob,
        media_type=user.avatar_mime,
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )


@router.get("/sessions", response_model=list[SessionRead])
async def sessions(current_user: CurrentUser, db: DbSession) -> list[SessionRead]:
    result = await db.execute(
        select(RefreshToken)
        .where(RefreshToken.user_id == current_user.id)
        .order_by(RefreshToken.created_at.desc())
        .limit(50)
    )
    return [SessionRead.model_validate(item) for item in result.scalars().all()]


@router.delete("/sessions/{session_id}", response_model=MessageResponse)
async def revoke_session(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> MessageResponse:
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.id == session_id,
            RefreshToken.user_id == current_user.id,
        )
    )
    stored = result.scalar_one_or_none()
    if not stored:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    if not stored.revoked_at:
        stored.revoked_at = datetime.now(UTC)
        await db.commit()
    return MessageResponse(message="Sessão revogada.")


@router.post("/sessions/revoke-all", response_model=MessageResponse)
async def revoke_all_sessions(current_user: CurrentUser, db: DbSession) -> MessageResponse:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == current_user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await db.commit()
    return MessageResponse(message="Todas as sessões foram revogadas. Entre novamente.")


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


@router.get("/2fa/status", response_model=TwoFactorStatus)
async def two_factor_status(current_user: CurrentUser) -> TwoFactorStatus:
    return TwoFactorStatus(
        enabled=current_user.totp_enabled,
        confirmed_at=current_user.totp_confirmed_at,
        recovery_codes_remaining=len(current_user.recovery_codes_hashes or []),
    )


@router.post("/2fa/setup", response_model=TwoFactorSetupResponse)
async def setup_two_factor(
    payload: TwoFactorSetupRequest,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> TwoFactorSetupResponse:
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Senha atual incorreta.")

    secret = generate_totp_secret()
    recovery_codes = generate_recovery_codes()
    current_user.totp_secret_encrypted = EncryptionService().encrypt(secret)
    current_user.totp_enabled = False
    current_user.totp_confirmed_at = None
    current_user.recovery_codes_hashes = [hash_recovery_code(code) for code in recovery_codes]

    uri = build_otpauth_uri(secret, str(current_user.email))
    await record_audit(
        db,
        action="auth.2fa_setup_started",
        user_id=current_user.id,
        ip_address=_client_ip(request),
    )
    await db.commit()
    return TwoFactorSetupResponse(
        secret=secret,
        otpauth_uri=uri,
        qr_data_uri=build_qr_data_uri(uri),
        recovery_codes=recovery_codes,
    )


@router.post("/2fa/confirm", response_model=TwoFactorStatus)
async def confirm_two_factor(
    payload: TwoFactorConfirmRequest,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> TwoFactorStatus:
    secret = _second_factor_secret(current_user)
    if not secret:
        raise HTTPException(status_code=400, detail="Inicie a configuração do 2FA primeiro.")
    if not verify_totp(secret, payload.code):
        raise HTTPException(status_code=400, detail="Código 2FA inválido.")

    current_user.totp_enabled = True
    current_user.totp_confirmed_at = datetime.now(UTC)
    await record_audit(
        db,
        action="auth.2fa_enabled",
        user_id=current_user.id,
        ip_address=_client_ip(request),
    )
    await db.commit()
    return TwoFactorStatus(
        enabled=True,
        confirmed_at=current_user.totp_confirmed_at,
        recovery_codes_remaining=len(current_user.recovery_codes_hashes or []),
    )


@router.post("/2fa/disable", response_model=MessageResponse)
async def disable_two_factor(
    payload: TwoFactorDisableRequest,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> MessageResponse:
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Senha atual incorreta.")
    if not current_user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA já está desativado.")
    _validate_second_factor(current_user, payload.code)

    current_user.totp_secret_encrypted = None
    current_user.totp_enabled = False
    current_user.totp_confirmed_at = None
    current_user.recovery_codes_hashes = []
    await record_audit(
        db,
        action="auth.2fa_disabled",
        user_id=current_user.id,
        ip_address=_client_ip(request),
    )
    await db.commit()
    return MessageResponse(message="Autenticação em duas etapas desativada.")


@router.post("/2fa/recovery-codes", response_model=TwoFactorRecoveryCodesResponse)
async def regenerate_recovery_codes(
    payload: TwoFactorRegenerateRecoveryRequest,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> TwoFactorRecoveryCodesResponse:
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Senha atual incorreta.")
    if not current_user.totp_enabled:
        raise HTTPException(status_code=400, detail="Ative o 2FA antes de gerar códigos de recuperação.")
    _validate_second_factor(current_user, payload.code)

    recovery_codes = generate_recovery_codes()
    current_user.recovery_codes_hashes = [hash_recovery_code(code) for code in recovery_codes]
    await record_audit(
        db,
        action="auth.2fa_recovery_regenerated",
        user_id=current_user.id,
        ip_address=_client_ip(request),
    )
    await db.commit()
    return TwoFactorRecoveryCodesResponse(recovery_codes=recovery_codes)
