from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.deps import DbSession, require_superuser
from app.core.permissions import normalize_permissions, permission_catalog
from app.models.user import User
from app.services.audit import record_audit

router = APIRouter(prefix="/admin", tags=["Administração"])
AdminUser = Annotated[User, Depends(require_superuser)]


class PermissionUpdate(BaseModel):
    permissions: list[str] = Field(default_factory=list)


class PermissionState(BaseModel):
    user_id: uuid.UUID
    permissions: list[str]


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()[:64]
    return request.client.host[:64] if request.client else None


@router.get("/permissions/catalog")
async def catalog(_: AdminUser) -> list[dict[str, str]]:
    return permission_catalog()


@router.get("/users/{user_id}/permissions", response_model=PermissionState)
async def get_user_permissions(
    user_id: uuid.UUID,
    _: AdminUser,
    db: DbSession,
) -> PermissionState:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    permissions = list((user.preferences or {}).get("permissions") or [])
    return PermissionState(user_id=user.id, permissions=permissions)


@router.put("/users/{user_id}/permissions", response_model=PermissionState)
async def update_user_permissions(
    user_id: uuid.UUID,
    payload: PermissionUpdate,
    request: Request,
    admin: AdminUser,
    db: DbSession,
) -> PermissionState:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    try:
        permissions = normalize_permissions(payload.permissions)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    preferences = dict(user.preferences or {})
    previous = list(preferences.get("permissions") or [])
    preferences["permissions"] = permissions
    user.preferences = preferences
    await record_audit(
        db,
        action="admin.user_permissions_updated",
        user_id=admin.id,
        entity_type="user",
        entity_id=str(user.id),
        details={
            "target_email": user.email,
            "previous_permissions": previous,
            "permissions": permissions,
        },
        ip_address=_client_ip(request),
    )
    await db.commit()
    return PermissionState(user_id=user.id, permissions=permissions)
