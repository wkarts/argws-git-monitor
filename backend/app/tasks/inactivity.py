from __future__ import annotations

import asyncio

from app.core.database import dispose_engine
from app.services.inactivity_monitor import evaluate_inactivity_policies
from app.tasks.celery_app import celery_app


@celery_app.task(name="inactivity.evaluate_all")
def evaluate_inactivity_task():
    async def runner():
        try:
            return await evaluate_inactivity_policies()
        finally:
            await dispose_engine()

    return asyncio.run(runner())
