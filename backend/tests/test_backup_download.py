from __future__ import annotations

import uuid

from app.api.routes.backup_download import backup_download_filename
from app.models.github import Repository
from app.models.platform import BackupSnapshot


def test_backup_download_filename_is_safe_and_descriptive() -> None:
    snapshot = BackupSnapshot(
        id=uuid.UUID("11111111-2222-3333-4444-555555555555"),
        user_id=uuid.uuid4(),
        repository_id=uuid.uuid4(),
        provider_id=uuid.uuid4(),
        backup_type="full",
        status="completed",
        permanent=False,
        manifest={},
    )
    repository = Repository(
        id=uuid.uuid4(),
        connection_id=uuid.uuid4(),
        github_id=123,
        owner="wkarts/../unsafe",
        name="ARGWS Git Monitor",
        full_name="wkarts/ARGWS Git Monitor",
        default_branch="main",
        html_url="https://github.com/wkarts/argws-git-monitor",
        private=True,
        monitoring_enabled=True,
    )

    filename = backup_download_filename(repository, snapshot)

    assert filename.endswith(".tar.gz")
    assert ".." not in filename
    assert "/" not in filename
    assert "ARGWS-Git-Monitor" in filename
    assert str(snapshot.id) in filename
