from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import logging
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import dispose_engine, session_scope
from app.core.security import hash_password
from app.models.activity import Notification
from app.models.github import (
    ConnectionStatus,
    GitHubConnection,
    HealthStatus,
    PullRequest,
    Release,
    Repository,
    WorkflowRun,
)
from app.models.user import User

logger = logging.getLogger(__name__)


async def create_initial_admin() -> User:
    settings = get_settings()
    async with session_scope() as session:
        result = await session.execute(
            select(User).where(User.email == str(settings.initial_admin_email).lower())
        )
        user = result.scalar_one_or_none()
        if user:
            return user
        user = User(
            name=settings.initial_admin_name,
            email=str(settings.initial_admin_email).lower(),
            password_hash=hash_password(settings.initial_admin_password),
            is_active=True,
            is_superuser=True,
            must_change_password=settings.initial_admin_must_change_password,
        )
        session.add(user)
        await session.flush()
        logger.info("Administrador inicial criado: %s", user.email)
        return user


async def create_demo_data(user_id) -> None:
    settings = get_settings()
    if not settings.demo_data_enabled:
        return

    async with session_scope() as session:
        result = await session.execute(
            select(GitHubConnection.id)
            .where(GitHubConnection.user_id == user_id)
            .limit(1)
        )
        # Nunca recria a demonstração ao lado de uma conexão real.
        if result.scalar_one_or_none() is not None:
            return

        now = datetime.now(UTC)
        connection = GitHubConnection(
            user_id=user_id,
            name="Demonstração",
            github_login="wkarts-demo",
            github_user_id=0,
            token_encrypted=None,
            token_last_four=None,
            status=ConnectionStatus.DEMO,
            auto_import=False,
            api_url="https://api.github.com",
            last_sync_at=now,
        )
        session.add(connection)
        await session.flush()

        samples = [
            {
                "github_id": 900000001,
                "name": "scheduler-pro-platform",
                "description": "Plataforma SaaS multitenant de agendamentos.",
                "private": True,
                "language": "Python",
                "health_score": 38,
                "health_status": HealthStatus.FAILING,
                "workflow_status": "completed",
                "workflow_conclusion": "failure",
                "workflow_name": "Release Desktop / Mobile",
                "commit": "Corrige pipeline de artefatos Android",
                "prs": 2,
                "issues": 5,
                "release": "v0.1.0-alpha.6",
                "pushed_at": now - timedelta(minutes=12),
            },
            {
                "github_id": 900000002,
                "name": "geradorsped",
                "description": "Gerador e auditor de EFD ICMS/IPI.",
                "private": True,
                "language": "Python",
                "health_score": 82,
                "health_status": HealthStatus.RUNNING,
                "workflow_status": "in_progress",
                "workflow_conclusion": None,
                "workflow_name": "CI / Testes",
                "commit": "Aprimora motor de leitura de XML",
                "prs": 1,
                "issues": 3,
                "release": "v0.1.0-alpha.8",
                "pushed_at": now - timedelta(minutes=35),
            },
            {
                "github_id": 900000003,
                "name": "pige360",
                "description": "Plataforma Integrada de Gestão Educacional.",
                "private": True,
                "language": "TypeScript",
                "health_score": 96,
                "health_status": HealthStatus.HEALTHY,
                "workflow_status": "completed",
                "workflow_conclusion": "success",
                "workflow_name": "Build and Test",
                "commit": "Prepara release alpha de homologação",
                "prs": 0,
                "issues": 2,
                "release": "v0.1.0-alpha.1",
                "pushed_at": now - timedelta(hours=2),
            },
            {
                "github_id": 900000004,
                "name": "argws-pro-communication",
                "description": "Hub de comunicação e WhatsApp reutilizável.",
                "private": True,
                "language": "Python",
                "health_score": 72,
                "health_status": HealthStatus.ATTENTION,
                "workflow_status": None,
                "workflow_conclusion": None,
                "workflow_name": None,
                "commit": "Estrutura inicial da stack",
                "prs": 0,
                "issues": 0,
                "release": None,
                "pushed_at": now - timedelta(days=2),
            },
        ]

        for index, sample in enumerate(samples, start=1):
            full_name = f"wkarts/{sample['name']}"
            repository = Repository(
                connection_id=connection.id,
                github_id=sample["github_id"],
                owner="wkarts",
                name=sample["name"],
                full_name=full_name,
                html_url=f"https://github.com/{full_name}",
                description=sample["description"],
                private=sample["private"],
                fork=False,
                archived=False,
                disabled=False,
                visibility="private",
                default_branch="main",
                language=sample["language"],
                stargazers_count=0,
                forks_count=0,
                open_issue_count=sample["issues"],
                open_pr_count=sample["prs"],
                branch_count=3,
                github_created_at=now - timedelta(days=500),
                github_updated_at=sample["pushed_at"],
                pushed_at=sample["pushed_at"],
                latest_commit_sha=f"{index:040x}",
                latest_commit_message=sample["commit"],
                latest_commit_author="wkarts",
                latest_commit_at=sample["pushed_at"],
                latest_release_tag=sample["release"],
                latest_release_name=sample["release"],
                latest_release_at=now - timedelta(days=index * 4) if sample["release"] else None,
                latest_workflow_id=990000000 + index if sample["workflow_status"] else None,
                latest_workflow_name=sample["workflow_name"],
                latest_workflow_status=sample["workflow_status"],
                latest_workflow_conclusion=sample["workflow_conclusion"],
                latest_workflow_url=f"https://github.com/{full_name}/actions",
                latest_workflow_at=now - timedelta(minutes=index * 7),
                health_score=sample["health_score"],
                health_status=sample["health_status"],
                monitoring_enabled=True,
                last_synced_at=now,
                extra_data={"demo": True},
            )
            session.add(repository)
            await session.flush()

            if sample["workflow_status"]:
                session.add(
                    WorkflowRun(
                        repository_id=repository.id,
                        github_id=990000000 + index,
                        name=sample["workflow_name"],
                        display_title=sample["commit"],
                        event="push",
                        status=sample["workflow_status"],
                        conclusion=sample["workflow_conclusion"],
                        head_branch="main",
                        head_sha=f"{index:040x}",
                        run_number=120 + index,
                        run_attempt=1,
                        html_url=f"https://github.com/{full_name}/actions",
                        actor_login="wkarts",
                        github_created_at=now - timedelta(minutes=index * 8),
                        github_updated_at=now - timedelta(minutes=index * 7),
                        run_started_at=now - timedelta(minutes=index * 8),
                        duration_seconds=60 * index,
                    )
                )

            for pr_number in range(1, sample["prs"] + 1):
                session.add(
                    PullRequest(
                        repository_id=repository.id,
                        github_id=980000000 + index * 100 + pr_number,
                        number=20 + pr_number,
                        title=f"Evolução funcional #{20 + pr_number}",
                        state="open",
                        draft=False,
                        html_url=f"https://github.com/{full_name}/pull/{20 + pr_number}",
                        user_login="wkarts",
                        head_ref=f"feature/evolucao-{pr_number}",
                        base_ref="main",
                        github_created_at=now - timedelta(days=pr_number),
                        github_updated_at=now - timedelta(hours=pr_number),
                    )
                )

            if sample["release"]:
                session.add(
                    Release(
                        repository_id=repository.id,
                        github_id=970000000 + index,
                        tag_name=sample["release"],
                        name=sample["release"],
                        draft=False,
                        prerelease="alpha" in sample["release"],
                        html_url=f"https://github.com/{full_name}/releases/tag/{sample['release']}",
                        target_commitish="main",
                        github_created_at=now - timedelta(days=index * 4),
                        published_at=now - timedelta(days=index * 4),
                    )
                )

        session.add(
            Notification(
                user_id=user_id,
                repository_id=None,
                event_type="system.welcome",
                severity="info",
                title="ARGWS Git Monitor está operacional",
                message="Conecte seu token do GitHub para substituir os dados demonstrativos pelos repositórios reais.",
                url=None,
                payload={"demo": True},
                created_at=now,
            )
        )
        logger.info("Dados demonstrativos criados")


async def bootstrap() -> None:
    user = await create_initial_admin()
    await create_demo_data(user.id)


async def main() -> None:
    try:
        await bootstrap()
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
