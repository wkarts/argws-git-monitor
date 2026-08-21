from __future__ import annotations

from celery import Celery

from app.core.config import get_settings
from app.core.logging import configure_logging

configure_logging()
settings = get_settings()

# A reconciliação completa consulta vários recursos por repositório. Para contas
# grandes, intervalos de poucos minutos esgotam o rate limit REST. Webhooks cobrem
# mudanças imediatas; o full-sync fica como reconciliação horária mínima.
FULL_SYNC_INTERVAL_SECONDS = max(float(settings.sync_interval_seconds), 3600.0)

celery_app = Celery(
    "argws_git_monitor",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.jobs", "app.tasks.inactivity"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="America/Bahia",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    worker_hijack_root_logger=False,
    broker_connection_retry_on_startup=True,
    result_expires=3600,
    beat_schedule={
        "sync-all-github-connections": {
            "task": "github.sync_all_connections",
            "schedule": FULL_SYNC_INTERVAL_SECONDS,
        },
        "evaluate-inactivity-policies": {
            "task": "inactivity.evaluate_all",
            "schedule": 900.0,
        },
        "cleanup-old-notifications": {
            "task": "notifications.cleanup",
            "schedule": 86400.0,
        },
    },
)
