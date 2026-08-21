from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=512)
    otp_code: str | None = Field(default=None, min_length=6, max_length=32)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=32)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=12, max_length=512)


class TwoFactorSetupRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=512)


class TwoFactorConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=32)


class TwoFactorDisableRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=512)
    code: str = Field(min_length=6, max_length=32)


class TwoFactorRegenerateRecoveryRequest(TwoFactorDisableRequest):
    pass


class TwoFactorStatus(BaseModel):
    enabled: bool
    confirmed_at: datetime | None = None
    recovery_codes_remaining: int = 0


class TwoFactorSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str
    qr_data_uri: str
    recovery_codes: list[str]


class TwoFactorRecoveryCodesResponse(BaseModel):
    recovery_codes: list[str]


class SessionRead(ORMModel):
    id: uuid.UUID
    expires_at: datetime
    revoked_at: datetime | None
    user_agent: str | None
    ip_address: str | None
    created_at: datetime


class UserRead(ORMModel):
    id: uuid.UUID
    name: str
    email: EmailStr
    is_active: bool
    is_superuser: bool
    must_change_password: bool
    totp_enabled: bool = False
    totp_confirmed_at: datetime | None = None
    last_login_at: datetime | None
    created_at: datetime


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    access_expires_at: datetime
    refresh_expires_at: datetime
    user: UserRead
