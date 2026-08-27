from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from auto_version import (
    AutoVersionError,
    apply_version,
    bump_version,
    classify_message,
    format_version,
    highest_bump,
    parse_semver,
    verify_version,
)


class AutoVersionTests(unittest.TestCase):
    def test_parse_and_bump_semver(self) -> None:
        self.assertEqual(parse_semver("v0.5.0"), (0, 5, 0))
        self.assertEqual(format_version(bump_version((0, 5, 0), "patch")), "0.5.1")
        self.assertEqual(format_version(bump_version((0, 5, 0), "minor")), "0.6.0")
        self.assertEqual(format_version(bump_version((0, 5, 0), "major")), "1.0.0")
        with self.assertRaises(AutoVersionError):
            parse_semver("0.5")

    def test_commit_classification(self) -> None:
        self.assertEqual(classify_message("feat: nova API"), "minor")
        self.assertEqual(classify_message("fix(release): corrigir publicação"), "patch")
        self.assertEqual(classify_message("perf: reduzir latência"), "patch")
        self.assertEqual(classify_message("feat!: alterar contrato\n\nBREAKING CHANGE: novo formato"), "major")
        self.assertEqual(classify_message("texto sem conventional commit"), "patch")
        self.assertIsNone(classify_message("chore(release): v0.6.0 [skip release]"))
        self.assertEqual(classify_message("docs: manual [release:minor]"), "minor")

    def test_highest_bump_wins(self) -> None:
        self.assertEqual(
            highest_bump(["fix: a", "feat: b", "docs: c"]),
            "minor",
        )
        self.assertEqual(
            highest_bump(["feat: a", "fix!: b"]),
            "major",
        )

    def test_apply_and_verify_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "backend").mkdir()
            (root / "frontend").mkdir()
            (root / "VERSION").write_text("0.5.0\n", encoding="utf-8")
            (root / "backend" / "pyproject.toml").write_text(
                '[project]\nname = "example"\nversion = "0.5.0"\n',
                encoding="utf-8",
            )
            (root / "frontend" / "package.json").write_text(
                json.dumps({"name": "example", "version": "0.5.0"}) + "\n",
                encoding="utf-8",
            )

            apply_version(root, "0.6.0")
            verify_version(root, "0.6.0")

            self.assertEqual((root / "VERSION").read_text(encoding="utf-8"), "0.6.0\n")
            self.assertIn(
                'version = "0.6.0"',
                (root / "backend" / "pyproject.toml").read_text(encoding="utf-8"),
            )
            package = json.loads((root / "frontend" / "package.json").read_text(encoding="utf-8"))
            self.assertEqual(package["version"], "0.6.0")

    def test_verify_detects_divergence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "backend").mkdir()
            (root / "frontend").mkdir()
            (root / "VERSION").write_text("0.6.0\n", encoding="utf-8")
            (root / "backend" / "pyproject.toml").write_text(
                '[project]\nversion = "0.5.0"\n',
                encoding="utf-8",
            )
            (root / "frontend" / "package.json").write_text(
                '{"version":"0.6.0"}\n',
                encoding="utf-8",
            )

            with self.assertRaises(AutoVersionError):
                verify_version(root, "0.6.0")


if __name__ == "__main__":
    unittest.main(verbosity=2)
