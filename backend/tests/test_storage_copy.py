from __future__ import annotations

from app.tasks.storage_hub import copy_snapshot_task


def test_storage_copy_task_is_registered() -> None:
    assert copy_snapshot_task.name == "storage.copy_snapshot"
    assert copy_snapshot_task.max_retries == 2
