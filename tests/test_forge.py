"""Exercise the public verification commands with native and HTML decks."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from pptx import Presentation
from pptx.util import Inches


ROOT = Path(__file__).resolve().parents[1]


class VerifyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def invoke(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(ROOT / "scripts/forge.py"), *map(str, args), "--json"],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=120)

    def sources(self):
        source, target = self.root / "原始.pptx", self.root / "修改.pptx"
        deck = Presentation()
        boxes = []
        for text in ("Sales", "Protected"):
            slide = deck.slides.add_slide(deck.slide_layouts[6])
            box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(1))
            box.text = text
            boxes.append(box)
        deck.save(source)
        boxes[0].text = "全面赋能"
        deck.save(target)
        return source, target

    def test_scope_resolves_slide_ids_and_flags_copy(self):
        source, target = self.sources()
        scope = self.root / "scope.json"
        scope.write_text(json.dumps({"version": 1, "rules": [
            {"id": "revise-title", "pages": "1", "properties": ["text"]}]}))
        result = self.invoke("verify-pptx", target, "--source", source, "--scope", scope,
                             "--structural-only", "--out", "qa")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        statuses = {c["check"]: c["status"] for c in report["checks"]}
        self.assertEqual(statuses["structure"], "PASS")
        self.assertEqual(statuses["properties"], "PASS")
        self.assertEqual(statuses["visual"], "NOT_REQUESTED")
        self.assertIn({"slide": 1, "check": "copy-review", "detail": "全面赋能"}, report["warnings"])
        self.assertEqual(json.loads((self.root / "qa/report.json").read_text(encoding="utf-8")), report)
        # A new run may not overwrite an earlier evidence directory.
        repeated = self.invoke("verify-pptx", target, "--structural-only", "--out", "qa")
        self.assertNotEqual(repeated.returncode, 0)

    def test_no_permission_to_change_other_slides(self):
        source, target = self.sources()
        result = self.invoke("verify-pptx", target, "--source", source, "--allow-slides", "2",
                             "--structural-only", "--out", "qa")
        self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertIn(("structure", "FAIL"), [(c["check"], c["status"]) for c in report["checks"]])
        invalid = self.invoke("verify-pptx", target, "--target-language", "en", "--structural-only")
        self.assertEqual(invalid.returncode, 2)

    def test_html_protected_markup_even_when_pixels_match(self):
        src, dest = self.root / "original.html", self.root / "edited.html"
        html = """<!doctype html><meta charset="utf-8"><style>
        *{margin:0}.deck-stage{width:1920px;height:1080px;position:absolute;top:0;left:0}
        .slide{position:absolute;inset:0;width:1920px;height:1080px;background:white;
        visibility:hidden}.slide.active,.slide.visible{visibility:visible}</style>
        <main class="deck-stage"><section class="slide active"><h1>标题</h1></section>
        <section class="slide"><h1>第二页</h1></section></main>"""
        src.write_text(html, encoding="utf-8")
        dest.write_text(html.replace("标题", "关键抓手").replace('class="slide"><h1>', 'class="slide" data-x="1"><h1>'), encoding="utf-8")
        result = self.invoke("verify-html", dest, "--source", src, "--allow-slides", "1",
                             "--expect-slides", "2", "--out", "qa")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        checks = {c["check"]: c for c in report["checks"]}
        self.assertEqual(checks["slide-markup"]["outside_scope"], [2])
        self.assertEqual(checks["contact-sheet"]["status"], "PASS")
        self.assertTrue((self.root / "qa/contact-sheet.png").is_file())
        self.assertIn({"slide": 1, "check": "copy-review", "detail": "关键抓手"}, report["warnings"])


if __name__ == "__main__":
    unittest.main()
