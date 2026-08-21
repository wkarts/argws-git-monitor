#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEV_COMPOSE = ROOT / "compose.dev.yaml"
EXPECTED_SERVICES = {
    "postgres",
    "redis",
    "rabbitmq",
    "migrate",
    "api",
    "worker",
    "beat",
    "web",
}

COMPOSE_FILES = {
    "root-local": ROOT / "compose.yaml",
    "root-dockge": ROOT / "compose.dockge.yaml",
    "docker-ghcr": ROOT / "deploy/docker/compose.ghcr.yaml",
    "docker-local": ROOT / "deploy/docker/compose.local.yaml",
    "dockge": ROOT / "deploy/dockge/compose.yaml",
    "portainer": ROOT / "deploy/portainer/compose.yaml",
    "cloudpanel-dockge": ROOT / "deploy/cloudpanel/dockge/compose.yaml",
}

REQUIRED_FILES = [
    ROOT / "deploy/README.md",
    ROOT / "deploy/migrate-named-volumes.sh",
    ROOT / "deploy/docker/README.md",
    ROOT / "deploy/docker/.env.example",
    ROOT / "deploy/docker/generate-env.sh",
    ROOT / "deploy/docker/deploy-ghcr.sh",
    ROOT / "deploy/docker/deploy-local.sh",
    ROOT / "deploy/dockge/README.md",
    ROOT / "deploy/dockge/.env.example",
    ROOT / "deploy/dockge/generate-env.sh",
    ROOT / "deploy/dockge/deploy.sh",
    ROOT / "deploy/portainer/README.md",
    ROOT / "deploy/portainer/stack.env.example",
    ROOT / "deploy/portainer/generate-stack-env.sh",
    ROOT / "deploy/cloudpanel/README.md",
    ROOT / "deploy/cloudpanel/nginx/argws-git-monitor.conf",
    ROOT / "deploy/cloudpanel/dockge/.env.example",
    ROOT / "deploy/cloudpanel/dockge/generate-env.sh",
    ROOT / "deploy/cloudpanel/dockge/deploy.sh",
    DEV_COMPOSE,
    *COMPOSE_FILES.values(),
]

EXPECTED_STORAGE = {
    "postgres": ("./data-postgres", "/var/lib/postgresql/data"),
    "redis": ("./data-redis", "/data"),
    "rabbitmq": ("./data-rabbitmq", "/var/lib/rabbitmq"),
}


def fail(message: str) -> None:
    print(f"[ERRO] {message}")
    raise SystemExit(1)


def ok(message: str) -> None:
    print(f"[OK] {message}")


def read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - erro operacional
        fail(f"YAML inválido em {path.relative_to(ROOT)}: {exc}")
    if not isinstance(data, dict):
        fail(f"A raiz de {path.relative_to(ROOT)} não é um objeto YAML")
    return data


def validate_required_files() -> None:
    missing = [str(path.relative_to(ROOT)) for path in REQUIRED_FILES if not path.is_file()]
    if missing:
        fail("Arquivos de deploy ausentes: " + ", ".join(missing))
    ok(f"{len(REQUIRED_FILES)} arquivos obrigatórios de deploy encontrados")


def validate_services(name: str, data: dict[str, Any]) -> None:
    services = data.get("services")
    if not isinstance(services, dict):
        fail(f"{name}: bloco services ausente")
    missing = EXPECTED_SERVICES - set(services)
    if missing:
        fail(f"{name}: serviços ausentes: {', '.join(sorted(missing))}")
    ok(f"{name}: oito serviços obrigatórios encontrados")


def parse_short_mount(name: str, service_name: str, mount: str) -> tuple[str, str]:
    parts = mount.split(":")
    if len(parts) < 2:
        fail(f"{name}: volume inválido em {service_name}: {mount}")
    return parts[0], parts[1]


def find_mount(name: str, service_name: str, service: dict[str, Any]) -> tuple[str, str]:
    volumes = service.get("volumes", [])
    if not isinstance(volumes, list):
        fail(f"{name}: volumes de {service_name} não formam uma lista")

    _expected_source, expected_target = EXPECTED_STORAGE[service_name]
    for mount in volumes:
        if isinstance(mount, str):
            source, target = parse_short_mount(name, service_name, mount)
        elif isinstance(mount, dict):
            source = str(mount.get("source", ""))
            target = str(mount.get("target", ""))
        else:
            continue
        if target == expected_target:
            return source, target

    fail(f"{name}: destino persistente {expected_target} ausente em {service_name}")


def validate_relative_storage(name: str, data: dict[str, Any]) -> None:
    services = data["services"]
    for service_name, (expected_source, expected_target) in EXPECTED_STORAGE.items():
        service = services.get(service_name)
        if not isinstance(service, dict):
            fail(f"{name}: serviço persistente {service_name} inválido")
        source, target = find_mount(name, service_name, service)
        if source != expected_source:
            fail(
                f"{name}: {service_name} deve usar {expected_source}:{expected_target}, "
                f"encontrado {source}:{target}"
            )
        if not source.startswith("./"):
            fail(f"{name}: fonte de {service_name} não começa com ./")
        if Path(source).is_absolute():
            fail(f"{name}: fonte absoluta não permitida em {service_name}: {source}")

    named_volumes = data.get("volumes")
    if named_volumes:
        fail(f"{name}: bloco de volumes nomeados não é permitido para dados persistentes")

    ok(
        f"{name}: persistência relativa validada em "
        "./data-postgres, ./data-redis e ./data-rabbitmq"
    )


def validate_dev_storage() -> None:
    data = read_yaml(DEV_COMPOSE)
    if data.get("volumes"):
        fail("compose.dev.yaml: bloco de volumes nomeados não é permitido")

    services = data.get("services")
    if not isinstance(services, dict):
        fail("compose.dev.yaml: bloco services ausente")
    web = services.get("web")
    if not isinstance(web, dict):
        fail("compose.dev.yaml: serviço web ausente")
    volumes = web.get("volumes", [])
    if "./data-frontend-node-modules:/app/node_modules" not in volumes:
        fail(
            "compose.dev.yaml: node_modules deve usar "
            "./data-frontend-node-modules:/app/node_modules"
        )
    ok("compose.dev.yaml: volume de desenvolvimento também usa caminho relativo")


def validate_image_mode(name: str, data: dict[str, Any]) -> None:
    services = data["services"]
    for service_name in ("migrate", "api", "worker", "beat", "web"):
        service = services[service_name]
        if not isinstance(service, dict):
            fail(f"{name}: serviço {service_name} inválido")
        if "build" in service:
            fail(f"{name}: serviço {service_name} não pode conter build")

    api_image = str(services["api"].get("image", ""))
    web_image = str(services["web"].get("image", ""))
    if "argws-git-monitor-api" not in api_image:
        fail(f"{name}: imagem da API ausente")
    if "argws-git-monitor-web" not in web_image:
        fail(f"{name}: imagem Web ausente")
    ok(f"{name}: implantação por imagens validada")


def validate_local_build(data: dict[str, Any]) -> None:
    services = data["services"]
    api = services["api"]
    web = services["web"]
    api_build = api.get("build", {})
    web_build = web.get("build", {})
    if api_build.get("context") != "../../backend":
        fail("docker-local: contexto de build da API deve ser ../../backend")
    if web_build.get("context") != "../../frontend":
        fail("docker-local: contexto de build da Web deve ser ../../frontend")
    ok("docker-local: contextos de build local validados")


def validate_cloudpanel(data: dict[str, Any]) -> None:
    ports = data["services"]["web"].get("ports", [])
    rendered = "\n".join(str(item) for item in ports)
    if "127.0.0.1" not in rendered:
        fail("cloudpanel-dockge: a porta Web deve ficar vinculada a 127.0.0.1")

    nginx_path = ROOT / "deploy/cloudpanel/nginx/argws-git-monitor.conf"
    nginx = nginx_path.read_text(encoding="utf-8")
    if "proxy_pass http://127.0.0.1:8080" not in nginx:
        fail("cloudpanel: proxy_pass local não encontrado")
    if "X-Forwarded-Proto" not in nginx:
        fail("cloudpanel: cabeçalho X-Forwarded-Proto ausente")
    ok("cloudpanel: bind local e reverse proxy validados")


def validate_portainer(data: dict[str, Any]) -> None:
    for service_name, service in data["services"].items():
        if isinstance(service, dict) and "env_file" in service:
            fail(f"portainer: serviço {service_name} não deve depender de env_file")
    ok("portainer: variáveis independentes de env_file validadas")


def validate_migration_script() -> None:
    content = (ROOT / "deploy/migrate-named-volumes.sh").read_text(encoding="utf-8")
    markers = [
        "_postgres_data",
        "_redis_data",
        "_rabbitmq_data",
        "data-postgres",
        "data-redis",
        "data-rabbitmq",
        "/source:ro",
    ]
    missing = [marker for marker in markers if marker not in content]
    if missing:
        fail("migrador incompleto; marcadores ausentes: " + ", ".join(missing))
    if "docker volume rm" in content:
        fail("migrador não pode remover automaticamente os volumes antigos")
    ok("migrador copia os dados e preserva os volumes antigos")


def validate_versions() -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    for path in [
        ROOT / "deploy/docker/.env.example",
        ROOT / "deploy/dockge/.env.example",
        ROOT / "deploy/portainer/stack.env.example",
        ROOT / "deploy/cloudpanel/dockge/.env.example",
    ]:
        content = path.read_text(encoding="utf-8")
        if f"APP_VERSION={version}" not in content:
            fail(f"{path.relative_to(ROOT)} não declara APP_VERSION={version}")
        if f"IMAGE_TAG={version}" not in content:
            fail(f"{path.relative_to(ROOT)} não declara IMAGE_TAG={version}")
    ok(f"versão {version} sincronizada nos ambientes de deploy")


def main() -> int:
    validate_required_files()

    loaded = {name: read_yaml(path) for name, path in COMPOSE_FILES.items()}
    for name, data in loaded.items():
        validate_services(name, data)
        validate_relative_storage(name, data)

    validate_dev_storage()
    validate_image_mode("root-dockge", loaded["root-dockge"])
    validate_image_mode("docker-ghcr", loaded["docker-ghcr"])
    validate_image_mode("dockge", loaded["dockge"])
    validate_image_mode("portainer", loaded["portainer"])
    validate_image_mode("cloudpanel-dockge", loaded["cloudpanel-dockge"])
    validate_local_build(loaded["docker-local"])
    validate_cloudpanel(loaded["cloudpanel-dockge"])
    validate_portainer(loaded["portainer"])
    validate_migration_script()
    validate_versions()

    print("[OK] Estrutura de deploy e armazenamento relativo validados integralmente")
    return 0


if __name__ == "__main__":
    sys.exit(main())
