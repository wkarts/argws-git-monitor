from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

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
_UNSET = object()


@dataclass(slots=True, frozen=True)
class HealthResult:
    score: int
    status: HealthStatus
    coverage: int
    reasons: tuple[str, ...]
    components: dict[str, dict[str, Any]]


def _component(
    *,
    label: str,
    weight: int,
    points: int,
    evaluated: bool = True,
    detail: str,
) -> dict[str, Any]:
    return {
        "label": label,
        "weight": weight,
        "points": max(0, min(weight, points)),
        "evaluated": evaluated,
        "detail": detail,
    }


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
    last_synced_at: datetime | None | object = _UNSET,
    now: datetime | None = None,
) -> HealthResult:
    """Calcula saúde somente sobre evidências observadas.

    Quando ``last_synced_at`` é explicitamente ``None`` o repositório ainda não
    possui uma leitura detalhada e fica UNKNOWN. A omissão desse argumento mantém
    compatibilidade com o cálculo executado dentro do próprio ciclo de sync.
    """

    current_time = now or datetime.now(UTC)
    if last_synced_at is None:
        return HealthResult(
            score=0,
            status=HealthStatus.UNKNOWN,
            coverage=0,
            reasons=("Aguardando primeira sincronização detalhada",),
            components={},
        )
    effective_sync = current_time if last_synced_at is _UNSET else last_synced_at
    assert isinstance(effective_sync, datetime)

    reasons: list[str] = []
    components: dict[str, dict[str, Any]] = {}

    availability_points = 20
    availability_detail = "Repositório disponível"
    if disabled:
        availability_points = 0
        availability_detail = "Repositório desabilitado no GitHub"
        reasons.append(availability_detail)
    elif archived:
        availability_points = 10
        availability_detail = "Repositório arquivado"
        reasons.append(availability_detail)
    components["availability"] = _component(
        label="Disponibilidade",
        weight=20,
        points=availability_points,
        detail=availability_detail,
    )

    synced = effective_sync if effective_sync.tzinfo else effective_sync.replace(tzinfo=UTC)
    sync_age_minutes = max(int((current_time - synced).total_seconds() // 60), 0)
    if sync_error:
        sync_points = 0
        sync_detail = "Última sincronização terminou com erro"
        reasons.append(sync_detail)
    elif sync_age_minutes <= 30:
        sync_points = 25
        sync_detail = f"Sincronizado há {sync_age_minutes} min"
    elif sync_age_minutes <= 180:
        sync_points = 20
        sync_detail = f"Sincronizado há {sync_age_minutes // 60} h"
    elif sync_age_minutes <= 1440:
        sync_points = 12
        sync_detail = "Sincronização com mais de 3 horas"
        reasons.append(sync_detail)
    else:
        sync_points = 5
        sync_detail = "Sincronização com mais de 24 horas"
        reasons.append(sync_detail)
    components["sync"] = _component(
        label="Sincronização",
        weight=25,
        points=sync_points,
        detail=sync_detail,
    )

    if pushed_at is None:
        activity_points = 8
        activity_detail = "Nenhum push localizado"
        reasons.append(activity_detail)
    else:
        pushed = pushed_at if pushed_at.tzinfo else pushed_at.replace(tzinfo=UTC)
        inactivity_days = max((current_time - pushed).days, 0)
        if inactivity_days < 30:
            activity_points = 20
            activity_detail = f"Atividade recente ({inactivity_days} dias)"
        elif inactivity_days < 60:
            activity_points = 16
            activity_detail = f"Sem push há {inactivity_days} dias"
        elif inactivity_days < 180:
            activity_points = 10
            activity_detail = f"Sem push há {inactivity_days} dias"
            reasons.append(activity_detail)
        else:
            activity_points = 4
            activity_detail = f"Sem push há {inactivity_days} dias"
            reasons.append(activity_detail)
    components["activity"] = _component(
        label="Atividade",
        weight=20,
        points=activity_points,
        detail=activity_detail,
    )

    normalized_status = (latest_workflow_status or "").lower()
    normalized_conclusion = (latest_workflow_conclusion or "").lower()
    has_ci = bool(normalized_status or normalized_conclusion)
    if not has_ci:
        components["ci"] = _component(
            label="CI/CD",
            weight=25,
            points=0,
            evaluated=False,
            detail="Nenhum GitHub Actions localizado (não avaliado)",
        )
    elif normalized_status in RUNNING_STATUSES:
        components["ci"] = _component(
            label="CI/CD", weight=25, points=20, detail="Workflow em execução"
        )
        reasons.append("Workflow em execução")
    elif normalized_conclusion in FAILURE_CONCLUSIONS:
        components["ci"] = _component(
            label="CI/CD",
            weight=25,
            points=0,
            detail=f"Último workflow: {normalized_conclusion}",
        )
        reasons.append(f"Último workflow terminou como {normalized_conclusion}")
    elif normalized_conclusion in {"neutral", "skipped"}:
        components["ci"] = _component(
            label="CI/CD",
            weight=25,
            points=18,
            detail=f"Último workflow: {normalized_conclusion}",
        )
    else:
        components["ci"] = _component(
            label="CI/CD",
            weight=25,
            points=25,
            detail=f"Último workflow: {normalized_conclusion or normalized_status}",
        )

    backlog_points = 10
    backlog_notes: list[str] = []
    if open_pr_count >= 25:
        backlog_points -= 5
        backlog_notes.append(f"{open_pr_count} PRs abertas")
    elif open_pr_count >= 10:
        backlog_points -= 2
        backlog_notes.append(f"{open_pr_count} PRs abertas")
    if open_issue_count >= 100:
        backlog_points -= 5
        backlog_notes.append(f"{open_issue_count} issues abertas")
    elif open_issue_count >= 50:
        backlog_points -= 2
        backlog_notes.append(f"{open_issue_count} issues abertas")
    backlog_detail = ", ".join(backlog_notes) if backlog_notes else "Backlog dentro dos limites"
    if backlog_notes:
        reasons.append(backlog_detail)
    components["backlog"] = _component(
        label="Backlog", weight=10, points=backlog_points, detail=backlog_detail
    )

    evaluated_weight = sum(
        int(item["weight"]) for item in components.values() if bool(item["evaluated"])
    )
    earned_points = sum(
        int(item["points"]) for item in components.values() if bool(item["evaluated"])
    )
    coverage = max(0, min(100, evaluated_weight))
    score = round((earned_points / evaluated_weight) * 100) if evaluated_weight else 0
    score = max(0, min(100, score))

    if coverage < 50:
        status = HealthStatus.UNKNOWN
    elif disabled or normalized_conclusion in FAILURE_CONCLUSIONS or score < 55:
        status = HealthStatus.FAILING
    elif normalized_status in RUNNING_STATUSES and score >= 55:
        status = HealthStatus.RUNNING
    elif archived or bool(sync_error) or score < 85:
        status = HealthStatus.ATTENTION
    else:
        status = HealthStatus.HEALTHY

    return HealthResult(
        score=score,
        status=status,
        coverage=coverage,
        reasons=tuple(reasons),
        components=components,
    )
