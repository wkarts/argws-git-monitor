from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.models.github import HealthStatus

FAILURE_CONCLUSIONS = {
    "failure",
    "cancelled",
    "timed_out",
    "action_required",
    "startup_failure",
    "stale",
}
RUNNING_STATUSES = {"queued", "requested", "waiting", "pending", "in_progress"}


@dataclass(slots=True, frozen=True)
class HealthResult:
    score: int
    status: HealthStatus
    reasons: tuple[str, ...]


def calculate_repository_health(
    *,
    archived: bool,
    disabled: bool,
    sync_error: str | None,
    pushed_at: datetime | None,
    latest_workflow_status: str | None,
    latest_workflow_conclusion: str | None,
    open_pr_count: int,
    open_issue_count: int,
    now: datetime | None = None,
) -> HealthResult:
    current_time = now or datetime.now(UTC)
    score = 100
    reasons: list[str] = []

    if disabled:
        score -= 80
        reasons.append("Repositório desabilitado no GitHub")
    elif archived:
        score -= 35
        reasons.append("Repositório arquivado")

    if sync_error:
        score -= 35
        reasons.append("Última sincronização terminou com erro")

    normalized_status = (latest_workflow_status or "").lower()
    normalized_conclusion = (latest_workflow_conclusion or "").lower()

    if normalized_status in RUNNING_STATUSES:
        reasons.append("Workflow em execução")
    elif normalized_conclusion in FAILURE_CONCLUSIONS:
        score -= 50
        reasons.append(f"Último workflow terminou como {normalized_conclusion}")
    elif normalized_conclusion in {"neutral", "skipped"}:
        score -= 5
        reasons.append(f"Último workflow terminou como {normalized_conclusion}")
    elif not latest_workflow_status and not latest_workflow_conclusion:
        score -= 10
        reasons.append("Nenhum workflow localizado")

    if pushed_at:
        pushed = pushed_at if pushed_at.tzinfo else pushed_at.replace(tzinfo=UTC)
        inactivity_days = max((current_time - pushed).days, 0)
        if inactivity_days >= 180:
            score -= 25
            reasons.append(f"Sem push há {inactivity_days} dias")
        elif inactivity_days >= 60:
            score -= 15
            reasons.append(f"Sem push há {inactivity_days} dias")
        elif inactivity_days >= 30:
            score -= 8
            reasons.append(f"Sem push há {inactivity_days} dias")

    if open_pr_count >= 25:
        score -= 10
        reasons.append("Grande quantidade de pull requests abertas")
    elif open_pr_count >= 10:
        score -= 5
        reasons.append("Muitas pull requests abertas")

    if open_issue_count >= 100:
        score -= 10
        reasons.append("Grande quantidade de issues abertas")
    elif open_issue_count >= 50:
        score -= 5
        reasons.append("Muitas issues abertas")

    score = max(0, min(100, score))

    if normalized_status in RUNNING_STATUSES and score >= 55:
        status = HealthStatus.RUNNING
    elif score < 45 or disabled or normalized_conclusion in FAILURE_CONCLUSIONS:
        status = HealthStatus.FAILING
    elif score < 75 or archived or bool(sync_error):
        status = HealthStatus.ATTENTION
    elif not latest_workflow_status and not latest_workflow_conclusion:
        status = HealthStatus.UNKNOWN
    else:
        status = HealthStatus.HEALTHY

    return HealthResult(score=score, status=status, reasons=tuple(reasons))
