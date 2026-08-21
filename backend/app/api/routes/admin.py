from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select, update

from app.api.deps import DbSession, require_superuser
from app.core.security import hash_password
from app.models.github import GitHubConnection, Repository
from app.models.user import RefreshToken, User
from app.schemas.admin import (
    AdminOverview,
    AdminPasswordResetResponse,
    AdminUserCreate,
    AdminUserRead,
    AdminUserUpdate,
)
from app.schemas.common import MessageResponse
from app.services.audit import record_audit

router = APIRouter(prefix="/admin", tags=["Administração"])
AdminUser = Annotated[User, Depends(require_superuser)]


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else None


async def _get_user(db: DbSession, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return user


async def _active_superuser_count(db: DbSession) -> int:
    return int(
        (
            await db.execute(
                select(func.count(User.id)).where(User.is_superuser.is_(True), User.is_active.is_(True))
            )
        ).scalar_one()
    )


def _row_to_read(row) -> AdminUserRead:
    user, connection_count, repository_count, session_count = row
    return AdminUserRead(
        id=user.id,
        name=user.name,
        email=user.email,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        must_change_password=user.must_change_password,
        totp_enabled=user.totp_enabled,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        github_connection_count=int(connection_count or 0),
        repository_count=int(repository_count or 0),
        active_session_count=int(session_count or 0),
    )


@router.get("/overview", response_model=AdminOverview)
async def overview(_: AdminUser, db: DbSession) -> AdminOverview:
    total_users = int((await db.execute(select(func.count(User.id)))).scalar_one())
    active_users = int(
        (await db.execute(select(func.count(User.id)).where(User.is_active.is_(True)))).scalar_one()
    )
    administrators = int(
        (await db.execute(select(func.count(User.id)).where(User.is_superuser.is_(True)))).scalar_one()
    )
    two_factor_enabled = int(
        (await db.execute(select(func.count(User.id)).where(User.totp_enabled.is_(True)))).scalar_one()
    )
    active_sessions = int(
        (
            await db.execute(
                select(func.count(RefreshToken.id)).where(
                    RefreshToken.revoked_at.is_(None),
                    RefreshToken.expires_at > datetime.now(UTC),
                )
            )
        ).scalar_one()
    )
    return AdminOverview(
        total_users=total_users,
        active_users=active_users,
        administrators=administrators,
        two_factor_enabled=two_factor_enabled,
        active_sessions=active_sessions,
    )


@router.get("/users", response_model=list[AdminUserRead])
async def list_users(
    _: AdminUser,
    db: DbSession,
    q: str | None = Query(default=None, max_length=200),
) -> list[AdminUserRead]:
    connection_count = (
        select(func.count(GitHubConnection.id))
        .where(GitHubConnection.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    repository_count = (
        select(func.count(Repository.id))
        .select_from(Repository)
        .join(GitHubConnection, Repository.connection_id == GitHubConnection.id)
        .where(GitHubConnection.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    session_count = (
        select(func.count(RefreshToken.id))
        .where(
            RefreshToken.user_id == User.id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > datetime.now(UTC),
        )
        .correlate(User)
        .scalar_subquery()
    )
    query = select(User, connection_count, repository_count, session_count)
    if q and q.strip():
        search = f"%{q.strip()}%"
        query = query.where(User.name.ilike(search) | User.email.ilike(search))
    result = await db.execute(query.order_by(User.is_superuser.desc(), User.name.asc()))
    return [_row_to_read(row) for row in result.all()]


@router.post("/users", response_model=AdminUserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: AdminUserCreate,
    request: Request,
    admin: AdminUser,
    db: DbSession,
) -> AdminUserRead:
    email = str(payload.email).lower()
    existing = (await db.execute(select(User.id).where(User.email == email))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Já existe um usuário com este e-mail.")

    user = User(
        name=payload.name.strip(),
        email=email,
        password_hash=hash_password(payload.password),
        is_active=payload.is_active,
        is_superuser=payload.is_superuser,
        must_change_password=payload.must_change_password,
        totp_enabled=False,
        recovery_codes_hashes=[],
    )
    db.add(user)
    await db.flush()
    await record_audit(
        db,
        action="admin.user_created",
        user_id=admin.id,
        entity_type="user",
        entity_id=str(user.id),
        details={"email": email, "is_superuser": user.is_superuser},
        ip_address=_client_ip(request),
    )
    await db.commit()
    await db.refresh(user)
    return AdminUserRead(
        id=user.id,
        name=user.name,
        email=user.email,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        must_change_password=user.must_change_password,
        totp_enabled=user.totp_enabled,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )


@router.patch("/users/{user_id}", response_model=AdminUserRead)
async def update_user(
    user_id: uuid.UUID,
    payload: AdminUserUpdate,
    request: Request,
    admin: AdminUser,
    db: DbSession,
) -> AdminUserRead:
    user = await _get_user(db, user_id)
    changes = payload.model_dump(exclude_unset=True)

    if user.id == admin.id:
        if changes.get("is_active") is False:
            raise HTTPException(status_code=400, detail="Você não pode desativar a própria conta.")
        if changes.get("is_superuser") is False:
            raise HTTPException(status_code=400, detail="Você não pode remover o próprio acesso administrativo.")

    if user.is_superuser and user.is_active and (
        changes.get("is_superuser") is False or changes.get("is_active") is False
    ):
        if await _active_superuser_count(db) <= 1:
            raise HTTPException(status_code=400, detail="A plataforma precisa manter ao menos um administrador ativo.")

    if "email" in changes and changes["email"] is not None:
        email = str(changes["email"]).lower()
        existing = (
            await db.execute(select(User.id).where(User.email == email, User.id != user.id))
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail="Já existe um usuário com este e-mail.")
        user.email = email
    if changes.get("name") is not None:
        user.name = str(changes["name"]).strip()
    for field in ("is_active", "is_superuser", "must_change_password"):
        if field in changes and changes[field] is not None:
            setattr(user, field, bool(changes[field]))

    if changes.get("is_active") is False:
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )

    await record_audit(
        db,
        action="admin.user_updated",
        user_id=admin.id,
        entity_type="user",
        entity_id=str(user.id),
        details={key: value for key, value in changes.items() if key != "email"} | {"email": user.email},
        ip_address=_client_ip(request),
    )
    await db.commit()
    await db.refresh(user)
    return AdminUserRead(
        id=user.id,
        name=user.name,
        email=user.email,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        must_change_password=user.must_change_password,
        totp_enabled=user.totp_enabled,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )


@router.post("/users/{user_id}/reset-password", response_model=AdminPasswordResetResponse)
async def reset_password(
    user_id: uuid.UUID,
    request: Request,
    admin: AdminUser,
    db: DbSession,
) -> AdminPasswordResetResponse:
    user = await _get_user(db, user_id)
    temporary_password = secrets.token_urlsafe(18)
    user.password_hash = hash_password(temporary_password)
    user.must_change_password = True
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await record_audit(
        db,
        action="admin.password_reset",
        user_id=admin.id,
        entity_type="user",
        entity_id=str(user.id),
        ip_address=_client_ip(request),
    )
    await db.commit()
    return AdminPasswordResetResponse(
        message="Senha temporária gerada e sessões revogadas.",
        temporary_password=temporary_password,
    )


@router.post("/users/{user_id}/revoke-sessions", response_model=MessageResponse)
async def revoke_user_sessions(
    user_id: uuid.UUID,
    request: Request,
    admin: AdminUser,
    db: DbSession,
) -> MessageResponse:
    user = await _get_user(db, user_id)
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await record_audit(
        db,
        action="admin.sessions_revoked",
        user_id=admin.id,
        entity_type="user",
        entity_id=str(user.id),
        ip_address=_client_ip(request),
    )
    await db.commit()
    return MessageResponse(message="Sessões do usuário revogadas.")


@router.post("/users/{user_id}/reset-2fa", response_model=MessageResponse)
async def reset_user_two_factor(
    user_id: uuid.UUID,
    request: Request,
    admin: AdminUser,
    db: DbSession,
) -> MessageResponse:
    user = await _get_user(db, user_id)
    user.totp_secret_encrypted = None
    user.totp_enabled = False
    user.totp_confirmed_at = None
    user.recovery_codes_hashes = []
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await record_audit(
        db,
        action="admin.2fa_reset",
        user_id=admin.id,
        entity_type="user",
        entity_id=str(user.id),
        ip_address=_client_ip(request),
    )
    await db.commit()
    return MessageResponse(message="2FA removido e sessões revogadas.")


@router.delete("/users/{user_id}", response_model=MessageResponse)
async def delete_user(
    user_id: uuid.UUID,
    request: Request,
    admin: AdminUser,
    db: DbSession,
) -> MessageResponse:
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Você não pode excluir a própria conta.")
    user = await _get_user(db, user_id)
    if user.is_superuser and user.is_active and await _active_superuser_count(db) <= 1:
        raise HTTPException(status_code=400, detail="A plataforma precisa manter ao menos um administrador ativo.")

    email = user.email
    await record_audit(
        db,
        action="admin.user_deleted",
        user_id=admin.id,
        entity_type="user",
        entity_id=str(user.id),
        details={"email": email},
        ip_address=_client_ip(request),
    )
    await db.delete(user)
    await db.commit()
    return MessageResponse(message=f"Usuário {email} removido.")
