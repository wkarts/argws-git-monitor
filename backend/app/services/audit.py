from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.request_context import get_request_id
from app.models.activity import AuditLog


async def record_audit(
    session: AsyncSession,
    *,
    action: str,
    user_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    audit_details = dict(details or {})
    correlation_id = get_request_id()
    if correlation_id and "correlation_id" not in audit_details:
        audit_details["correlation_id"] = correlation_id
    session.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=audit_details,
            ip_address=ip_address,
            created_at=datetime.now(UTC),
        )
    )
