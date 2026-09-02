#!/usr/bin/env python3
"""Regression tests for scripts/audit_html_slides.py (synthetic decks)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "audit_html_slides.py"


def deck(slides: str, extra_css: str = "") -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;width:100%;height:100%;overflow:hidden}}
.deck-stage{{position:absolute;left:0;top:0;width:1920px;height:1080px;overflow:hidden}}
.slide{{position:absolute;inset:0;width:1920px;height:1080px;overflow:hidden;visibility:hidden;background:#fff}}
.slide.active,.slide.visible{{visibility:visible}}
h1,p,div{{margin:0;font-size:48px}}
{extra_css}</style></head><body><main class="deck-stage">{slides}</main></body></html>"""


CLEAN = deck(
    '<section class="slide active"><h1 style="padding:80px">封面标题</h1>'
    '<p style="position:absolute;left:80px;top:900px">页脚 · 2026</p></section>'
    '<section class="slide"><h1 style="padding:80px">Second slide</h1>'
    '<p style="position:absolute;left:80px;top:900px">footer</p></section>')


class AuditHtmlSlidesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="deckforge-audit-html-")
        self.temp = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_audit(self, html: str, *args: str,
                  utf8_env: bool = True) -> subprocess.CompletedProcess[str]:
        path = self.temp / "deck.html"
        path.write_text(html, encoding="utf-8")
        env = os.environ.copy()
        if utf8_env:
            env["PYTHONUTF8"] = "1"
        else:
            env.pop("PYTHONUTF8", None)   # exercise the locale-codepage path
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), str(path), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=env, timeout=120, check=False,
        )

    def test_clean_deck_passes(self) -> None:
        result = self.run_audit(CLEAN)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OK", result.stdout)

    def test_defect_slides_fail_with_named_checks(self) -> None:
        # One defect per slide so every hard check is exercised in one run.
        result = self.run_audit(deck(
            # slide 1: clipped text (clips at 40px, content is far taller)
            '<section class="slide active"><div style="width:600px;height:40px;'
            'overflow:hidden">Line one<br>Line two<br>Line three</div></section>'
            # slide 2: text crossing the bottom stage edge
            '<section class="slide"><h1 style="position:absolute;left:80px;'
            'top:1040px">Runs off the bottom edge</h1></section>'
            # slide 3: broken image (HTTP 404) + refused connection
            # (requestfailed path) + a webfont whose file 404s (FontFace error)
            '<section class="slide"><h1 style="font-family:DeckForgeGhostFont">'
            'With image</h1>'
            '<img src="does-not-exist.png" style="width:400px;height:300px">'
            '<img src="http://127.0.0.1:1/refused.png" '
            'style="width:40px;height:40px">'
            '</section>'
            # slide 4: completely blank
            '<section class="slide"></section>',
            extra_css='@font-face{font-family:DeckForgeGhostFont;'
                      'src:url("missing.woff2")}'))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        out = result.stdout
        for check in ("clipped-text", "offstage-text", "broken-image",
                      "blank-slide", "resource-error", "font-error",
                      "request failed"):
            self.assertIn(check, out, f"expected {check} in:\n{out}")

        # Both overflow verdicts must say how far the text actually reaches:
        # 3px of bleed and 300px of spill call for different repairs and read
        # identically without a magnitude.
        for check in ("clipped-text", "offstage-text"):
            line = next(l for l in out.splitlines() if check in l)
            magnitude = re.search(r"\[\+(\d+)px\]", line)
            self.assertIsNotNone(magnitude, f"no pixel magnitude: {line}")
            self.assertGreater(int(magnitude.group(1)), 0, line)

    def test_decorative_bleed_inside_clipping_card_passes(self) -> None:
        # A rounded overflow:hidden card whose decorative glow bleeds past its
        # edge is a standard template pattern; only TEXT leaving the clip box
        # may fail. (Regression: element scroll-size measurement flagged this.)
        result = self.run_audit(deck(
            '<section class="slide active">'
            '<div style="position:relative;width:800px;height:400px;'
            'overflow:hidden;background:#222;margin:80px">'
            '<div style="position:absolute;right:-250px;bottom:-150px;'
            'width:500px;height:400px;background:#0ff"></div>'
            '<h1 style="padding:60px;color:#fff">Card body text fits fine.</h1>'
            '</div>'
            '<p style="position:absolute;left:80px;top:900px">footer</p>'
            '</section>'))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_allow_clipped_text_excuses_deliberate_mask(self) -> None:
        masked = deck(
            '<section class="slide active">'
            '<div style="width:600px;height:40px;overflow:hidden">'
            'Masked display word</div>'
            '<p style="position:absolute;left:80px;top:900px">footer</p>'
            '</section>')
        plain = self.run_audit(masked)
        self.assertEqual(plain.returncode, 1)
        self.assertIn("clipped-text", plain.stdout)
        excused = self.run_audit(masked, "--allow-clipped-text", "Masked display")
        self.assertEqual(excused.returncode, 0, excused.stdout + excused.stderr)

    def test_require_font_missing_fails_generic_passes(self) -> None:
        missing = self.run_audit(CLEAN, "--require-font", "DeckForge-No-Such-Font")
        self.assertEqual(missing.returncode, 1)
        self.assertIn("font-missing", missing.stdout)
        generic = self.run_audit(CLEAN, "--require-font", "sans-serif")
        self.assertEqual(generic.returncode, 0, generic.stdout + generic.stderr)

    def test_emoji_findings_survive_locale_codepage_stdout(self) -> None:
        # Findings echo slide text; without PYTHONUTF8 a cp936/cp1252 pipe must
        # degrade (errors=replace), not crash the gate with UnicodeEncodeError.
        result = self.run_audit(deck(
            '<section class="slide active">'
            '<h1 style="position:absolute;left:100px;top:100px">🚀 Alpha ✦</h1>'
            '<p style="position:absolute;left:110px;top:110px">Beta overlaps</p>'
            '<p style="position:absolute;left:80px;top:900px">footer</p>'
            '</section>'), utf8_env=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("UnicodeEncodeError", result.stdout + result.stderr)
        self.assertIn("text-overlap", result.stdout)

    def test_magnitude_is_not_part_of_the_excuse_match_surface(self) -> None:
        # The " [+Npx]" magnitude is report text, not match surface. If excuses
        # matched against it, "px" — or whatever pixel count a finding happens
        # to carry — would excuse every finding of that kind and turn this
        # fail-closed gate into a pass on real defects.
        clipped = deck(
            '<section class="slide active"><div style="width:600px;height:40px;'
            'overflow:hidden">Line one<br>Line two<br>Line three</div></section>')
        for snippet in ("px", "[+", "21px"):
            result = self.run_audit(clipped, "--allow-clipped-text", snippet)
            self.assertEqual(result.returncode, 1,
                             f"{snippet!r} must excuse nothing:\n{result.stdout}")
            self.assertIn("clipped-text", result.stdout,
                          f"{snippet!r} swallowed a real finding:\n{result.stdout}")

    def test_magnitude_is_measured_from_the_real_stage_edge(self) -> None:
        # Regression: measuring from the TOL-expanded box understated every
        # magnitude by exactly TOL, so a 3px bleed reported as +1px — wrong at
        # the small end, which is where the repair decision is close.
        result = self.run_audit(deck(
            '<section class="slide active"><div style="position:absolute;'
            'left:-3px;top:100px;font:20px/1 monospace;white-space:nowrap">'
            'SPILL</div></section>'))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        line = next(l for l in result.stdout.splitlines() if "offstage-text" in l)
        self.assertIn("[+3px]", line, line)

    def test_offstage_excuse_and_unused_excuse(self) -> None:
        offstage = deck(
            '<section class="slide active"><h1 style="position:absolute;'
            'left:80px;top:1040px">Deliberate bleed</h1>'
            '<p style="padding:80px">body</p></section>')
        excused = self.run_audit(offstage, "--allow-offstage-text", "Deliberate bleed")
        self.assertEqual(excused.returncode, 0, excused.stdout + excused.stderr)
        unused = self.run_audit(offstage,
                                "--allow-offstage-text", "Deliberate bleed",
                                "--allow-offstage-text", "matches nothing")
        self.assertEqual(unused.returncode, 1)
        self.assertIn("unused-excuse", unused.stdout)

    def test_slide_geometry_fails(self) -> None:
        result = self.run_audit(deck(
            '<section class="slide active"><h1 style="padding:80px">x</h1></section>',
            extra_css=".slide{width:1600px}"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("slide-geometry", result.stdout)

    def test_expect_slides_and_json(self) -> None:
        result = self.run_audit(CLEAN, "--expect-slides", "3", "--json")
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["slides"], 2)
        self.assertIn("slide-count", [f["check"] for f in report["failures"]])

    def test_overlap_and_empty_bottom_warn_but_pass(self) -> None:
        result = self.run_audit(deck(
            '<section class="slide active">'
            '<h1 style="position:absolute;left:100px;top:100px">Alpha text</h1>'
            '<p style="position:absolute;left:120px;top:110px">Beta overlaps</p>'
            '</section>'))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("text-overlap", result.stdout)
        self.assertIn("empty-bottom", result.stdout)

    def test_zero_slides_fails(self) -> None:
        result = self.run_audit("<!doctype html><html><body>none</body></html>")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no-slides", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
