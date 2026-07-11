#!/usr/bin/env python3
"""Integration smoke tests for scripts/export_pdf.py."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "export_pdf.py"


HTML = """<!doctype html>
<html><head><meta charset="utf-8"><style>
html,body{margin:0;width:100%;height:100%;overflow:hidden}
.deck-stage{position:absolute;width:1920px;height:1080px}
.slide{position:absolute;inset:0;width:1920px;height:1080px;visibility:hidden}
.slide.active,.slide.visible{visibility:visible}
.reveal{opacity:0;transform:translateY(20px)}
.deck-controls{position:fixed;inset:0;background:#ff00ff}
</style></head><body><main class="deck-stage">
<section class="slide active"><h1 class="reveal">第一页</h1></section>
<section class="slide"><h1 class="reveal">Second page</h1></section>
</main><div class="deck-controls">MUST HIDE</div></body></html>"""


class ExportPdfTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="deckforge-export-test-")
        self.temp = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_export(self, html: Path, pdf: Path) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), str(html), str(pdf), "--compact"],
            capture_output=True, text=True, env=env, timeout=90, check=False,
        )

    def test_lossless_two_page_export_with_cjk_path(self) -> None:
        html = self.temp / "演示 deck.html"
        pdf = self.temp / "演示 deck.pdf"
        html.write_text(HTML, encoding="utf-8")
        result = self.run_export(html, pdf)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = pdf.read_bytes()
        self.assertGreater(len(data), 20_000)
        self.assertNotIn(b"/DCTDecode", data)
        self.assertIn(b"/FlateDecode", data)
        pages = len(re.findall(rb"/Type\s*/Page\b", data))
        self.assertEqual(pages, 2)

    def test_zero_slide_input_fails(self) -> None:
        html = self.temp / "empty.html"
        pdf = self.temp / "empty.pdf"
        html.write_text("<!doctype html><html><body>none</body></html>", encoding="utf-8")
        result = self.run_export(html, pdf)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("0 slides found", result.stdout + result.stderr)
        self.assertFalse(pdf.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
