from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.schemas.notification import NotificationRead
from app.schemas.repository import RepositoryRead, WorkflowRunRead


class DashboardStats(BaseModel):
    total_repositories: int
    private_repositories: int
    public_repositories: int
    healthy: int
    running: int
    attention: int
    failing: int
    unknown: int
    # Métricas introduzidas na v0.4.0 possuem default para manter compatibilidade
    # com fixtures/consumidores anteriores enquanto o backend sempre as preenche.
    health_evaluated: int = 0
    health_pending: int = 0
    average_health_score: int
    average_health_coverage: int = 0
    open_pull_requests: int
    open_issues: int
    unread_notifications: int


class DashboardWorkflow(WorkflowRunRead):
    repository_id: uuid.UUID
    repository_full_name: str


class DashboardResponse(BaseModel):
    stats: DashboardStats
    repositories: list[RepositoryRead]
    recent_workflows: list[DashboardWorkflow]
    recent_notifications: list[NotificationRead]
