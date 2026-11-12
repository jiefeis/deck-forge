"""Smoke-test the actual committed runtime ZIP, without the source checkout on sys.path."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Inches


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import package_skill


class PackageTests(unittest.TestCase):
    def test_export_ignored_runtime_helper_blocks_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            for name in package_skill.REQUIRED | package_skill.TRANSLATION_AND_AUDIT:
                path = repo / name
                path.parent.mkdir(exist_ok=True, parents=True)
                path.write_bytes(b"fixture\n")
            (repo / ".gitattributes").write_text("/.gitattributes export-ignore\n/scripts/_chart_workbook.py export-ignore\n")
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                            "-c", "commit.gpgsign=false", "commit", "-qm", "fixture"], cwd=repo, check=True)
            output = repo / "release.zip"
            with patch.object(package_skill, "ROOT", repo), self.assertRaisesRegex(ValueError, "_chart_workbook.py"):
                package_skill.build("HEAD", output)
            self.assertFalse(output.exists())

    def test_extracted_entrypoints_and_resources(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            archive = folder / "deck-forge.zip"
            env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}
            subprocess.run([sys.executable, str(ROOT / "tools/package_skill.py"),
                            "--output", str(archive)], cwd=folder, env=env, check=True)
            with zipfile.ZipFile(archive) as package:
                package.extractall(folder)
            installed = folder / "deck-forge"
            for arguments in [
                ["validate_skill_structure.py", str(installed)], ["validate_template_pack.py", str(installed)],
                ["native_charts.py", "inspect", "--help"], ["native_charts.py", "audit", "--help"],
                ["translate_pptx.py", "extract", "--help"], ["translate_pptx.py", "apply", "--help"],
                ["render_pptx.py", "--help"], ["forge.py", "preflight", "--help"],
                ["forge.py", "verify-html", "--help"], ["forge.py", "verify-pptx", "--help"],
            ]:
                with self.subTest(arguments=arguments):
                    script, *args = arguments
                    subprocess.run([sys.executable, "-B", str(installed / "scripts" / script), *args],
                                   cwd=folder, stdout=subprocess.DEVNULL, env=env, check=True)

            # Exercise lazy imports and child scripts from the ZIP, including the XLSX writer.
            def run_installed(script, *args):
                return subprocess.check_output([sys.executable, "-B", str(installed / "scripts" / script), *args],
                                               cwd=folder, env=env, text=True, encoding="utf-8")

            deck = Presentation()
            slide = deck.slides.add_slide(deck.slide_layouts[6])
            data = CategoryChartData()
            data.categories = ["East", "West"]
            data.add_series("Revenue", (10, 20))
            slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(1),
                                   Inches(6), Inches(4), data)
            deck.save(folder / "source.pptx")
            baseline = json.loads(run_installed("forge.py", "preflight", "source.pptx", "--out", "baseline", "--json"))
            self.assertEqual(baseline["source"]["page_count"], 1)
            run_installed("translate_pptx.py", "extract", "source.pptx", "plan.json")
            plan_file = folder / "plan.json"
            plan = json.loads(plan_file.read_text(encoding="utf-8"))
            labels = [entry for entry in plan["entries"] if entry["source"] == "East"]
            self.assertEqual(len(labels), 1)
            labels[0]["target"] = "东区"
            plan_file.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
            run_installed("translate_pptx.py", "apply", "source.pptx", "plan.json", "edited.pptx")
            chart = Presentation(folder / "edited.pptx").slides[0].shapes[0].chart
            self.assertEqual(chart.plots[0].categories[0].label, "东区")
            report = json.loads(run_installed("forge.py", "verify-pptx", "edited.pptx",
                                              "--structural-only", "--out", "qa", "--json"))
            self.assertIn(("native-charts", "PASS"), [(c["check"], c["status"]) for c in report["checks"]])


if __name__ == "__main__":
    unittest.main()
