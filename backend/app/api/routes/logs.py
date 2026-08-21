from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload

from app.api.deps import DbSession, require_superuser
from app.models.activity import AuditLog
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.logs import AuditLogRead, LogPurgeRequest, LogPurgeResult, LogSourceRead, LogTailResponse
from app.services.audit import record_audit
from app.services.log_center import build_log_bundle, list_sources, purge_rotated_logs, tail_source

router = APIRouter(prefix="/admin/logs", tags=["Central de Logs"])


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else None


@router.get("/sources", response_model=list[LogSourceRead])
async def sources(_: User = Depends(require_superuser)) -> list[LogSourceRead]:
    return list_sources()


@router.get("/tail/{source}", response_model=LogTailResponse)
async def tail(
    source: str,
    _: User = Depends(require_superuser),
    lines: int = Query(default=500, ge=1, le=10000),
    q: str | None = Query(default=None, max_length=300),
    level: str | None = Query(default=None, max_length=20),
) -> LogTailResponse:
    try:
        return tail_source(source, lines=lines, query=q, level=level)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/audit", response_model=list[AuditLogRead])
async def audit_logs(
    _: User = Depends(require_superuser),
    db: DbSession = None,
    q: str | None = Query(default=None, max_length=300),
    action: str | None = Query(default=None, max_length=150),
    limit: int = Query(default=300, ge=1, le=2000),
) -> list[AuditLogRead]:
    query = select(AuditLog).options(joinedload(AuditLog.user))
    if action:
        query = query.where(AuditLog.action.ilike(f"%{action.strip()}%"))
    if q:
        term = f"%{q.strip()}%"
        query = query.join(User, AuditLog.user_id == User.id, isouter=True).where(
            or_(
                AuditLog.action.ilike(term),
                AuditLog.entity_type.ilike(term),
                AuditLog.entity_id.ilike(term),
                AuditLog.ip_address.ilike(term),
                User.name.ilike(term),
                User.email.ilike(term),
            )
        )
    rows = (
        await db.execute(query.order_by(AuditLog.created_at.desc()).limit(limit))
    ).scalars().unique().all()
    return [
        AuditLogRead(
            id=item.id,
            user_id=item.user_id,
            user_name=item.user.name if item.user else None,
            user_email=item.user.email if item.user else None,
            action=item.action,
            entity_type=item.entity_type,
            entity_id=item.entity_id,
            details=item.details or {},
            ip_address=item.ip_address,
            created_at=item.created_at,
        )
        for item in rows
    ]


async def _audit_csv(db: DbSession) -> bytes:
    rows = (
        await db.execute(
            select(AuditLog).options(joinedload(AuditLog.user)).order_by(AuditLog.created_at.desc())
        )
    ).scalars().unique().all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "created_at", "action", "user_id", "user_name", "user_email", "entity_type",
        "entity_id", "ip_address", "details_json"
    ])
    for item in rows:
        writer.writerow([
            item.created_at.isoformat(),
            item.action,
            str(item.user_id or ""),
            item.user.name if item.user else "",
            item.user.email if item.user else "",
            item.entity_type or "",
            item.entity_id or "",
            item.ip_address or "",
            json.dumps(item.details or {}, ensure_ascii=False),
        ])
    return buffer.getvalue().encode("utf-8-sig")


@router.get("/download")
async def download_logs(
    request: Request,
    admin: User = Depends(require_superuser),
    db: DbSession = None,
    source: list[str] = Query(default=[]),
    include_audit: bool = True,
):
    extra = {"audit/audit.csv": await _audit_csv(db)} if include_audit else None
    try:
        payload = build_log_bundle(source, extra_files=extra)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await record_audit(
        db,
        action="admin.logs_downloaded",
        user_id=admin.id,
        details={"sources": source or ["all"], "include_audit": include_audit},
        ip_address=_client_ip(request),
    )
    await db.commit()
    filename = f"argws-git-monitor-logs-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.zip"
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/purge", response_model=LogPurgeResult)
async def purge_logs(
    payload: LogPurgeRequest,
    request: Request,
    admin: User = Depends(require_superuser),
    db: DbSession = None,
) -> LogPurgeResult:
    if payload.confirmation != "PURGAR LOGS":
        raise HTTPException(status_code=400, detail='Digite exatamente "PURGAR LOGS".')
    result = purge_rotated_logs(payload.older_than_days)
    await record_audit(
        db,
        action="admin.logs_purged",
        user_id=admin.id,
        details={
            "older_than_days": payload.older_than_days,
            "deleted_files": result.deleted_files,
            "reclaimed_bytes": result.reclaimed_bytes,
        },
        ip_address=_client_ip(request),
    )
    await db.commit()
    return result
