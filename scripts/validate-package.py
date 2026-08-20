#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - validado no CI após instalar PyYAML
    raise SystemExit("PyYAML é necessário: pip install pyyaml") from exc

ROOT = Path(__file__).resolve().parent.parent
ERRORS: list[str] = []
WARNINGS: list[str] = []
CHECKS: list[str] = []


def ok(message: str) -> None:
    CHECKS.append(message)
    print(f"[OK] {message}")


def error(message: str) -> None:
    ERRORS.append(message)
    print(f"[ERRO] {message}")


def warning(message: str) -> None:
    WARNINGS.append(message)
    print(f"[AVISO] {message}")


def require_files(paths: list[str]) -> None:
    missing = [item for item in paths if not (ROOT / item).is_file()]
    if missing:
        error(f"Arquivos obrigatórios ausentes: {', '.join(missing)}")
    else:
        ok(f"{len(paths)} arquivos estruturais obrigatórios encontrados")


def parse_yaml_files(paths: list[str]) -> None:
    for item in paths:
        try:
            payload = yaml.safe_load((ROOT / item).read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("raiz YAML não é um objeto")
        except Exception as exc:
            error(f"YAML inválido em {item}: {exc}")
            return
    ok(f"{len(paths)} arquivos YAML analisados")


def parse_json_files(paths: list[str]) -> None:
    for item in paths:
        try:
            json.loads((ROOT / item).read_text(encoding="utf-8"))
        except Exception as exc:
            error(f"JSON inválido em {item}: {exc}")
            return
    ok(f"{len(paths)} arquivos JSON analisados")


def validate_compose() -> None:
    data = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    services = set((data or {}).get("services", {}))
    expected = {"postgres", "redis", "rabbitmq", "migrate", "api", "worker", "beat", "web"}
    missing = expected - services
    if missing:
        error(f"Serviços Docker ausentes: {', '.join(sorted(missing))}")
    else:
        ok("Stack Docker contém os 8 serviços previstos")

    exposed = {
        name
        for name, config in (data or {}).get("services", {}).items()
        if isinstance(config, dict) and config.get("ports")
    }
    unexpected = exposed - {"web", "rabbitmq"}
    if unexpected:
        error(f"Serviços internos indevidamente publicados: {', '.join(sorted(unexpected))}")
    else:
        ok("PostgreSQL, Redis e AMQP permanecem isolados da rede do host")


def validate_gitignore() -> None:
    content = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    protected = {line.strip() for line in content if line.strip() and not line.startswith("#")}
    required = {".env", "CREDENCIAIS_INICIAIS.txt", "backups/*", "*.dump", ".venv/", "node_modules/"}
    missing = required - protected
    if missing:
        error(f"Itens sensíveis/gerados ausentes no .gitignore: {', '.join(sorted(missing))}")
    else:
        ok(".gitignore protege segredos, backups e dependências")


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"')
    return values


def validate_generated_env() -> None:
    path = ROOT / ".env"
    if not path.exists():
        warning(".env não está presente; situação esperada em checkout do GitHub")
        return
    env = parse_env(path)
    length_rules = {
        "APP_SECRET_KEY": 64,
        "INITIAL_ADMIN_PASSWORD": 12,
        "POSTGRES_PASSWORD": 24,
        "RABBITMQ_DEFAULT_PASS": 24,
        "GITHUB_WEBHOOK_SECRET": 32,
    }
    for key, minimum in length_rules.items():
        if len(env.get(key, "")) < minimum:
            error(f"{key} possui menos de {minimum} caracteres")
    encryption_key = env.get("ENCRYPTION_KEY", "")
    try:
        decoded = base64.urlsafe_b64decode(encryption_key.encode("ascii"))
        if len(decoded) != 32:
            raise ValueError("deve decodificar exatamente 32 bytes")
    except Exception as exc:
        error(f"ENCRYPTION_KEY não é uma chave Fernet válida: {exc}")
    if not ERRORS:
        ok("Segredos gerados atendem aos requisitos de comprimento e formato")


def validate_shell_scripts() -> None:
    scripts = sorted((ROOT / "scripts").glob("*.sh")) + sorted(ROOT.glob("*_LINUX.sh"))
    for script in scripts:
        result = subprocess.run(
            ["bash", "-n", str(script)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            error(f"Sintaxe Bash inválida em {script.relative_to(ROOT)}: {result.stderr.strip()}")
            return
        mode = script.stat().st_mode
        if not mode & stat.S_IXUSR:
            warning(f"Script sem bit executável: {script.relative_to(ROOT)}")
    ok(f"{len(scripts)} scripts Bash analisados")


def validate_python_syntax() -> None:
    targets = [ROOT / "backend/app", ROOT / "backend/tests", ROOT / "backend/migrations"]
    result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", *(str(item) for item in targets)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        error(f"Compilação sintática Python falhou: {result.stderr.strip()}")
    else:
        ok("Backend, testes e migrations compilam sintaticamente")


def validate_frontend_structure() -> None:
    vue_files = sorted((ROOT / "frontend/src").rglob("*.vue"))
    ts_files = sorted((ROOT / "frontend/src").rglob("*.ts"))
    start_errors = len(ERRORS)
    for vue_file in vue_files:
        content = vue_file.read_text(encoding="utf-8")
        if len(re.findall(r"<script\s+setup\s+lang=\"ts\">", content)) != 1:
            error(f"{vue_file.relative_to(ROOT)} não contém exatamente um script setup TypeScript")
        if "<template>" not in content or "</template>" not in content:
            error(f"Seção principal <template> ausente em {vue_file.relative_to(ROOT)}")
        if content.count("</script>") != 1:
            error(f"Seção <script> incompleta em {vue_file.relative_to(ROOT)}")
    if len(ERRORS) == start_errors:
        ok(f"Frontend contém {len(vue_files)} componentes Vue e {len(ts_files)} módulos TypeScript")


def validate_images() -> None:
    expected = {
        "frontend/public/pwa-192x192.png": (192, 192),
        "frontend/public/pwa-512x512.png": (512, 512),
        "frontend/public/pwa-maskable-512x512.png": (512, 512),
        "frontend/public/apple-touch-icon.png": (180, 180),
        "docs/previews/argws-git-monitor-dashboard-desktop-v0.2.0.png": (1440, 900),
        "docs/previews/argws-git-monitor-dashboard-mobile-v0.2.0.png": (390, 844),
    }
    try:
        from PIL import Image
    except ImportError:
        warning("Pillow não disponível; dimensões dos ícones não foram inspecionadas")
        return
    for item, size in expected.items():
        with Image.open(ROOT / item) as image:
            if image.size != size:
                error(f"Ícone {item} possui {image.size}, esperado {size}")
    if not ERRORS:
        ok("Ícones PWA possuem dimensões corretas")


def validate_no_embedded_github_token() -> None:
    patterns = [
        re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
        re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    ]
    ignored = {".env", "CREDENCIAIS_INICIAIS.txt", "validate-package.py"}
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.name in ignored or any(part in {".git", ".venv", "node_modules", "__pycache__"} for part in path.parts):
            continue
        if path.suffix.lower() in {".png", ".ico", ".jpg", ".jpeg", ".zip", ".gz", ".dump"}:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(pattern.search(content) for pattern in patterns):
            error(f"Possível token GitHub embutido em {path.relative_to(ROOT)}")
            return
    ok("Nenhum token GitHub real foi encontrado no código-fonte")


def validate_credentials_consistency() -> None:
    env_path = ROOT / ".env"
    credentials_path = ROOT / "CREDENCIAIS_INICIAIS.txt"
    if not env_path.exists() or not credentials_path.exists():
        return
    env = parse_env(env_path)
    content = credentials_path.read_text(encoding="utf-8")
    if env.get("INITIAL_ADMIN_EMAIL") not in content or env.get("INITIAL_ADMIN_PASSWORD") not in content:
        error("CREDENCIAIS_INICIAIS.txt não corresponde ao .env gerado")
    else:
        ok("Credenciais de primeiro acesso correspondem ao ambiente gerado")


def validate_visual_contract() -> None:
    start_errors = len(ERRORS)
    required_routes = {
        "pull-requests": "PullRequestsView",
        "actions": "ActionsView",
        "releases": "ReleasesView",
        "issues": "IssuesView",
    }
    router = (ROOT / "frontend/src/router/index.ts").read_text(encoding="utf-8")
    for path, component in required_routes.items():
        if f"path: '{path}'" not in router or component not in router:
            error(f"Rota visual/operacional ausente: /{path} -> {component}")

    shell = (ROOT / "frontend/src/layouts/AppShell.vue").read_text(encoding="utf-8")
    for label in [
        "Dashboard",
        "Repositórios",
        "Pull Requests",
        "Actions",
        "Releases",
        "Issues",
        "Alertas",
        "Configurações",
    ]:
        if f"label: '{label}'" not in shell:
            error(f"Item obrigatório do shell ausente: {label}")

    dashboard = (ROOT / "frontend/src/views/DashboardView.vue").read_text(encoding="utf-8")
    for marker in [
        "overview-metrics",
        "health-overview-content",
        "recent-activity-list",
        "desktop-repository-table",
        "mobile-repository-list",
        "mobile-critical-card",
    ]:
        if marker not in dashboard:
            error(f"Componente obrigatório do dashboard ausente: {marker}")

    operations = (ROOT / "backend/app/api/routes/operations.py").read_text(encoding="utf-8")
    for endpoint in [
        '@router.get("/actions"',
        '@router.get("/pull-requests"',
        '@router.get("/releases"',
        '@router.get("/issues"',
    ]:
        if endpoint not in operations:
            error(f"Endpoint agregado ausente: {endpoint}")

    preview = (ROOT / "docs/previews/dashboard-visual-contract.html").read_text(encoding="utf-8")
    for marker in ["ARGWS Git Monitor", "scheduler-pro-platform", "bottom-nav", "mobile-content"]:
        if marker not in preview:
            error(f"Fixture visual incompleto: {marker}")

    if len(ERRORS) == start_errors:
        ok("Contrato visual v0.2.0 preserva rotas, menu, dashboard e evidências")


def validate_docs() -> None:
    documents = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
    empty = [str(item.relative_to(ROOT)) for item in documents if item.stat().st_size < 300]
    if empty:
        error(f"Documentação vazia ou insuficiente: {', '.join(empty)}")
    else:
        ok(f"{len(documents)} documentos operacionais presentes")


def write_summary() -> None:
    summary = {
        "project": "ARGWS Git Monitor",
        "version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "checks": len(CHECKS),
        "warnings": WARNINGS,
        "errors": ERRORS,
        "status": "passed" if not ERRORS else "failed",
    }
    (ROOT / "validation-result.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    os.chdir(ROOT)
    require_files([
        "compose.yaml",
        "compose.dev.yaml",
        "compose.ghcr.yaml",
        ".env.example",
        ".gitignore",
        "README.md",
        "VERSION",
        "backend/Dockerfile",
        "backend/pyproject.toml",
        "backend/alembic.ini",
        "frontend/Dockerfile",
        "frontend/package.json",
        "frontend/vite.config.ts",
        "frontend/nginx.conf",
        "frontend/src/layouts/AppShell.vue",
        "frontend/src/views/DashboardView.vue",
        "frontend/src/views/ActionsView.vue",
        "frontend/src/views/PullRequestsView.vue",
        "frontend/src/views/ReleasesView.vue",
        "frontend/src/views/IssuesView.vue",
        "backend/app/api/routes/operations.py",
        "backend/app/schemas/operations.py",
        "docs/CONTRATO_VISUAL.md",
        "docs/previews/dashboard-visual-contract.html",
        "docs/previews/argws-git-monitor-dashboard-desktop-v0.2.0.png",
        "docs/previews/argws-git-monitor-dashboard-mobile-v0.2.0.png",
        ".github/workflows/ci.yml",
        ".github/workflows/release.yml",
    ])
    parse_yaml_files([
        "compose.yaml",
        "compose.dev.yaml",
        "compose.ghcr.yaml",
        ".github/workflows/ci.yml",
        ".github/workflows/release.yml",
        ".github/workflows/codeql.yml",
        ".github/dependabot.yml",
    ])
    parse_json_files(["frontend/package.json", "frontend/tsconfig.json", "frontend/tsconfig.app.json"])
    validate_compose()
    validate_gitignore()
    validate_generated_env()
    validate_credentials_consistency()
    validate_shell_scripts()
    validate_python_syntax()
    validate_frontend_structure()
    validate_images()
    validate_no_embedded_github_token()
    validate_visual_contract()
    validate_docs()
    write_summary()
    print(f"\nResultado: {len(CHECKS)} verificações aprovadas, {len(WARNINGS)} aviso(s), {len(ERRORS)} erro(s).")
    return 1 if ERRORS else 0


if __name__ == "__main__":
    raise SystemExit(main())
