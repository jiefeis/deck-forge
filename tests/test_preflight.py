"""Exercise the preflight CLI, its evidence and its source-concurrency checks."""

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from unittest.mock import patch

from PIL import Image
from pptx import Presentation


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import forge


class PreflightTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def pptx(self):
        path = self.root / "原稿.pptx"
        deck = Presentation()
        slides = [deck.slides.add_slide(deck.slide_layouts[6]) for _ in range(4)]
        ids = [s.slide_id for s in slides]
        order = deck.slides._sldIdLst
        order.remove(order[1])  # orphan slide2.xml stays in the archive
        order.insert(0, order[-1])
        slides[3]._element.set("show", "0")
        order[-1].set("show", "false")
        deck.save(path)
        return path, [ids[3], ids[0], ids[2]]

    def invoke(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(ROOT / "scripts/forge.py"), "preflight", *map(str, args), "--json"],
            cwd=self.root, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            capture_output=True, text=True, encoding="utf-8", timeout=90,
        )

    def report(self, code, output, expected_code):
        self.assertEqual(code, expected_code, output)
        data = json.loads(output)
        saved = Path(data["directory"]) / "report.json"
        self.assertEqual(data, json.loads(saved.read_text(encoding="utf-8")))
        self.assertEqual(data["status"], "PASS" if code == 0 else "FAIL")
        return data, {c["check"]: c for c in data["checks"]}

    @staticmethod
    def environment_ok(qa, name, script, args):
        qa.record(name, "PASS")
        return True

    def in_process(self, source, output, *args, expected=1):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = forge.main(["preflight", str(source), "--out", str(self.root / output), "--json", *args])
        return self.report(rc, stdout.getvalue(), expected)

    def test_real_pptx_environment_order_and_hidden_pages(self):
        path, order = self.pptx()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        run = self.invoke(path, "--out", "evidence")
        result, checks = self.report(run.returncode, run.stdout, 0)
        self.assertEqual(result["source"], {
            "path": str(path), "format": "pptx", "sha256": digest, "page_count": 3,
            "slide_order": order, "visible_slide_count": 1, "hidden_slide_count": 2, "hidden_pages": [1, 3],
        })
        self.assertEqual(result["inputs"], {str(path): digest})
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
        env = checks["environment"]
        self.assertEqual((env["status"], env["exit_code"]), ("PASS", 0))
        log = (Path(result["directory"]) / env["evidence"]).read_text(encoding="utf-8")
        self.assertIn(sys.executable, log)
        self.assertIn("environment OK", log)
        self.assertEqual(checks["inputs-unchanged"]["status"], "PASS")

    def test_rendered_html_includes_relative_script_and_ignores_template(self):
        path = self.root / "HTML deck 中文.HTM"
        path.write_text('<div class="slide"></div><template><div class="slide"></div></template>'
                        '<div class="slide-notes"></div><script src="slides.js"></script>', encoding="utf-8")
        (self.root / "slides.js").write_text(
            'setTimeout(() => document.body.insertAdjacentHTML("beforeend", '
            '\' <article class="slide second"></article>\'), 250);', encoding="utf-8")
        run = self.invoke(path, "--out", "html")
        result, checks = self.report(run.returncode, run.stdout, 0)
        self.assertEqual(result["source"]["format"], "html")
        self.assertEqual(result["source"]["page_count"], 2)
        self.assertEqual(result["source"]["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(checks["page-count"]["status"], "PASS")
        (self.root / "slides.js").unlink()
        broken = self.invoke(path, "--out", "missing-script")
        result, checks = self.report(broken.returncode, broken.stdout, 1)
        self.assertIsNone(result["source"]["page_count"])
        self.assertIn("HTTP 404", checks["page-count"]["reason"])

    def test_browser_option_reaches_both_environment_and_html_count(self):
        path = self.root / "deck.html"
        path.write_text('<section class="slide"></section>', encoding="utf-8")
        browser = self.root / "my-browser"
        with patch.object(forge.Verification, "run", autospec=True, return_value=True) as env, \
                patch.object(forge, "html_page_count", return_value=1) as count:
            result, _ = self.in_process(path, "explicit-browser", "--browser-executable", str(browser), expected=0)
        self.assertEqual(env.call_args.args[1:], ("environment", "check_env.py", ["--browser-executable", browser]))
        count.assert_called_once_with(path, result["source"]["sha256"], browser)

    def test_actual_environment_failure_is_retained_with_status_and_diagnostics(self):
        path, _ = self.pptx()
        run = self.invoke(path, "--browser-executable", self.root / "absent-browser", "--out", "failure")
        result, checks = self.report(run.returncode, run.stdout, 1)
        env = checks["environment"]
        self.assertEqual(env["status"], "FAIL")
        self.assertNotEqual(env["exit_code"], 0)
        self.assertTrue((self.root / "failure" / env["evidence"]).is_file())
        self.assertIn("absent-browser", (self.root / "failure" / env["stderr"]).read_text(encoding="utf-8"))
        self.assertEqual(result["source"]["page_count"], 3)

    def test_pdf_counts_real_pages_and_handles_missing_optional_reader(self):
        path = self.root / "slides.pdf"
        with Image.new("RGB", (10, 10), "white") as first, Image.new("RGB", (12, 12), "blue") as second:
            first.save(path, "PDF", save_all=True, append_images=[second])
        with patch.object(forge.Verification, "run", self.environment_ok):
            if importlib.util.find_spec("pypdfium2") is not None:
                result, _ = self.in_process(path, "pdf", expected=0)
                self.assertEqual(result["source"]["page_count"], 2)
            with patch.dict(sys.modules, {"pypdfium2": None}):
                result, checks = self.in_process(path, "missing-pdf-reader")
            self.assertIsNone(result["source"]["page_count"])
            self.assertIn("pypdfium2", checks["page-count"]["reason"])

    def test_pptx_count_checks_referenced_slide_graph_only(self):
        path, order = self.pptx()
        partial = self.root / "partial.pptx"
        ambiguous = self.root / "ambiguous.pptx"
        rels = "ppt/_rels/presentation.xml.rels"
        with zipfile.ZipFile(path) as source, zipfile.ZipFile(partial, "w") as good, \
                zipfile.ZipFile(ambiguous, "w") as bad:
            for part in source.namelist():
                if part not in (rels, "ppt/presentation.xml") and not part.startswith("ppt/slides/slide"):
                    continue
                data = source.read(part)
                good.writestr(part, data)
                if part == rels:
                    tree = ET.fromstring(data)
                    slide_rel = next(node for node in tree if node.get("Type", "").endswith("/slide"))
                    tree.append(slide_rel)
                    data = ET.tostring(tree)
                bad.writestr(part, data)
        with patch.object(forge.Verification, "run", self.environment_ok):
            result, _ = self.in_process(partial, "counted", expected=0)
            self.assertEqual(result["source"]["slide_order"], order)
            result, checks = self.in_process(ambiguous, "ambiguous")
            self.assertIsNone(result["source"]["page_count"])
            self.assertIn("ambiguous", checks["page-count"]["reason"])

    def test_invalid_formats_do_not_acquire_counts(self):
        with patch.object(forge.Verification, "run", self.environment_ok):
            for filename, content in (("notes.txt", b"page 1\npage 2"), ("broken.pptx", b"not a ZIP"),
                                      ("broken.pdf", b"0 pages")):
                with self.subTest(filename=filename):
                    path = self.root / filename
                    path.write_bytes(content)
                    result, checks = self.in_process(path, path.stem + path.suffix[1:])
                    self.assertEqual(result["source"]["sha256"], hashlib.sha256(content).hexdigest())
                    self.assertIsNone(result["source"]["page_count"])
                    self.assertEqual(checks["page-count"]["status"], "FAIL")
                    if path.suffix == ".txt":
                        self.assertIn("unsupported", checks["page-count"]["reason"])

    def test_missing_input_existing_evidence_and_source_as_output(self):
        path, _ = self.pptx()
        before = path.read_bytes()
        folder = self.root / "qa"
        folder.mkdir()
        sentinel = folder / "report.json"
        sentinel.write_bytes(b"preserve prior evidence")
        for source, out in ((path, folder), (path, path), (self.root / "missing.pptx", self.root / "new"),
                            (self.root, self.root / "new")):
            with self.subTest(source=source, out=out):
                self.assertEqual(self.invoke(source, "--out", out).returncode, 2)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(sentinel.read_bytes(), b"preserve prior evidence")
        self.assertFalse((self.root / "new").exists())

    def test_save_during_native_count_cannot_mix_snapshot_or_win_an_overwrite(self):
        path, _ = self.pptx()
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        current = Presentation()
        current.slides.add_slide(current.slide_layouts[6])
        original_count = forge.pptx_page_counts

        def save_while_counting(frozen):
            self.assertNotEqual(path, frozen)
            current.save(path)
            return original_count(frozen)

        with patch.object(forge.Verification, "run", self.environment_ok), \
                patch.object(forge, "pptx_page_counts", side_effect=save_while_counting):
            result, checks = self.in_process(path, "stale")
        self.assertEqual(result["source"]["sha256"], before)
        self.assertEqual(result["source"]["page_count"], 3)
        self.assertEqual(checks["inputs-unchanged"]["status"], "FAIL")
        self.assertEqual(len(Presentation(path).slides), 1)


if __name__ == "__main__":
    unittest.main()
