#!/usr/bin/env python3
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import shutil
import stat
import tarfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT.parent
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
TOP_LEVEL = "argws-git-monitor"

COMMON_EXCLUDES = {
    ".git/*",
    ".venv/*",
    "**/__pycache__/*",
    "**/.pytest_cache/*",
    "**/.ruff_cache/*",
    "**/node_modules/*",
    "**/dist/*",
    "**/.coverage",
    "backups/*",
    "*.zip",
    "*.tar.gz",
}
SOURCE_EXCLUDES = COMMON_EXCLUDES | {".env", ".env.*", "CREDENCIAIS_INICIAIS.txt"}
SOURCE_INCLUDES = {".env.example"}


def matches(path: str, patterns: set[str]) -> bool:
    normalized = path.replace(os.sep, "/")
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in patterns)


def iter_files(*, source: bool) -> list[Path]:
    excludes = SOURCE_EXCLUDES if source else COMMON_EXCLUDES
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT).as_posix()
        if source and relative in SOURCE_INCLUDES:
            files.append(path)
            continue
        if matches(relative, excludes):
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(ROOT).as_posix())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate_manifest() -> None:
    entries = []
    for path in iter_files(source=False):
        relative = path.relative_to(ROOT).as_posix()
        if relative == "MANIFEST.json":
            continue
        entries.append(
            {
                "path": relative,
                "size": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    payload = {
        "project": "ARGWS Git Monitor",
        "version": VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "file_count": len(entries),
        "files": entries,
    }
    (ROOT / "MANIFEST.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_zip(target: Path, *, source: bool) -> None:
    target.unlink(missing_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in iter_files(source=source):
            relative = path.relative_to(ROOT).as_posix()
            arcname = f"{TOP_LEVEL}/{relative}"
            info = zipfile.ZipInfo.from_file(path, arcname=arcname)
            info.date_time = (2026, 8, 20, 12, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (path.stat().st_mode & 0xFFFF) << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def write_tar(target: Path) -> None:
    target.unlink(missing_ok=True)
    with tarfile.open(target, "w:gz", compresslevel=9) as archive:
        for path in iter_files(source=False):
            relative = path.relative_to(ROOT).as_posix()
            archive.add(path, arcname=f"{TOP_LEVEL}/{relative}", recursive=False)


def main() -> None:
    generate_manifest()
    complete_zip = OUTPUT / f"ARGWS-Git-Monitor-v{VERSION}-PACOTE-COMPLETO.zip"
    source_zip = OUTPUT / f"ARGWS-Git-Monitor-v{VERSION}-FONTE-GITHUB.zip"
    complete_tar = OUTPUT / f"ARGWS-Git-Monitor-v{VERSION}-PACOTE-COMPLETO.tar.gz"
    write_zip(complete_zip, source=False)
    write_zip(source_zip, source=True)
    write_tar(complete_tar)

    artifacts = [complete_zip, source_zip, complete_tar]
    checksums = OUTPUT / f"ARGWS-Git-Monitor-v{VERSION}-SHA256SUMS.txt"
    checksums.write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in artifacts),
        encoding="utf-8",
    )
    print("Pacotes gerados:")
    for path in [*artifacts, checksums]:
        print(f"- {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
