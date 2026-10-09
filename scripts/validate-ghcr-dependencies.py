#!/usr/bin/env python3
"""Validate Git Monitor GHCR dependencies and broker probes without starting containers."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "infra" / "images.json"

COMPOSE_FILES = [
    "compose.yaml",
    "compose.dockge.yaml",
    "deploy/docker/compose.ghcr.yaml",
    "deploy/docker/compose.local.yaml",
    "deploy/dockge/compose.yaml",
    "deploy/cloudpanel/dockge/compose.yaml",
    "deploy/portainer/compose.yaml",
]

SERVICE_IMAGES = {
    "logs-init": "alpine",
    "postgres": "postgres",
    "redis": "redis",
    "rabbitmq": "rabbitmq",
    "minio": "minio",
}

PROBE = ["CMD", "bash", "-ec", "exec 3<>/dev/tcp/127.0.0.1/5672"]
PROBE_TIMING = {"interval": "60s", "timeout": "3s", "retries": 5, "start_period": "90s"}

def load_catalog() -> list[dict[str, str]]:
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    assert data.get("schema") == 1
    entries = data.get("images")
    assert isinstance(entries, list) and len(entries) == 8
    by_name = {item["name"]: item for item in entries}
    assert set(by_name) == set(SERVICE_IMAGES.values()) | {"python", "node", "nginx"}
    assert len(by_name) == len(entries)
    for item in entries:
        name, source, tag, target = (item[key] for key in ("name", "source", "tag", "target"))
        assert re.fullmatch(r"[a-z]+", name)
        assert re.fullmatch(r"[A-Za-z0-9._-]+", tag) and tag != "latest"
        assert source.startswith("docker.io/") and source.endswith(":" + tag)
        if name == "minio":
            assert source == "docker.io/dappros/minio:RELEASE.2025-09-07T16-13-09Z"
            assert "third-party" in item.get("provenance", "")
        else:
            assert source.startswith("docker.io/library/"), (name, source)
        assert target == f"ghcr.io/wkarts/argws-git-monitor-{name}:{tag}"
    return entries

def validate() -> None:
    import yaml

    images = {item["name"]: item["target"] for item in load_catalog()}
    for path in COMPOSE_FILES:
        data = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
        services = data["services"]
        for name, image in SERVICE_IMAGES.items():
            assert services[name]["image"] == images[image], (path, name, services[name].get("image"))
        broker = services["rabbitmq"]
        hc = broker["healthcheck"]
        assert hc.get("test") == PROBE, (path, "RabbitMQ TCP probe", hc)
        for name, expected in PROBE_TIMING.items():
            assert hc.get(name) == expected, (path, name, hc.get(name))
        assert "rabbitmq-diagnostics" not in str(hc), path
        # Preserve exact internal broker address, connection settings and data mounts.
        assert "amqp://" in str(services["worker"]["environment"].get("CELERY_BROKER_URL", "")), path
        assert any(str(mount).startswith("./data-rabbitmq:/var/lib/rabbitmq") for mount in broker["volumes"]), path
        assert any(str(mount).startswith("./data-postgres:/var/lib/postgresql/data") for mount in services["postgres"]["volumes"]), path
        assert any(str(mount).startswith("./data-redis:/data") for mount in services["redis"]["volumes"]), path

    backend = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    frontend = (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    assert "ARG PYTHON_BASE=python:3.13-slim" in backend
    assert "FROM ${PYTHON_BASE} AS runtime" in backend
    assert "ARG NODE_BASE=node:24-alpine" in frontend
    assert "ARG NGINX_BASE=nginx:1.27-alpine" in frontend
    assert "FROM ${NODE_BASE} AS build" in frontend
    assert "FROM ${NGINX_BASE} AS runtime" in frontend

    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "dependencies:" in release and "mirror-dependencies.yml" in release
    assert "PYTHON_BASE=ghcr.io/" in release
    assert "NODE_BASE=ghcr.io/" in release
    assert "NGINX_BASE=ghcr.io/" in release
    print(f"PASS: {len(COMPOSE_FILES)} Compose manifests, 8 GHCR images, lightweight RabbitMQ probes and build bases")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", action="store_true", help="Emit GitHub Actions matrix as JSON")
    args = parser.parse_args()
    if args.matrix:
        print(json.dumps({"include": load_catalog()}, separators=(",", ":")))
    else:
        validate()

if __name__ == "__main__":
    main()
