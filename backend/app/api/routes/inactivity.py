from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import delete, select

from app.api.deps import CurrentUser, DbSession
from app.models.github import GitHubConnection, Repository
from app.models.inactivity import (
    InactivityActionLog,
    InactivityPolicy,
    InactivityPolicyRepository,
)
from app.schemas.common import MessageResponse
from app.schemas.inactivity import (
    InactivityActionLogRead,
    InactivityEvaluationResult,
    InactivityPolicyCreate,
    InactivityPolicyRead,
    InactivityPolicyUpdate,
)
from app.services.inactivity_monitor import evaluate_inactivity_policies

router = APIRouter(prefix="/inactivity-policies", tags=["Automação por inatividade"])


async def _owned_policy(db: DbSession, policy_id: uuid.UUID, user_id: uuid.UUID) -> InactivityPolicy:
    result = await db.execute(
        select(InactivityPolicy).where(
            InactivityPolicy.id == policy_id,
            InactivityPolicy.user_id == user_id,
        )
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Política de inatividade não encontrada.")
    return policy


async def _validate_repositories(
    db: DbSession,
    repository_ids: list[uuid.UUID],
    user_id: uuid.UUID,
) -> list[uuid.UUID]:
    unique_ids = list(dict.fromkeys(repository_ids))
    if not unique_ids:
        return []
    result = await db.execute(
        select(Repository.id)
        .join(GitHubConnection, Repository.connection_id == GitHubConnection.id)
        .where(
            Repository.id.in_(unique_ids),
            GitHubConnection.user_id == user_id,
        )
    )
    valid = list(result.scalars().all())
    if len(valid) != len(unique_ids):
        raise HTTPException(
            status_code=400,
            detail="Um ou mais repositórios não pertencem ao usuário autenticado.",
        )
    return valid


async def _repository_ids(db: DbSession, policy_id: uuid.UUID) -> list[uuid.UUID]:
    result = await db.execute(
        select(InactivityPolicyRepository.repository_id)
        .where(InactivityPolicyRepository.policy_id == policy_id)
        .order_by(InactivityPolicyRepository.added_at.asc())
    )
    return list(result.scalars().all())


async def _serialize(db: DbSession, policy: InactivityPolicy) -> InactivityPolicyRead:
    ids = await _repository_ids(db, policy.id)
    data = InactivityPolicyRead.model_validate(policy)
    data.repository_ids = ids
    data.repository_count = len(ids)
    return data


@router.get("", response_model=list[InactivityPolicyRead])
async def list_policies(current_user: CurrentUser, db: DbSession) -> list[InactivityPolicyRead]:
    result = await db.execute(
        select(InactivityPolicy)
        .where(InactivityPolicy.user_id == current_user.id)
        .order_by(InactivityPolicy.enabled.desc(), InactivityPolicy.name.asc())
    )
    policies = result.scalars().all()
    return [await _serialize(db, policy) for policy in policies]


@router.post("", response_model=InactivityPolicyRead, status_code=status.HTTP_201_CREATED)
async def create_policy(
    payload: InactivityPolicyCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> InactivityPolicyRead:
    repository_ids = await _validate_repositories(db, payload.repository_ids, current_user.id)
    duplicate = await db.execute(
        select(InactivityPolicy.id).where(
            InactivityPolicy.user_id == current_user.id,
            InactivityPolicy.name == payload.name.strip(),
        )
    )
    if duplicate.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Já existe uma política com este nome.")

    policy = InactivityPolicy(
        user_id=current_user.id,
        name=payload.name.strip(),
        description=payload.description,
        timeout_value=payload.timeout_value,
        timeout_unit=payload.timeout_unit,
        action=payload.action,
        enabled=payload.enabled,
        activity_sources=payload.activity_sources,
    )
    db.add(policy)
    await db.flush()
    now = datetime.now(UTC)
    for repository_id in repository_ids:
        db.add(
            InactivityPolicyRepository(
                policy_id=policy.id,
                repository_id=repository_id,
                added_at=now,
            )
        )
    await db.commit()
    await db.refresh(policy)
    return await _serialize(db, policy)


@router.put("/{policy_id}", response_model=InactivityPolicyRead)
async def update_policy(
    policy_id: uuid.UUID,
    payload: InactivityPolicyUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> InactivityPolicyRead:
    policy = await _owned_policy(db, policy_id, current_user.id)
    repository_ids = await _validate_repositories(db, payload.repository_ids, current_user.id)
    duplicate = await db.execute(
        select(InactivityPolicy.id).where(
            InactivityPolicy.user_id == current_user.id,
            InactivityPolicy.name == payload.name.strip(),
            InactivityPolicy.id != policy.id,
        )
    )
    if duplicate.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Já existe outra política com este nome.")

    policy.name = payload.name.strip()
    policy.description = payload.description
    policy.timeout_value = payload.timeout_value
    policy.timeout_unit = payload.timeout_unit
    policy.action = payload.action
    policy.enabled = payload.enabled
    policy.activity_sources = payload.activity_sources
    await db.execute(
        delete(InactivityPolicyRepository).where(
            InactivityPolicyRepository.policy_id == policy.id
        )
    )
    now = datetime.now(UTC)
    for repository_id in repository_ids:
        db.add(
            InactivityPolicyRepository(
                policy_id=policy.id,
                repository_id=repository_id,
                added_at=now,
            )
        )
    await db.commit()
    await db.refresh(policy)
    return await _serialize(db, policy)


@router.delete("/{policy_id}", response_model=MessageResponse)
async def delete_policy(
    policy_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> MessageResponse:
    policy = await _owned_policy(db, policy_id, current_user.id)
    name = policy.name
    await db.delete(policy)
    await db.commit()
    return MessageResponse(message=f"Política “{name}” removida.")


@router.post("/{policy_id}/evaluate", response_model=InactivityEvaluationResult)
async def evaluate_policy(
    policy_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> InactivityEvaluationResult:
    await _owned_policy(db, policy_id, current_user.id)
    result = await evaluate_inactivity_policies(
        user_id=current_user.id,
        policy_id=policy_id,
    )
    return InactivityEvaluationResult.model_validate(result)


@router.post("/evaluate-all", response_model=InactivityEvaluationResult)
async def evaluate_all_policies(current_user: CurrentUser) -> InactivityEvaluationResult:
    result = await evaluate_inactivity_policies(user_id=current_user.id)
    return InactivityEvaluationResult.model_validate(result)


@router.get("/logs", response_model=list[InactivityActionLogRead])
async def action_logs(
    current_user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[InactivityActionLogRead]:
    result = await db.execute(
        select(InactivityActionLog)
        .join(
            InactivityPolicy,
            InactivityActionLog.policy_id == InactivityPolicy.id,
            isouter=True,
        )
        .where(InactivityPolicy.user_id == current_user.id)
        .order_by(InactivityActionLog.created_at.desc())
        .limit(limit)
    )
    return [InactivityActionLogRead.model_validate(item) for item in result.scalars().all()]
