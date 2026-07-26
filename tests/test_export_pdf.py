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

    def run_export(self, html: Path, pdf: Path,
                   *extra: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        browser_args = ([] if not env.get("DECK_FORGE_TEST_BROWSER_EXECUTABLE")
                        else ["--browser-executable",
                              env["DECK_FORGE_TEST_BROWSER_EXECUTABLE"]])
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), str(html), str(pdf),
             "--compact", *browser_args, *extra],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=env, timeout=90, check=False,
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

    def test_invalid_browser_executable_fails_before_export(self) -> None:
        html = self.temp / "deck.html"
        pdf = self.temp / "deck.pdf"
        html.write_text(HTML, encoding="utf-8")
        result = self.run_export(
            html, pdf, "--browser-executable", str(self.temp / "missing.exe"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--browser-executable is not a file",
                      result.stdout + result.stderr)
        self.assertFalse(pdf.exists())

    def test_keep_pngs_saves_captures_hides_chrome_purges_stale(self) -> None:
        html = self.temp / "deck.html"
        pdf = self.temp / "deck.pdf"
        pngs = self.temp / "pngs"
        pngs.mkdir()
        stale = pngs / "slide-009.png"        # leftover from a "previous run"
        stale.write_bytes(b"stale")
        html.write_text(HTML, encoding="utf-8")
        result = self.run_export(html, pdf, "--keep-pngs", str(pngs))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(sorted(p.name for p in pngs.glob("*.png")),
                         ["slide-001.png", "slide-002.png"])
        self.assertFalse(stale.exists())

        # Direct chrome-hiding assertion: .deck-controls is a full-viewport
        # magenta overlay in the fixture; if EXPORT_CSS failed to hide it,
        # every captured pixel would be #ff00ff.
        from PIL import Image
        with Image.open(pngs / "slide-001.png") as img:
            rgb = img.convert("RGB")
            samples = [rgb.getpixel((x, y))
                       for x in (10, 960, 1900) for y in (10, 540, 1070)]
        self.assertNotIn((255, 0, 255), samples,
                         "presentation chrome leaked into the capture")

    def test_require_font_fails_when_family_unresolved(self) -> None:
        html = self.temp / "deck.html"
        pdf = self.temp / "deck.pdf"
        html.write_text(HTML, encoding="utf-8")
        result = self.run_export(html, pdf,
                                 "--require-font", "DeckForge-No-Such-Font")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("required font not available",
                      result.stdout + result.stderr)
        self.assertFalse(pdf.exists())

    def test_missing_asset_fails_closed_unless_ignored(self) -> None:
        broken = HTML.replace(
            '<section class="slide active"><h1 class="reveal">第一页</h1></section>',
            '<section class="slide active"><h1 class="reveal">第一页</h1>'
            '<img src="missing-asset.png"></section>')
        html = self.temp / "broken.html"
        pdf = self.temp / "broken.pdf"
        html.write_text(broken, encoding="utf-8")

        result = self.run_export(html, pdf)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing-asset.png", result.stdout + result.stderr)
        self.assertFalse(pdf.exists())

        ignored = self.run_export(html, pdf, "--ignore-resource-errors")
        self.assertEqual(ignored.returncode, 0, ignored.stdout + ignored.stderr)
        self.assertIn("WARNING (ignored)", ignored.stdout)
        self.assertTrue(pdf.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
