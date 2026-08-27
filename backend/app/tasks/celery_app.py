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
    include=[
        "app.tasks.jobs",
        "app.tasks.inactivity",
        "app.tasks.platform",
        "app.tasks.backup_lifecycle",
        "app.tasks.realtime",
    ],
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
    worker_cancel_long_running_tasks_on_connection_loss=True,
    # RabbitMQ 4.x rejeita filas simultaneamente transitórias e não exclusivas.
    # As filas temporárias de pidbox/eventos são exclusivas para não depender do
    # recurso depreciado transient_nonexcl_queues.
    control_queue_exclusive=True,
    event_queue_exclusive=True,
    result_expires=3600,
    beat_schedule={
        "sync-all-github-connections": {
            "task": "github.sync_all_connections",
            "schedule": FULL_SYNC_INTERVAL_SECONDS,
        },
        "ensure-realtime-github-webhooks": {
            "task": "realtime.ensure_repository_webhooks",
            "schedule": 300.0,
        },
        "evaluate-inactivity-policies": {
            "task": "inactivity.evaluate_all",
            "schedule": 900.0,
        },
        "schedule-repository-backups": {
            "task": "platform.schedule_backups",
            "schedule": 300.0,
        },
        "cleanup-old-notifications": {
            "task": "notifications.cleanup",
            "schedule": 86400.0,
        },
    },
)
