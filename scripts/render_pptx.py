#!/usr/bin/env python3
"""Render a native PPTX to physical-page PNGs and a same-engine QA receipt."""

from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from audit_pptx_structure import build_manifest


MANIFEST = "render-manifest.json"
ENGINES = ("auto", "powerpoint", "wps", "libreoffice")
TEXT_TOLERANCE_PT = 1.0


class RenderError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def find_libreoffice() -> str | None:
    names = ("soffice.com", "soffice", "libreoffice") if os.name == "nt" else (
        "soffice", "libreoffice",
    )
    for name in names:
        executable = shutil.which(name)
        if executable:
            return executable
    candidates = []
    if sys.platform == "darwin":
        bundle = Path("LibreOffice.app/Contents/MacOS/soffice")
        candidates = [Path("/Applications") / bundle, Path.home() / "Applications" / bundle]
    elif os.name == "nt":
        candidates = [
            Path(os.environ[key]) / "LibreOffice" / "program" / "soffice.com"
            for key in ("ProgramFiles", "ProgramFiles(x86)") if os.environ.get(key)
        ]
    return next((str(path) for path in candidates if path.is_file()), None)


def run_engine(command: list[str], name: str, work: Path) -> str:
    result = subprocess.run(
        command, cwd=work, capture_output=True, text=True, errors="replace",
        env={**os.environ, "TEMP": str(work), "TMP": str(work), "TMPDIR": str(work)},
    )
    detail = (result.stdout + result.stderr).strip()
    if result.returncode:
        raise RenderError(f"{name} failed (exit {result.returncode}): {detail}")
    return detail


def pdf_text_bounds(page, index: int) -> tuple[int, list[dict]]:
    """Check extractable glyph ink against the crop box, in PDF points."""
    page_left, page_bottom, page_right, page_top = page.get_bbox()
    excess = {"left": 0.0, "bottom": 0.0, "right": 0.0, "top": 0.0}
    measured = outside = 0
    with closing(page.get_textpage()) as text:
        for character in range(text.count_chars()):
            left, bottom, right, top = text.get_charbox(character)
            if right <= left or top <= bottom:
                continue
            measured += 1
            amounts = (page_left - left, page_bottom - bottom, right - page_right, top - page_top)
            if max(amounts) > TEXT_TOLERANCE_PT:
                outside += 1
                for side, amount in zip(excess, amounts):
                    excess[side] = max(excess[side], amount)
    if not outside:
        return measured, []
    return measured, [{
        "physical_index": index, "code": "text-outside-slide",
        "measurement": "pdf-glyph-bounds", "glyph_count": outside,
        "overflow_pt": {side: round(value, 2) for side, value in excess.items()
                        if value > TEXT_TOLERANCE_PT},
    }]


def render_libreoffice(source: Path, stage: Path, rows: list[dict], slide_count: int,
                       size: tuple[int, int]) -> tuple[str, dict, list[dict]]:
    executable = find_libreoffice()
    if not executable:
        raise RenderError("LibreOffice Impress is required. Install LibreOffice and make soffice available.")
    try:
        import pypdfium2 as pdfium
        from PIL import Image
    except ImportError as exc:
        raise RenderError("LibreOffice rendering requires python -m pip install pypdfium2 Pillow") from exc

    work = source.parent
    # Always export the full deck. PDF ordinal i then means PPTX physical i,
    # even for a hidden middle slide or a deck with no visible slides.
    options = {
        "ExportHiddenSlides": {"type": "boolean", "value": "true"},
        "UseLosslessCompression": {"type": "boolean", "value": "true"},
    }
    detail = run_engine([
        executable, "-env:UserInstallation=" + (work / "lo-profile").as_uri(),
        "--headless", "--nologo", "--norestore", "--convert-to",
        "pdf:impress_pdf_Export:" + json.dumps(options, separators=(",", ":")),
        "--outdir", str(work), str(source),
    ], "LibreOffice", work)
    pdf = source.with_suffix(".pdf")
    if not pdf.is_file():
        raise RenderError(f"LibreOffice did not produce a PDF: {detail}")
    warnings = []
    unavailable = []
    measured = 0
    with pdfium.PdfDocument(pdf) as doc:
        if len(doc) != slide_count:
            raise RenderError(f"LibreOffice exported {len(doc)} PDF pages for {slide_count} physical slides. "
                              "Verify Impress supports the ExportHiddenSlides PDF option.")
        for row in rows:
            index = row["physical_index"]
            with closing(doc[index - 1]) as page:
                try:
                    count, page_warnings = pdf_text_bounds(page, index)
                except pdfium.PdfiumError:
                    unavailable.append(index)
                else:
                    measured += count
                    warnings.extend(page_warnings)
                page_width, page_height = page.get_size()
                scale = min(size[0] / page_width, size[1] / page_height)
                with closing(page.render(scale=scale)) as bitmap, bitmap.to_pil() as pixels:
                    path = stage / row["file"]
                    if pixels.size == size:
                        pixels.save(path, "PNG")
                    else:
                        with pixels.resize(size, Image.Resampling.LANCZOS) as resized:
                            resized.save(path, "PNG")
    measurement = {
        "method": "pdf-glyph-bounds", "measured_glyphs": measured,
        "unavailable_physical_indices": unavailable, "tolerance_pt": TEXT_TOLERANCE_PT,
        "scope": "Extractable PDF glyphs on rendered slides. Clipped or rasterized text may be absent.",
    }
    return "libreoffice", measurement, warnings


def render_com(source: Path, stage: Path, engine: str, width: int, height: int | None,
               include_hidden: bool, rows: list[dict], slide_count: int) -> tuple[str, dict, list[dict]]:
    if os.name != "nt":
        raise RenderError(f"{engine} requires Windows. Use --engine libreoffice on this platform.")
    powershell = shutil.which("powershell.exe")
    if not powershell:
        raise RenderError("Windows PowerShell is required for PowerPoint/WPS rendering.")
    command = [
        powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", str(Path(__file__).with_suffix(".ps1").resolve()), "-InputPptx", str(source),
        "-OutputDir", str(stage), "-Engine", engine, "-Width", str(width),
    ]
    if height is not None:
        command.extend(["-Height", str(height)])
    if include_hidden:
        command.append("-IncludeHidden")
    run_engine(command, "PowerPoint/WPS", source.parent)
    receipt = json.loads((stage / MANIFEST).read_text(encoding="utf-8-sig"))
    actual = receipt["engine"]
    if actual not in ("powerpoint", "wps") or engine not in ("auto", actual):
        raise RenderError(f"COM reported unexpected engine {actual!r} for request {engine!r}")
    if receipt["slide_count"] != slide_count or receipt["rendered"] != rows:
        raise RenderError("COM page order/visibility disagrees with the source PPTX.")
    return actual, receipt["text_bounds"], receipt["layout_warnings"]


def check_destination(output: Path) -> None:
    if output.exists():
        if not output.is_dir():
            raise RenderError(f"Output is not a directory: {output}")
        if (output / MANIFEST).exists() or any(output.glob("slide-*.png")):
            raise RenderError(f"Output already contains a render. Use a fresh directory: {output}")


def publish(stage: Path, output: Path, rows: list[dict]) -> None:
    # A new directory can be published in one rename on the destination volume.
    # Existing directories may contain unrelated files. Exclusively create each
    # result there and publish the receipt last, rolling back this run on failure.
    check_destination(output)
    if not output.exists():
        stage.rename(output)
        return
    created = []
    try:
        for name in [row["file"] for row in rows] + [MANIFEST]:
            path = output / name
            with (stage / name).open("rb") as src, path.open("xb") as dst:
                created.append(path)
                shutil.copyfileobj(src, dst)
    except BaseException:
        for path in created:
            path.unlink()
        raise


def render_pptx(input_path: Path, output: Path, *, engine: str = "auto", width: int = 1920,
                height: int | None = None, include_hidden: bool = False) -> dict:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RenderError("PNG verification requires python -m pip install Pillow") from exc

    source = input_path.expanduser().resolve()
    output = output.expanduser().resolve()
    if source.suffix.lower() != ".pptx" or not source.is_file():
        raise RenderError(f"Expected an existing .pptx file: {source}")
    if (engine not in ENGINES or not 320 <= width <= 7680
            or (height is not None and not 180 <= height <= 4320)):
        raise RenderError("Use a supported engine, width 320..7680 and explicit height 180..4320.")
    check_destination(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".deckforge-render-", dir=output.parent) as temp:
        work = Path(temp)
        scratch = work / "input.pptx"
        shutil.copyfile(source, scratch)
        deck = build_manifest(scratch)
        ambiguous = {"duplicate-zip-entry", "duplicate-slide-relationship-id", "duplicate-stable-slide-id"}
        if (not deck["slide_count"] or any(s["integrity_incomplete"] for s in deck["slides"])
                or any(w["code"] in ambiguous for w in deck["integrity_warnings"])):
            raise RenderError("Cannot resolve every physical slide in the presentation order.")
        size_emu = deck["slide_size"]
        if min(size_emu.values()) <= 0:
            raise RenderError("Invalid slide dimensions in PPTX.")
        render_height = height if height is not None else max(1, round(width * size_emu["cy"] / size_emu["cx"]))
        size = (width, render_height)
        rows = [
            {"physical_index": slide["page"], "hidden": slide["hidden"],
             "file": f"slide-{slide['page']:03d}.png"}
            for slide in deck["slides"] if include_hidden or not slide["hidden"]
        ]
        stage = work / "images"
        stage.mkdir()
        if engine == "libreoffice" or (engine == "auto" and os.name != "nt"):
            actual, measurement, warnings = render_libreoffice(scratch, stage, rows, deck["slide_count"], size)
        else:
            actual, measurement, warnings = render_com(
                scratch, stage, engine, width, height, include_hidden, rows, deck["slide_count"],
            )
        if {p.name for p in stage.iterdir() if p.name != MANIFEST} != {row["file"] for row in rows}:
            raise RenderError("Exported page files disagree with the physical slide list.")
        for row in rows:
            path = stage / row["file"]
            with Image.open(path) as image:
                if image.format != "PNG" or image.size != size:
                    raise RenderError(f"Unexpected format or dimensions in {path.name}: {image.format} {image.size}")
                image.verify()
            with Image.open(path) as image:
                image.load()
        source_hash = sha256(source)
        if source_hash != deck["package_fingerprint"]:
            raise RenderError("Source changed during rendering.")
        receipt = {
            "source": str(source), "source_sha256": source_hash, "engine": actual,
            "width": size[0], "height": size[1], "include_hidden": include_hidden,
            "slide_count": deck["slide_count"],
            "hidden_physical_indices": [s["page"] for s in deck["slides"] if s["hidden"]],
            "rendered": rows, "text_bounds": measurement, "layout_warnings": warnings,
        }
        (stage / MANIFEST).write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        publish(stage, output, rows)
        return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--engine", choices=ENGINES, default="auto",
                        help="auto selects PowerPoint/WPS on Windows and LibreOffice elsewhere")
    parser.add_argument("--width", type=int, default=1920, help="output width, default 1920")
    parser.add_argument("--height", type=int, help="output height, default derived from slide aspect ratio")
    parser.add_argument("--include-hidden", action="store_true")
    args = parser.parse_args()
    try:
        receipt = render_pptx(args.input, args.output, engine=args.engine, width=args.width,
                              height=args.height, include_hidden=args.include_hidden)
    except (OSError, ImportError, ValueError, RuntimeError) as exc:
        print(f"render_pptx: {exc}", file=sys.stderr)
        return 1
    print(f"Rendered {len(receipt['rendered'])} slide(s) with {receipt['engine']} -> {args.output / MANIFEST}")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    raise SystemExit(main())
