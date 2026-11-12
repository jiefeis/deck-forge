"""Smoke-test the actual committed runtime ZIP, without the source checkout on sys.path."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]


class PackageTests(unittest.TestCase):
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
                ["native_charts.py", "inspect", "--help"], ["render_pptx.py", "--help"],
                ["forge.py", "verify-html", "--help"], ["forge.py", "verify-pptx", "--help"],
            ]:
                with self.subTest(arguments=arguments):
                    script, *args = arguments
                    subprocess.run([sys.executable, "-B", str(installed / "scripts" / script), *args],
                                   cwd=folder, stdout=subprocess.DEVNULL, env=env, check=True)


if __name__ == "__main__":
    unittest.main()
