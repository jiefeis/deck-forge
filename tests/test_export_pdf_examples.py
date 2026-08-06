#!/usr/bin/env python3
"""End-to-end export + audit integration tests on the two bundled examples.

lumen-2026 is the canonical deck; aurora-metrics deliberately deviates from
viewport-base.css to stress exporter compatibility. Both load Google Fonts, so
these tests skip cleanly when that CDN is unreachable (the exporter itself
fails closed on font errors by design — that behavior has its own offline
tests in test_export_pdf.py).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EXPORT = ROOT / "scripts" / "export_pdf.py"
AUDIT = ROOT / "scripts" / "audit_html_slides.py"
EXAMPLES = ROOT / "examples"


def _fonts_cdn_reachable() -> bool:
    # The decks need both hosts: googleapis serves the CSS, gstatic the woff2.
    for url in ("https://fonts.googleapis.com/css2?family=Roboto",
                "https://fonts.gstatic.com/"):
        try:
            urllib.request.urlopen(url, timeout=5)
        except urllib.error.HTTPError:
            pass                        # reachable; status is irrelevant
        except Exception:
            return False
    return True


# With DECK_FORGE_REQUIRE_CDN=1 (set in CI) an unreachable CDN is a hard
# failure, not a silent skip: these tests are the only end-to-end coverage of
# the bundled examples. Without the variable, local offline runs skip cleanly.
_REQUIRE_CDN = os.environ.get("DECK_FORGE_REQUIRE_CDN") == "1"
_CDN_REACHABLE = _fonts_cdn_reachable()


@unittest.skipUnless(_CDN_REACHABLE or _REQUIRE_CDN,
                     "fonts.googleapis.com unreachable; examples need webfonts")
class ExampleDeckTests(unittest.TestCase):
    def setUp(self) -> None:
        if _REQUIRE_CDN and not _CDN_REACHABLE:
            self.fail(
                "DECK_FORGE_REQUIRE_CDN=1 but fonts.googleapis.com / "
                "fonts.gstatic.com are unreachable; the example-deck "
                "end-to-end tests must not be skipped in this environment"
            )
        self.temp_dir = tempfile.TemporaryDirectory(prefix="deckforge-examples-")
        self.temp = Path(self.temp_dir.name)
        self.env = os.environ.copy()
        self.env["PYTHONUTF8"] = "1"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_script(self, script: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(script), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=self.env, timeout=300, check=False,
        )

    def run_with_retry(self, script: Path,
                       *args: str) -> subprocess.CompletedProcess[str]:
        # One retry on ANY failure: transient CDN hiccups surface as exporter
        # resource errors (stdout) OR Playwright network timeouts (stderr
        # traceback); a deterministic failure fails twice anyway.
        result = self.run_script(script, *args)
        if result.returncode:
            result = self.run_script(script, *args)
        return result

    def export_and_check(self, example: str) -> None:
        html = EXAMPLES / example / "index.html"
        pdf = self.temp / f"{example}.pdf"
        pngs = self.temp / f"{example}-pngs"
        result = self.run_with_retry(EXPORT, str(html), str(pdf),
                                     "--compact", "--keep-pngs", str(pngs))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        found = re.search(r"Found (\d+) slides", result.stdout)
        self.assertIsNotNone(found, result.stdout)
        slides = int(found.group(1))
        self.assertGreaterEqual(slides, 2)

        data = pdf.read_bytes()
        self.assertNotIn(b"/DCTDecode", data)          # lossless contract
        self.assertIn(b"/FlateDecode", data)
        pages = len(re.findall(rb"/Type\s*/Page\b", data))
        self.assertEqual(pages, slides)

        kept = sorted(p.name for p in pngs.glob("slide-*.png"))
        self.assertEqual(len(kept), slides)            # v1/v2 comparison inputs
        self.assertEqual(kept[0], "slide-001.png")

    def test_lumen_2026_exports_cleanly(self) -> None:
        self.export_and_check("lumen-2026")

    def test_aurora_metrics_exports_cleanly(self) -> None:
        self.export_and_check("aurora-metrics")

    def test_lumen_2026_passes_html_audit(self) -> None:
        # The --require-font families are webfonts the deck actually loads —
        # the positive control for the metric-based availability probe.
        result = self.run_with_retry(
            AUDIT, str(EXAMPLES / "lumen-2026" / "index.html"),
            "--require-font", "Noto Serif SC",
            "--require-font", "Space Grotesk")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
