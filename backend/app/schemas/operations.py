from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class OperationWorkflowRead(BaseModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    repository_full_name: str
    repository_private: bool
    github_id: int
    name: str
    display_title: str | None
    event: str | None
    status: str
    conclusion: str | None
    head_branch: str | None
    head_sha: str | None
    run_number: int | None
    run_attempt: int | None
    html_url: str
    actor_login: str | None
    github_created_at: datetime | None
    github_updated_at: datetime | None
    run_started_at: datetime | None
    duration_seconds: int | None


class OperationPullRequestRead(BaseModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    repository_full_name: str
    repository_private: bool
    github_id: int
    number: int
    title: str
    state: str
    draft: bool
    html_url: str
    user_login: str | None
    head_ref: str | None
    base_ref: str | None
    mergeable_state: str | None
    github_created_at: datetime | None
    github_updated_at: datetime | None
    closed_at: datetime | None
    merged_at: datetime | None


class OperationReleaseRead(BaseModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    repository_full_name: str
    repository_private: bool
    github_id: int
    tag_name: str
    name: str | None
    draft: bool
    prerelease: bool
    html_url: str
    target_commitish: str | None
    github_created_at: datetime | None
    published_at: datetime | None


class OperationIssueRead(BaseModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    repository_full_name: str
    repository_private: bool
    github_id: int
    number: int
    title: str
    state: str
    html_url: str
    user_login: str | None
    comments: int
    locked: bool
    labels: list[str] = Field(default_factory=list)
    github_created_at: datetime | None
    github_updated_at: datetime | None
    closed_at: datetime | None


class IssueCreateRequest(BaseModel):
    repository_id: uuid.UUID
    title: str = Field(min_length=1, max_length=1000)
    body: str | None = Field(default=None, max_length=65536)


class IssueStateRequest(BaseModel):
    state: str = Field(pattern="^(open|closed)$")


class IssueSummaryRead(BaseModel):
    repository_id: uuid.UUID
    repository_full_name: str
    repository_private: bool
    repository_html_url: str
    open_issue_count: int
    health_score: int
    health_status: str
    last_synced_at: datetime | None
