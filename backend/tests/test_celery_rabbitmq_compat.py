from app.tasks.celery_app import celery_app


def test_celery_control_queues_are_rabbitmq43_compatible() -> None:
    assert celery_app.conf.control_queue_exclusive is True
    assert celery_app.conf.control_queue_durable is False


def test_celery_event_queues_are_exclusive() -> None:
    assert celery_app.conf.event_queue_exclusive is True
    assert celery_app.conf.event_queue_durable is False
