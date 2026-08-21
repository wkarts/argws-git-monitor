from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.models.github import HealthStatus
from app.schemas.common import ORMModel
from app.services.health import calculate_repository_health


class WorkflowRunRead(ORMModel):
    id: uuid.UUID
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


class PullRequestRead(ORMModel):
    id: uuid.UUID
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


class ReleaseRead(ORMModel):
    id: uuid.UUID
    github_id: int
    tag_name: str
    name: str | None
    draft: bool
    prerelease: bool
    html_url: str
    target_commitish: str | None
    github_created_at: datetime | None
    published_at: datetime | None


class RepositoryRead(ORMModel):
    id: uuid.UUID
    connection_id: uuid.UUID
    github_id: int
    owner: str
    name: str
    full_name: str
    html_url: str
    description: str | None
    private: bool
    fork: bool
    archived: bool
    disabled: bool
    visibility: str
    default_branch: str
    language: str | None
    stargazers_count: int
    forks_count: int
    open_issue_count: int
    open_pr_count: int
    branch_count: int
    pushed_at: datetime | None
    latest_commit_sha: str | None
    latest_commit_message: str | None
    latest_commit_author: str | None
    latest_commit_at: datetime | None
    latest_release_tag: str | None
    latest_release_name: str | None
    latest_release_at: datetime | None
    latest_workflow_id: int | None
    latest_workflow_name: str | None
    latest_workflow_status: str | None
    latest_workflow_conclusion: str | None
    latest_workflow_url: str | None
    latest_workflow_at: datetime | None
    health_score: int
    health_status: HealthStatus
    health_coverage: int = 0
    health_reasons: list[str] = Field(default_factory=list)
    health_components: dict[str, dict[str, Any]] = Field(default_factory=dict)
    monitoring_enabled: bool
    last_synced_at: datetime | None
    sync_error: str | None

    @model_validator(mode="after")
    def calculate_explainable_health(self) -> RepositoryRead:
        result = calculate_repository_health(
            archived=self.archived,
            disabled=self.disabled,
            sync_error=self.sync_error,
            last_synced_at=self.last_synced_at,
            pushed_at=self.pushed_at,
            latest_workflow_status=self.latest_workflow_status,
            latest_workflow_conclusion=self.latest_workflow_conclusion,
            open_pr_count=self.open_pr_count,
            open_issue_count=self.open_issue_count,
        )
        self.health_score = result.score
        self.health_status = result.status
        self.health_coverage = result.coverage
        self.health_reasons = list(result.reasons)
        self.health_components = result.components
        return self


class RepositoryDetail(RepositoryRead):
    workflow_runs: list[WorkflowRunRead]
    pull_requests: list[PullRequestRead]
    releases: list[ReleaseRead]


class RepositoryUpdate(BaseModel):
    monitoring_enabled: bool


class RepositoryRemoteUpdate(BaseModel):
    private: bool | None = None
    archived: bool | None = None
    description: str | None = Field(default=None, max_length=350)


class RepositoryDeleteRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=520)


class WorkflowActionResponse(BaseModel):
    message: str
    run_id: int
