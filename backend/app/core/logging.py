from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from app.core.config import get_settings


class JsonFormatter(logging.Formatter):
    def __init__(self, service_role: str) -> None:
        super().__init__()
        self.service_role = service_role

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "service": self.service_role,
            "message": record.getMessage(),
            "process": record.process,
            "thread": record.thread,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    if getattr(root, "_argws_configured", False):
        return

    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root.addHandler(console)

    if settings.log_file:
        try:
            path = Path(settings.log_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = TimedRotatingFileHandler(
                path,
                when="midnight",
                backupCount=max(settings.log_retention_days, 1),
                encoding="utf-8",
                utc=True,
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(JsonFormatter(settings.service_role))
            root.addHandler(file_handler)
        except OSError as exc:
            console.emit(
                logging.LogRecord(
                    name="app.logging",
                    level=logging.WARNING,
                    pathname=__file__,
                    lineno=0,
                    msg=f"Não foi possível abrir LOG_FILE={settings.log_file}: {exc}",
                    args=(),
                    exc_info=None,
                )
            )

    root._argws_configured = True  # type: ignore[attr-defined]
    logging.captureWarnings(True)

    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "Logging configurado",
        extra={"service_role": settings.service_role, "pid": os.getpid()},
    )
