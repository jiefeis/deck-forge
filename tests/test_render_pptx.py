#!/usr/bin/env python3
"""Windows integration test for scripts/render_pptx.ps1."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from pptx import Presentation


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "render_pptx.ps1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RenderPptxTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt" and shutil.which("powershell.exe"),
                         "PowerPoint/WPS COM rendering is Windows-only")
    def test_visible_and_hidden_render_without_source_mutation(self) -> None:
        temp = Path(tempfile.mkdtemp(prefix="deckforge-render-test-"))
        try:
            pptx = temp / "source.pptx"
            prs = Presentation()
            visible = prs.slides.add_slide(prs.slide_layouts[1])
            visible.shapes.title.text = "VISIBLE"
            hidden = prs.slides.add_slide(prs.slide_layouts[1])
            hidden.shapes.title.text = "HIDDEN"
            hidden._element.set("show", "0")
            prs.save(pptx)
            before = sha256(pptx)

            # Regression guard for the PSModulePath inheritance bug: a child
            # powershell.exe launched under PowerShell 7's PSModulePath loads the
            # Core Microsoft.PowerShell.Utility, where Get-FileHash is not
            # available, and the render aborts. render_pptx.ps1 must hash via
            # .NET, not Get-FileHash. Simulate it with a higher-version Core
            # Utility manifest ahead of the real one on PSModulePath.
            fake_util = temp / "ps7" / "Modules" / "Microsoft.PowerShell.Utility"
            fake_util.mkdir(parents=True)
            (fake_util / "Microsoft.PowerShell.Utility.psd1").write_text(
                "@{\n"
                "GUID = '1DA87E53-152B-403E-98DC-74D7B4D63D59'\n"
                "ModuleVersion = '7.0.0.0'\n"
                "CompatiblePSEditions = @('Core')\n"
                "NestedModules = 'Microsoft.PowerShell.Commands.Utility.dll'\n"
                "CmdletsToExport = @('Get-FileHash')\n"
                "FunctionsToExport = @()\n"
                "AliasesToExport = @()\n"
                "}\n",
                encoding="ascii",
            )
            env = os.environ.copy()
            env["PSModulePath"] = (
                str(fake_util.parent) + os.pathsep + env.get("PSModulePath", "")
            )

            visible_dir = temp / "visible"
            all_dir = temp / "all"
            base = [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(SCRIPT), "-InputPptx", str(pptx),
            ]
            first = subprocess.run(
                base + ["-OutputDir", str(visible_dir), "-Engine", "auto"],
                capture_output=True, text=True, timeout=90, env=env,
            )
            if first.returncode and "No supported presentation engine" in (
                first.stdout + first.stderr
            ):
                self.skipTest("PowerPoint/WPS COM engine is not registered")
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            second = subprocess.run(
                base + ["-OutputDir", str(all_dir), "-Engine", "auto",
                        "-IncludeHidden"],
                capture_output=True, text=True, timeout=90, env=env,
            )
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)

            self.assertEqual(before, sha256(pptx))
            self.assertEqual(len(list(visible_dir.glob("slide-*.png"))), 1)
            self.assertEqual(len(list(all_dir.glob("slide-*.png"))), 2)
            manifest = json.loads(
                (visible_dir / "render-manifest.json").read_text(encoding="utf-8-sig")
            )
            self.assertEqual(manifest["slide_count"], 2)
            self.assertEqual(manifest["hidden_physical_indices"], [2])
            self.assertFalse(manifest["include_hidden"])
            # The .NET SHA-256 helper must agree with an independent hash.
            self.assertEqual(manifest["source_sha256"].lower(), before.lower())
        finally:
            shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
