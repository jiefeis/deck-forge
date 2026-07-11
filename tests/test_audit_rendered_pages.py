#!/usr/bin/env python3
"""Synthetic regression tests for scripts/audit_rendered_pages.py."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "audit_rendered_pages.py"
SPEC = importlib.util.spec_from_file_location("audit_rendered_pages", SCRIPT)
AUDIT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AUDIT
SPEC.loader.exec_module(AUDIT)


def pattern_image(width: int = 64, height: int = 36, offset: int = 0) -> Image.Image:
    image = Image.new("RGB", (width, height))
    image.putdata(
        [
            (
                (x * 13 + offset) % 256,
                (y * 19 + offset * 3) % 256,
                ((x + y) * 11 + offset * 5) % 256,
            )
            for y in range(height)
            for x in range(width)
        ]
    )
    return image


def save_image(directory: Path, index: int, image: Image.Image) -> Path:
    path = directory / f"slide-{index:03d}.png"
    image.save(path, "PNG")
    image.close()
    return path


class RenderedPageAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="deckforge-render-audit-")
        root = Path(self.temp.name)
        self.source = root / "source"
        self.target = root / "target"
        self.source.mkdir()
        self.target.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_identical_pages_pass(self) -> None:
        save_image(self.source, 1, pattern_image())
        save_image(self.target, 1, pattern_image())

        report = AUDIT.audit_rendered_pages(self.source, self.target)

        self.assertTrue(report["ok"])
        self.assertEqual(report["exit_code"], 0)
        self.assertEqual(report["summary"]["difference_count"], 0)
        self.assertEqual(report["slides"][0]["status"], "identical")

    def test_unauthorized_change_fails_and_tolerance_is_configurable(self) -> None:
        save_image(self.source, 1, pattern_image())
        changed = pattern_image()
        changed.putpixel((0, 0), (255, 255, 255))
        save_image(self.target, 1, changed)

        failed = AUDIT.audit_rendered_pages(self.source, self.target)
        tolerated = AUDIT.audit_rendered_pages(
            self.source,
            self.target,
            max_changed_ratio=0.001,
        )

        self.assertFalse(failed["ok"])
        self.assertIn(
            "unauthorized-pixel-change",
            {item["code"] for item in failed["violations"]},
        )
        self.assertTrue(tolerated["ok"])
        self.assertEqual(tolerated["slides"][0]["status"], "changed-tolerated")

    def test_authorized_change_is_reported_without_failure(self) -> None:
        save_image(self.source, 3, pattern_image())
        save_image(self.target, 3, pattern_image(offset=17))

        report = AUDIT.audit_rendered_pages(
            self.source,
            self.target,
            allow_slides={3},
        )

        self.assertTrue(report["ok"])
        self.assertEqual(report["summary"]["difference_count"], 1)
        self.assertEqual(report["differences"][0]["disposition"], "allowed")
        self.assertEqual(report["slides"][0]["status"], "changed-authorized")

    def test_missing_physical_page_always_fails(self) -> None:
        save_image(self.source, 1, pattern_image())
        save_image(self.source, 2, pattern_image(offset=9))
        save_image(self.target, 1, pattern_image())

        report = AUDIT.audit_rendered_pages(
            self.source,
            self.target,
            allow_slides={2},
        )

        self.assertFalse(report["ok"])
        self.assertIn(
            "missing-target-page",
            {item["code"] for item in report["violations"]},
        )
        self.assertEqual(report["summary"]["missing_page_count"], 1)

    def test_white_overlay_fails_even_when_pixel_change_is_authorized(self) -> None:
        save_image(self.source, 1, pattern_image())
        save_image(self.target, 1, Image.new("RGB", (64, 36), "white"))

        report = AUDIT.audit_rendered_pages(
            self.source,
            self.target,
            allow_slides={1},
        )

        self.assertFalse(report["ok"])
        codes = {item["code"] for item in report["violations"]}
        self.assertIn("near-white-coverage", codes)
        self.assertIn("low-variance-coverage", codes)
        self.assertNotIn("unauthorized-pixel-change", codes)

    def test_legitimate_dark_page_requires_explicit_solid_allowance(self) -> None:
        save_image(self.source, 5, Image.new("RGB", (64, 36), (18, 18, 18)))
        save_image(self.target, 5, Image.new("RGB", (64, 36), (18, 18, 18)))

        blocked = AUDIT.audit_rendered_pages(self.source, self.target)
        allowed = AUDIT.audit_rendered_pages(
            self.source,
            self.target,
            allow_solid_slides={5},
        )

        self.assertFalse(blocked["ok"])
        self.assertIn(
            "low-variance-coverage",
            {item["code"] for item in blocked["violations"]},
        )
        self.assertTrue(allowed["ok"])
        self.assertGreater(allowed["summary"]["allowed_solid_risk_count"], 0)

    def test_explicit_page_map_compares_backup_at_different_index(self) -> None:
        save_image(self.source, 3, pattern_image(offset=7))
        save_image(self.target, 50, pattern_image(offset=7))

        report = AUDIT.audit_rendered_pages(
            self.source,
            self.target,
            page_map={3: 50},
        )

        self.assertTrue(report["ok"])
        self.assertEqual(report["summary"]["audited_page_pair_count"], 1)
        self.assertEqual(report["slides"][0]["source_physical_index"], 3)
        self.assertEqual(report["slides"][0]["target_physical_index"], 50)
        self.assertEqual(report["policy"]["page_map"], [{"source": 3, "target": 50}])

    def test_explicit_page_map_rejects_missing_or_duplicate_targets(self) -> None:
        save_image(self.source, 3, pattern_image())
        save_image(self.target, 50, pattern_image())

        missing = AUDIT.audit_rendered_pages(
            self.source,
            self.target,
            page_map={4: 50},
        )
        self.assertFalse(missing["ok"])
        self.assertIn(
            "missing-source-page",
            {item["code"] for item in missing["violations"]},
        )
        with self.assertRaises(AUDIT.AuditError):
            AUDIT.parse_page_maps(["3:50", "4:50"])

    def test_cli_json_and_exit_codes(self) -> None:
        save_image(self.source, 1, pattern_image())
        save_image(self.target, 1, pattern_image())
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        passed = subprocess.run(
            [sys.executable, str(SCRIPT), str(self.source), str(self.target), "--json"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
        save_image(self.target, 1, pattern_image(offset=23))
        failed = subprocess.run(
            [sys.executable, str(SCRIPT), str(self.source), str(self.target), "--json"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
        bad_input = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(self.source / "missing"),
                str(self.target),
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )

        self.assertEqual(passed.returncode, 0, passed.stderr)
        self.assertTrue(json.loads(passed.stdout)["ok"])
        self.assertEqual(failed.returncode, 1, failed.stderr)
        self.assertEqual(json.loads(failed.stdout)["exit_code"], 1)
        self.assertEqual(bad_input.returncode, 2, bad_input.stderr)
        self.assertEqual(json.loads(bad_input.stdout)["exit_code"], 2)

    def test_cli_page_map_and_invalid_duplicate_target(self) -> None:
        save_image(self.source, 3, pattern_image(offset=4))
        save_image(self.target, 50, pattern_image(offset=4))
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        passed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(self.source),
                str(self.target),
                "--page-map",
                "3:50",
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
        rejected = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(self.source),
                str(self.target),
                "--page-map",
                "3:50",
                "--page-map",
                "4:50",
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )

        self.assertEqual(passed.returncode, 0, passed.stderr)
        self.assertTrue(json.loads(passed.stdout)["ok"])
        self.assertEqual(rejected.returncode, 2, rejected.stderr)
        self.assertEqual(json.loads(rejected.stdout)["exit_code"], 2)


if __name__ == "__main__":
    unittest.main()
