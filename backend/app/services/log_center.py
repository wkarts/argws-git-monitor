from __future__ import annotations

import io
import json
import re
import zipfile
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from app.core.config import get_settings
from app.schemas.logs import LogLineRead, LogPurgeResult, LogSourceRead, LogTailResponse


@dataclass(frozen=True, slots=True)
class LogSourceDefinition:
    key: str
    label: str
    category: str
    directory: str
    patterns: tuple[str, ...]


SOURCE_DEFINITIONS: tuple[LogSourceDefinition, ...] = (
    LogSourceDefinition("api", "API FastAPI", "Aplicação", "api", ("*.log*",)),
    LogSourceDefinition("worker", "Celery Worker", "Aplicação", "worker", ("*.log*",)),
    LogSourceDefinition("beat", "Celery Beat", "Aplicação", "beat", ("*.log*",)),
    LogSourceDefinition("migrate", "Migrations / Bootstrap", "Aplicação", "migrate", ("*.log*",)),
    LogSourceDefinition("web-access", "Nginx · acesso", "Web", "web", ("access.log*",)),
    LogSourceDefinition("web-error", "Nginx · erros", "Web", "web", ("error.log*",)),
    LogSourceDefinition("postgres", "PostgreSQL", "Infraestrutura", "postgres", ("*.log*",)),
    LogSourceDefinition("redis", "Redis", "Infraestrutura", "redis", ("*.log*",)),
    LogSourceDefinition("rabbitmq", "RabbitMQ", "Infraestrutura", "rabbitmq", ("*.log*",)),
)
SOURCE_MAP = {item.key: item for item in SOURCE_DEFINITIONS}
LEVEL_RE = re.compile(r"\b(TRACE|DEBUG|INFO|NOTICE|WARN(?:ING)?|ERROR|CRITICAL|FATAL)\b", re.I)
ISO_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}[T ][0-9:.+-]+Z?)")


def _root() -> Path:
    return Path(get_settings().log_stack_root)


def _definition(source: str) -> LogSourceDefinition:
    try:
        return SOURCE_MAP[source]
    except KeyError as exc:
        raise ValueError(f"Fonte de log desconhecida: {source}") from exc


def _safe_files(definition: LogSourceDefinition) -> list[Path]:
    root = _root()
    directory = root / definition.directory
    if not directory.is_dir():
        return []
    files: dict[Path, Path] = {}
    for pattern in definition.patterns:
        for candidate in directory.glob(pattern):
            try:
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(root.resolve(strict=False))
            except (OSError, ValueError):
                continue
            if resolved.is_file():
                files[resolved] = resolved
    return sorted(
        files.values(),
        key=lambda path: path.stat().st_mtime if path.exists() else 0,
        reverse=True,
    )


def source_metadata(source: str) -> LogSourceRead:
    definition = _definition(source)
    files = _safe_files(definition)
    size = 0
    modified: datetime | None = None
    for path in files:
        try:
            stat = path.stat()
        except OSError:
            continue
        size += stat.st_size
        timestamp = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
        if modified is None or timestamp > modified:
            modified = timestamp
    return LogSourceRead(
        key=definition.key,
        label=definition.label,
        category=definition.category,
        available=bool(files),
        file_count=len(files),
        size_bytes=size,
        last_modified_at=modified,
    )


def list_sources() -> list[LogSourceRead]:
    return [source_metadata(item.key) for item in SOURCE_DEFINITIONS]


def _tail_text(path: Path, line_limit: int, byte_limit: int = 8 * 1024 * 1024) -> list[str]:
    if line_limit <= 0:
        return []
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            position = size
            chunks: deque[bytes] = deque()
            newlines = 0
            read_bytes = 0
            block = 64 * 1024
            while position > 0 and newlines <= line_limit and read_bytes < byte_limit:
                step = min(block, position, byte_limit - read_bytes)
                position -= step
                handle.seek(position)
                data = handle.read(step)
                chunks.appendleft(data)
                newlines += data.count(b"\n")
                read_bytes += len(data)
        text = b"".join(chunks).decode("utf-8", errors="replace")
        return text.splitlines()[-line_limit:]
    except OSError:
        return []


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _parse_line(source: str, file_name: str, raw: str) -> LogLineRead:
    stripped = raw.rstrip("\r\n")
    try:
        payload = json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        payload = None

    if isinstance(payload, dict):
        message = str(payload.get("message") or payload.get("msg") or stripped)
        level = str(payload.get("level") or "").upper() or None
        timestamp = _parse_timestamp(payload.get("timestamp") or payload.get("time"))
        return LogLineRead(
            source=source,
            file=file_name,
            timestamp=timestamp,
            level=level,
            logger=str(payload.get("logger") or "") or None,
            service=str(payload.get("service") or "") or None,
            message=message,
            raw=stripped,
            extra={
                key: value
                for key, value in payload.items()
                if key not in {"timestamp", "time", "level", "logger", "service", "message", "msg"}
            },
        )

    match = LEVEL_RE.search(stripped)
    level = match.group(1).upper().replace("WARN", "WARNING") if match else None
    time_match = ISO_PREFIX_RE.match(stripped)
    timestamp = _parse_timestamp(time_match.group(1)) if time_match else None
    return LogLineRead(
        source=source,
        file=file_name,
        timestamp=timestamp,
        level=level,
        message=stripped,
        raw=stripped,
    )


def tail_source(
    source: str,
    *,
    lines: int | None = None,
    query: str | None = None,
    level: str | None = None,
) -> LogTailResponse:
    settings = get_settings()
    line_limit = min(
        max(lines or settings.log_default_tail_lines, 1),
        settings.log_max_tail_lines,
    )
    metadata = source_metadata(source)
    definition = _definition(source)
    files = _safe_files(definition)
    remaining = line_limit
    collected: list[tuple[str, str]] = []
    for path in files:
        if remaining <= 0:
            break
        raw_lines = _tail_text(path, remaining)
        collected[0:0] = [(path.name, raw) for raw in raw_lines]
        remaining = line_limit - len(collected)

    query_normalized = (query or "").casefold().strip()
    level_normalized = (level or "").upper().strip()
    parsed: list[LogLineRead] = []
    for file_name, raw in collected[-line_limit:]:
        item = _parse_line(source, file_name, raw)
        if query_normalized and query_normalized not in item.raw.casefold():
            continue
        if level_normalized and (item.level or "").upper() != level_normalized:
            continue
        parsed.append(item)

    return LogTailResponse(
        source=metadata,
        files=[path.name for path in files],
        lines=parsed,
        truncated=len(collected) >= line_limit,
    )


def _iter_unique_files(sources: Iterable[str]) -> list[tuple[str, Path]]:
    seen: set[Path] = set()
    result: list[tuple[str, Path]] = []
    for source in sources:
        definition = _definition(source)
        for path in _safe_files(definition):
            if path in seen:
                continue
            seen.add(path)
            result.append((source, path))
    return result


def build_log_bundle(sources: Iterable[str]) -> bytes:
    settings = get_settings()
    selected = list(dict.fromkeys(sources)) or list(SOURCE_MAP)
    entries = _iter_unique_files(selected)
    max_bytes = settings.log_download_max_mb * 1024 * 1024
    included_bytes = 0
    manifest: list[dict[str, Any]] = []
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source, path in entries:
            try:
                stat = path.stat()
            except OSError:
                continue
            if included_bytes + stat.st_size > max_bytes:
                manifest.append(
                    {
                        "source": source,
                        "file": path.name,
                        "size_bytes": stat.st_size,
                        "included": False,
                        "reason": "limite_do_bundle",
                    }
                )
                continue
            try:
                data = path.read_bytes()
            except OSError:
                continue
            included_bytes += len(data)
            archive.writestr(f"{source}/{path.name}", data)
            manifest.append(
                {
                    "source": source,
                    "file": path.name,
                    "size_bytes": len(data),
                    "included": True,
                }
            )
        archive.writestr(
            "MANIFEST.json",
            json.dumps(
                {
                    "generated_at": datetime.now(UTC).isoformat(),
                    "max_bundle_mb": settings.log_download_max_mb,
                    "files": manifest,
                },
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8"),
        )
    return buffer.getvalue()


def purge_rotated_logs(older_than_days: int) -> LogPurgeResult:
    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    deleted = 0
    reclaimed = 0
    per_source: dict[str, int] = {}
    seen: set[Path] = set()
    for definition in SOURCE_DEFINITIONS:
        files = _safe_files(definition)
        newest = files[0] if files else None
        count = 0
        for path in files:
            if path in seen or path == newest:
                continue
            seen.add(path)
            try:
                stat = path.stat()
                modified = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
            except OSError:
                continue
            if modified >= cutoff:
                continue
            try:
                size = stat.st_size
                path.unlink()
            except OSError:
                continue
            deleted += 1
            reclaimed += size
            count += 1
        if count:
            per_source[definition.key] = count
    return LogPurgeResult(
        deleted_files=deleted,
        reclaimed_bytes=reclaimed,
        sources=per_source,
    )
