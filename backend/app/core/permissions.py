from __future__ import annotations

OPERATION_PERMISSIONS: tuple[tuple[str, str, str], ...] = (
    ("repository.create", "Criar repositórios", "GitHub Tools"),
    ("repository.visibility", "Alterar visibilidade", "GitHub Tools"),
    ("repository.protection", "Gerenciar proteção de branches", "GitHub Tools"),
    ("repository.delete_branch", "Excluir branches", "GitHub Tools"),
    ("repository.replicate", "Replicar repositórios", "GitHub Tools"),
    ("ghcr.delete", "Excluir versões GHCR", "GHCR"),
    ("ghcr.delete_package", "Excluir packages GHCR", "GHCR"),
    ("backup.providers.manage", "Gerenciar storage providers", "Backup & Recovery"),
    ("backup.policy.manage", "Gerenciar políticas de backup", "Backup & Recovery"),
    ("backup.execute", "Executar backups", "Backup & Recovery"),
    ("backup.restore", "Executar restores", "Backup & Recovery"),
    ("release.channels.manage", "Gerenciar publishing channels", "Releases"),
    ("release.publish", "Publicar releases", "Releases"),
    ("deploy.targets.manage", "Gerenciar deployment targets", "Deployments"),
    ("deploy.execute", "Executar deployments", "Deployments"),
    ("deploy.rollback", "Executar rollback", "Deployments"),
    ("cleanup.profile.manage", "Gerenciar cleanup profiles", "Repository Clinic"),
    ("cleanup.execute", "Executar Deep Clean", "Repository Clinic"),
    ("operations.*", "Acesso a todas as operações", "Administração"),
)

OPERATION_PERMISSION_IDS = frozenset(item[0] for item in OPERATION_PERMISSIONS)


def normalize_permissions(values: list[str] | tuple[str, ...] | None) -> list[str]:
    if not values:
        return []
    normalized = sorted({str(value).strip() for value in values if str(value).strip()})
    unknown = [value for value in normalized if value not in OPERATION_PERMISSION_IDS]
    if unknown:
        raise ValueError("Permissões desconhecidas: " + ", ".join(unknown))
    if "operations.*" in normalized:
        return ["operations.*"]
    return normalized


def permission_catalog() -> list[dict[str, str]]:
    return [
        {"id": permission, "label": label, "group": group}
        for permission, label, group in OPERATION_PERMISSIONS
    ]
