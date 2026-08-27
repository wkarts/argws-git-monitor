#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Iterable

SEMVER_RE = re.compile(r"^(?:v)?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
CONVENTIONAL_BREAKING_RE = re.compile(
    r"(?im)^[a-z][a-z0-9-]*(?:\([^\n)]+\))?!:\s*"
)
FEATURE_RE = re.compile(r"(?im)^feat(?:\([^\n)]+\))?:\s*")
PATCH_RE = re.compile(
    r"(?im)^(?:fix|perf|refactor|security|build|ci|chore|docs|style|test)"
    r"(?:\([^\n)]+\))?:\s*"
)
BUMP_PRIORITY = {"patch": 1, "minor": 2, "major": 3}


class AutoVersionError(RuntimeError):
    pass


def parse_semver(value: str) -> tuple[int, int, int]:
    match = SEMVER_RE.fullmatch(value.strip())
    if not match:
        raise AutoVersionError(f"Versão SemVer estável inválida: {value!r}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def format_version(version: tuple[int, int, int]) -> str:
    return ".".join(str(part) for part in version)


def bump_version(base: tuple[int, int, int], bump: str) -> tuple[int, int, int]:
    major, minor, patch = base
    if bump == "major":
        return major + 1, 0, 0
    if bump == "minor":
        return major, minor + 1, 0
    if bump == "patch":
        return major, minor, patch + 1
    raise AutoVersionError(f"Tipo de incremento desconhecido: {bump}")


def classify_message(message: str) -> str | None:
    text = message.strip()
    if not text:
        return None

    lowered = text.lower()
    if "[skip release]" in lowered or "[release:none]" in lowered:
        return None
    if "[release:major]" in lowered:
        return "major"
    if "[release:minor]" in lowered:
        return "minor"
    if "[release:patch]" in lowered:
        return "patch"
    if "breaking change:" in lowered or "breaking-change:" in lowered:
        return "major"
    if CONVENTIONAL_BREAKING_RE.search(text):
        return "major"
    if FEATURE_RE.search(text):
        return "minor"
    if PATCH_RE.search(text):
        return "patch"

    # Qualquer PR/commit relevante sem Conventional Commit ainda gera patch.
    # Assim o fluxo nunca volta a depender de alguém informar uma versão manualmente.
    return "patch"


def highest_bump(messages: Iterable[str]) -> str | None:
    winner: str | None = None
    for message in messages:
        bump = classify_message(message)
        if bump and (winner is None or BUMP_PRIORITY[bump] > BUMP_PRIORITY[winner]):
            winner = bump
    return winner


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        raise AutoVersionError(f"git {' '.join(args)} falhou: {stderr or completed.returncode}")
    return completed.stdout.strip()


def _semver_tags(raw_tags: str) -> list[tuple[tuple[int, int, int], str]]:
    result: list[tuple[tuple[int, int, int], str]] = []
    for raw in raw_tags.splitlines():
        tag = raw.strip()
        if not tag:
            continue
        try:
            result.append((parse_semver(tag), tag))
        except AutoVersionError:
            continue
    return result


def latest_reachable_tag() -> tuple[tuple[int, int, int], str] | None:
    tags = _semver_tags(_git("tag", "--merged", "HEAD", "--list", "v[0-9]*"))
    return max(tags, key=lambda item: item[0]) if tags else None


def current_head_tag() -> tuple[tuple[int, int, int], str] | None:
    tags = _semver_tags(_git("tag", "--points-at", "HEAD"))
    return max(tags, key=lambda item: item[0]) if tags else None


def commit_messages_since(tag: str | None) -> list[str]:
    revision = f"{tag}..HEAD" if tag else "HEAD"
    raw = _git("log", "--first-parent", "--format=%B%x00", revision)
    return [part.strip() for part in raw.split("\x00") if part.strip()]


def declared_version(root: Path) -> str:
    value = (root / "VERSION").read_text(encoding="utf-8").strip()
    parse_semver(value)
    return value


def resolve_release(root: Path) -> dict[str, str]:
    head_sha = _git("rev-parse", "HEAD")
    tagged_head = current_head_tag()
    if tagged_head:
        version_tuple, tag = tagged_head
        version = format_version(version_tuple)
        major, minor, _patch = version_tuple
        return {
            "version": version,
            "tag": tag,
            "major_minor": f"{major}.{minor}",
            "release_required": "false",
            "bump": "none",
            "previous_tag": tag,
            "source_sha": head_sha,
            "reason": "head-already-tagged",
        }

    latest = latest_reachable_tag()
    if latest:
        base_version, previous_tag = latest
    else:
        base_version, previous_tag = (0, 0, 0), ""

    messages = commit_messages_since(previous_tag or None)
    bump = highest_bump(messages)
    if not bump:
        version = declared_version(root)
        parsed = parse_semver(version)
        return {
            "version": version,
            "tag": f"v{version}",
            "major_minor": f"{parsed[0]}.{parsed[1]}",
            "release_required": "false",
            "bump": "none",
            "previous_tag": previous_tag,
            "source_sha": head_sha,
            "reason": "no-release-worthy-commits",
        }

    next_tuple = bump_version(base_version, bump)
    version = format_version(next_tuple)
    return {
        "version": version,
        "tag": f"v{version}",
        "major_minor": f"{next_tuple[0]}.{next_tuple[1]}",
        "release_required": "true",
        "bump": bump,
        "previous_tag": previous_tag,
        "source_sha": head_sha,
        "reason": "automatic-semver",
    }


def apply_version(root: Path, version: str) -> None:
    parse_semver(version)

    version_file = root / "VERSION"
    version_file.write_text(f"{version}\n", encoding="utf-8")

    pyproject_path = root / "backend" / "pyproject.toml"
    pyproject = pyproject_path.read_text(encoding="utf-8")
    replaced, count = re.subn(
        r'(?m)^version\s*=\s*"[^"]+"\s*$',
        f'version = "{version}"',
        pyproject,
        count=1,
    )
    if count != 1:
        raise AutoVersionError("Não foi possível atualizar [project].version em backend/pyproject.toml")
    pyproject_path.write_text(replaced, encoding="utf-8")

    package_path = root / "frontend" / "package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    package["version"] = version
    package_path.write_text(
        json.dumps(package, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def verify_version(root: Path, expected: str) -> None:
    parse_semver(expected)
    values: dict[str, str] = {
        "VERSION": (root / "VERSION").read_text(encoding="utf-8").strip(),
    }

    pyproject_text = (root / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"\s*$', pyproject_text)
    if not match:
        raise AutoVersionError("backend/pyproject.toml não contém project.version")
    values["backend"] = match.group(1)

    package = json.loads((root / "frontend" / "package.json").read_text(encoding="utf-8"))
    values["frontend"] = str(package.get("version", ""))

    if any(value != expected for value in values.values()):
        rendered = ", ".join(f"{name}={value}" for name, value in values.items())
        raise AutoVersionError(f"Versões divergentes; esperado {expected}: {rendered}")


def write_github_output(path: Path, payload: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for key, value in payload.items():
            handle.write(f"{key}={value}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Autoversionamento SemVer do ARGWS Git Monitor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    resolve = subparsers.add_parser("resolve", help="Calcula a próxima versão a partir das tags e commits")
    resolve.add_argument("--github-output", type=Path)
    resolve.add_argument("--json", action="store_true")

    apply = subparsers.add_parser("apply", help="Sincroniza VERSION, backend e frontend")
    apply.add_argument("version")

    verify = subparsers.add_parser("verify", help="Valida que todas as fontes possuem a mesma versão")
    verify.add_argument("version")

    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = Path(__file__).resolve().parents[1]

    if args.command == "resolve":
        payload = resolve_release(root)
        if args.github_output:
            write_github_output(args.github_output, payload)
        if args.json or not args.github_output:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.command == "apply":
        apply_version(root, args.version)
        verify_version(root, args.version)
        return 0

    if args.command == "verify":
        verify_version(root, args.version)
        return 0

    raise AutoVersionError(f"Comando não implementado: {args.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AutoVersionError as exc:
        raise SystemExit(f"auto-version: {exc}") from exc
