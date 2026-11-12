#!/usr/bin/env python3
"""Physical-page, PNG and failure-path checks for the native renderer."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches, Pt


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import render_pptx as renderer


COLORS = [(32, 100, 160), (196, 75, 46), (57, 142, 74)]


def build_fixture(path: Path) -> None:
    presentation = Presentation()
    presentation.slide_width = Inches(10)
    presentation.slide_height = Inches(7.5)
    # Part filenames are created in a different order from the slide show.
    for index in (1, 2, 0):
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        fill = slide.background.fill
        fill.solid()
        fill.fore_color.rgb = RGBColor(*COLORS[index])
        marker = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.5), Inches(1), Inches(2), Inches(1.5))
        marker.fill.solid()
        marker.fill.fore_color.rgb = RGBColor(255, 255, 255)
        if index == 1:
            slide._element.set("show", "0")
        if index == 0:
            frame = slide.shapes.add_textbox(Inches(9.4), Inches(0.2), Inches(3), Inches(1)).text_frame
            frame.word_wrap = False
            frame.text = "Overflow at right"
            frame.paragraphs[0].runs[0].font.size = Pt(28)
    order = presentation.slides._sldIdLst
    order.insert(0, order[-1])
    presentation.save(path)


def colored_pdf(colors: list[tuple[int, int, int]]) -> bytes:
    """A small vector PDF with known pixel colors and partially off-page text."""
    ids = [4 + 2 * i for i in range(len(colors))]
    kids = " ".join(f"{i} 0 R" for i in ids)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(ids)} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for number, color in zip(ids, colors):
        objects.append((
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 300] /Contents {number + 1} 0 R "
            "/Resources << /Font << /F1 3 0 R >> >> >>"
        ).encode())
        rgb = " ".join(f"{channel/255:.6f}" for channel in color)
        content = f"{rgb} rg 0 0 400 300 re f".encode()
        if number == ids[0]:
            content += b" BT 0 g /F1 32 Tf 391 240 Td (WIDE) Tj ET"
        objects.append(f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream")
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, obj in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(pdf)


class CrossPlatformRendering(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="deckforge-native-render-test-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "source with spaces.pptx"
        build_fixture(self.source)
        self.digest = hashlib.sha256(self.source.read_bytes()).hexdigest()

    def assert_pages(self, output: Path, include_hidden: bool) -> dict:
        receipt = json.loads((output / renderer.MANIFEST).read_text(encoding="utf-8-sig"))
        self.assertEqual(receipt["source"], str(self.source.resolve()))
        self.assertEqual(receipt["source_sha256"].lower(), self.digest)
        self.assertEqual(receipt["slide_count"], 3)
        self.assertEqual(receipt["hidden_physical_indices"], [2])
        self.assertEqual(receipt["include_hidden"], include_hidden)
        self.assertEqual((receipt["width"], receipt["height"]), (400, 300))
        physical = [1, 2, 3] if include_hidden else [1, 3]
        expected = [{"physical_index": i, "hidden": i == 2, "file": f"slide-{i:03}.png"} for i in physical]
        self.assertEqual(receipt["rendered"], expected)
        self.assertEqual(sorted(p.name for p in output.glob("*.png")), [r["file"] for r in expected])
        for row in expected:
            with Image.open(output / row["file"]) as image:
                self.assertEqual((image.format, image.size), ("PNG", (400, 300)))
                pixel = image.convert("RGB").getpixel((200, 150))
                color = COLORS[row["physical_index"] - 1]
                self.assertLessEqual(max(abs(a - b) for a, b in zip(pixel, color)), 3, row["file"])
        self.assertEqual(self.digest, hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertEqual(list(self.root.glob(".deckforge-render-*")), [])
        return receipt

    def exercise_real_engines(self, first_engine: str, allow_missing_com: bool = False) -> str:
        engine = first_engine
        for include_hidden in (False, True):
            output = self.root / ("all" if include_hidden else "visible")
            args = [sys.executable, "-B", str(SCRIPTS / "render_pptx.py"), str(self.source),
                    str(output), "--engine", engine, "--width", "400"]
            if include_hidden:
                args.extend(["--include-hidden", "--height", "300"])
            result = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=180)
            detail = result.stdout + result.stderr
            if allow_missing_com and not include_hidden and result.returncode and "No supported presentation engine" in detail:
                self.skipTest("PowerPoint/WPS COM engine is not registered")
            self.assertEqual(result.returncode, 0, detail)
            receipt = self.assert_pages(output, include_hidden)
            self.assertIn(receipt["engine"], result.stdout)
            if engine != "auto":
                self.assertEqual(receipt["engine"], engine)
            engine = receipt["engine"]  # Pin the second render to the first actual provider.
            if engine == "powerpoint":
                self.assertGreater(receipt["text_bounds"]["measured_text_ranges"], 0)
                self.assertTrue(any(w["physical_index"] == 1 and "right" in w["overflow_pt"]
                                    for w in receipt["layout_warnings"]))
        return engine

    def test_linux_ci_real_libreoffice_and_pdfium(self) -> None:
        required = os.environ.get("DECK_FORGE_REQUIRE_LIBREOFFICE") == "1"
        if not renderer.find_libreoffice() or importlib.util.find_spec("pypdfium2") is None:
            if required:
                self.fail("Linux CI must install LibreOffice Impress and pypdfium2 for native rendering")
            self.skipTest("LibreOffice or pypdfium2 is unavailable")
        first_engine = "libreoffice" if os.name == "nt" else "auto"
        self.assertEqual(self.exercise_real_engines(first_engine), "libreoffice")
        self.exercise_public_verifier(first_engine)

    def exercise_public_verifier(self, engine: str) -> None:
        target = self.root / "candidate.pptx"
        shutil.copyfile(self.source, target)
        output = self.root / "qa"
        run = subprocess.run(
            [sys.executable, "-B", str(SCRIPTS / "forge.py"), "verify-pptx", str(target),
             "--source", str(self.source), "--engine", engine, "--out", str(output), "--json"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
        )
        self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
        report = json.loads(run.stdout)
        checks = {item["check"]: item for item in report["checks"]}
        for name in ("render-coverage-source", "render-coverage-target"):
            self.assertEqual(checks[name]["status"], "PASS")
            self.assertEqual(checks[name]["pages"], [1, 2, 3])
        self.assertEqual(checks["render-coverage-source"]["engine"], checks["render-coverage-target"]["engine"])
        self.assertEqual(checks["pixels"]["status"], "PASS")
        self.assertEqual(checks["contact-sheet"]["status"], "PASS")
        self.assertEqual(checks["inputs-unchanged"]["status"], "PASS")
        self.assertTrue((output / "contact-sheet.png").is_file())

    @unittest.skipUnless(os.name == "nt" and shutil.which("powershell.exe"), "COM requires Windows")
    def test_real_windows_com_wrapper(self) -> None:
        self.assertIn(self.exercise_real_engines("auto", allow_missing_com=True), ("powerpoint", "wps"))

    @unittest.skipUnless(importlib.util.find_spec("pypdfium2"), "requires optional pypdfium2")
    def test_pdfium_mapping_bounds_and_short_export(self) -> None:
        exported_colors = COLORS.copy()

        def convert(command: list[str], name: str, work: Path) -> str:
            self.assertEqual(name, "LibreOffice")
            self.assertIn("-env:UserInstallation=" + (work / "lo-profile").as_uri(), command)
            self.assertIn('"ExportHiddenSlides":{"type":"boolean","value":"true"}', command[command.index("--convert-to")+1])
            scratch = Path(command[-1])
            self.assertNotEqual(scratch, self.source)
            self.assertEqual(scratch.read_bytes(), self.source.read_bytes())
            scratch.with_suffix(".pdf").write_bytes(colored_pdf(exported_colors))
            return ""

        with patch.object(renderer, "find_libreoffice", return_value="soffice"), patch.object(renderer, "run_engine", convert):
            output = self.root / "render"
            renderer.render_pptx(self.source, output, engine="libreoffice", width=400)
            receipt = self.assert_pages(output, False)
            warnings = receipt["layout_warnings"]
            self.assertEqual([w["physical_index"] for w in warnings], [1])
            self.assertGreater(warnings[0]["overflow_pt"]["right"], 1.0)
            self.assertGreater(receipt["text_bounds"]["measured_glyphs"], 0)
            resized = self.root / "resized"
            renderer.render_pptx(self.source, resized, engine="libreoffice", width=400, height=180)
            with Image.open(resized / "slide-003.png") as image:
                self.assertEqual(image.size, (400, 180))
            exported_colors.pop()
            with self.assertRaisesRegex(renderer.RenderError, "2 PDF pages for 3 physical slides"):
                renderer.render_pptx(self.source, self.root / "short", engine="libreoffice", width=400)
            self.assertFalse((self.root / "short").exists())
            self.assertEqual(list(self.root.glob(".deckforge-render-*")), [])

    def test_existing_assets_and_source_change_do_not_publish(self) -> None:
        output = self.root / "existing"
        output.mkdir()
        (output / "note.txt").write_text("keep", encoding="utf-8")
        guarded = output / "slide-001.png"
        guarded.write_bytes(b"existing")
        with self.assertRaisesRegex(renderer.RenderError, "already contains"):
            renderer.render_pptx(self.source, output, engine="libreoffice")
        self.assertEqual(guarded.read_bytes(), b"existing")
        guarded.unlink()

        def change_source(scratch, stage, rows, count, size):
            for row in rows:
                with Image.new("RGB", size) as image:
                    image.save(stage / row["file"])
            with self.source.open("ab") as live:
                live.write(b"external edit during render")
            return "libreoffice", {}, []

        with patch.object(renderer, "render_libreoffice", change_source):
            with self.assertRaisesRegex(renderer.RenderError, "Source changed"):
                renderer.render_pptx(self.source, output, engine="libreoffice", width=400)
        self.assertEqual([p.name for p in output.iterdir()], ["note.txt"])
        self.assertEqual(list(self.root.glob(".deckforge-render-*")), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
