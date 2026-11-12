#!/usr/bin/env python3
"""Snapshot a source deck or verify a delivery and collect its evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path
from urllib.parse import quote

from _copy_review import flagged_phrases
from _pptx_common import AuditError, NS, _relationships, _rels_part, _root_for, _shown, q
from audit_pptx_structure import parse_slide_ranges


SCRIPTS = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def flags(name, values):
    return [arg for value in values for arg in (name, str(value))]


class Verification:
    def __init__(self, directory):
        self.directory = directory
        self.checks = []
        self.warnings = []

    def record(self, name, status, **details):
        self.checks.append(dict(check=name, status=status, **details))

    def run(self, name, script, args, *, structured=False, baseline=False):
        command = [sys.executable, "-B", str(SCRIPTS / script), *map(str, args)]
        if structured:
            command.append("--json")
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        payload = None
        if structured:
            try:
                payload = json.loads(result.stdout)
            except ValueError:
                pass
        evidence = name + (".json" if payload is not None else ".log")
        (self.directory / evidence).write_text(result.stdout, encoding="utf-8")
        details = dict(evidence=evidence, exit_code=result.returncode)
        if result.stderr:
            log = name + ".stderr.log"
            (self.directory / log).write_text(result.stderr, encoding="utf-8")
            details["stderr"] = log
        ok = result.returncode == 0 and (not structured or payload is not None)
        status = "PASS" if ok else "FAIL"
        if ok and isinstance(payload, dict) and payload.get("status") == "skipped":
            status = "SKIPPED"
            details["reason"] = payload.get("reason", "not applicable")
        if baseline and result.returncode == 1 and isinstance(payload, dict) and payload.get("slides", 0) > 0:
            status = "BASELINE_FINDINGS"
        self.record(name, status, **details)
        return payload if structured else ok

    def sheet(self, rows):
        images = self.directory / "contact-sheet.png"
        args = flags("--row", [f"{label}={path}" for label, path in rows])
        self.run("contact-sheet", "make_contact_sheet.py", [*args, "--output", images])


def html_page_count(path, digest, browser_executable):
    from playwright.sync_api import Error, sync_playwright
    import export_pdf

    # Use the exporter's local origin, viewport and startup interval. Relative
    # scripts can create slides after the HTML document itself has loaded.
    browser_path = export_pdf.resolve_browser_executable(browser_executable)
    server, port = export_pdf._start_server(path.parent)
    try:
        with sync_playwright() as runtime:
            browser = export_pdf.launch_chromium(runtime, browser_path)
            try:
                page = browser.new_page(viewport={"width": 1920, "height": 1080})
                errors = []
                data_types = {"script", "fetch", "xhr"}
                page.on("pageerror", lambda error: errors.append(f"JavaScript error: {error}"))
                page.on("requestfailed", lambda req: errors.append(f"failed {req.resource_type} request")
                        if req.resource_type in data_types else None)
                page.on("response", lambda res: errors.append(f"HTTP {res.status} for {res.request.resource_type}")
                        if res.status >= 400 and res.request.resource_type in data_types else None)
                url = f"http://127.0.0.1:{port}/{quote(path.name)}"
                response = page.goto(url, wait_until="networkidle")
                if not response or not response.ok or hashlib.sha256(response.body()).hexdigest() != digest:
                    raise AuditError("The HTML loaded by Chromium does not match the source SHA-256.")
                page.add_style_tag(content=export_pdf.EXPORT_CSS)
                page.wait_for_function("document.fonts.status === 'loaded'")
                page.wait_for_timeout(1200)
                if errors:
                    raise AuditError(f"HTML slide count could be incomplete: {errors[0]}")
                return page.locator(".slide").count()
            finally:
                browser.close()
    except Error as exc:
        raise AuditError(f"Cannot count HTML slides in Chromium: {exc}") from exc
    finally:
        server.shutdown()
        server.server_close()


def pptx_page_counts(path):
    from audit_pptx_typography import _ordered_slides

    part = "ppt/presentation.xml"
    with zipfile.ZipFile(path) as package:
        entries = Counter(package.namelist())
        names = set(entries)
        for required in (part, _rels_part(part)):
            if entries[required] != 1:
                raise AuditError(f"Expected one PPTX package part {required}.")
        presentation = _root_for(package, part, None)
        if presentation.tag != q("p", "presentation"):
            raise AuditError(f"Invalid PPTX presentation root in {part}.")
        relationship_ids = Counter(rel["id"] for rel in _relationships(package, part, names))
        for node in presentation.findall("./p:sldIdLst/p:sldId", NS):
            rel_id = node.get(q("r", "id"))
            if relationship_ids[rel_id] != 1:
                raise AuditError(f"Missing or ambiguous presentation slide relationship {rel_id!r}.")

        slides = _ordered_slides(package, names, presentation)
        order = [s["slide_id"] for s in slides]
        if "" in order or len(order) != len(set(order)):
            raise AuditError("Missing or duplicate stable PPTX slide IDs.")
        hidden = []
        for slide in slides:
            slide_part = slide["part"]
            if entries[slide_part] != 1:
                raise AuditError(f"Ambiguous PPTX slide part {slide_part}.")
            root = _root_for(package, slide_part, None)
            if root.tag != q("p", "sld"):
                raise AuditError(f"Invalid PPTX slide root in {slide_part}.")
            if not slide["shown_in_presentation"] or not _shown(root.get("show")):
                hidden.append(slide["page"])
    return dict(page_count=len(order), slide_order=order, visible_slide_count=len(order) - len(hidden),
                hidden_slide_count=len(hidden), hidden_pages=hidden)


def source_pages(path, source, directory, browser_executable):
    fmt = source["format"]
    if fmt == "html":
        return {"page_count": html_page_count(path, source["sha256"], browser_executable)}
    if fmt not in {"pdf", "pptx"}:
        raise AuditError(f"Page count unknown for unsupported source format {fmt!r}.")

    # Count an immutable copy of the exact bytes identified by the report. A
    # live Office file can be saved again while the environment check runs.
    with tempfile.TemporaryDirectory(dir=directory) as temp:
        snapshot = Path(temp) / ("source." + fmt)
        shutil.copyfile(path, snapshot)
        if sha256(snapshot) != source["sha256"]:
            raise AuditError("Source changed after its SHA-256 was recorded. Run preflight again.")
        if fmt == "pptx":
            return pptx_page_counts(snapshot)
        try:
            import pypdfium2 as pdfium
        except (ImportError, OSError) as exc:
            raise AuditError("Counting PDF pages requires python -m pip install pypdfium2.") from exc
        try:
            with pdfium.PdfDocument(snapshot) as document:
                return {"page_count": len(document)}
        except pdfium.PdfiumError as exc:
            raise AuditError(f"Cannot count PDF pages: {exc}") from exc


def preflight(args, qa, path, source):
    browser = ["--browser-executable", args.browser_executable] if args.browser_executable else []
    env_ok = qa.run("environment", "check_env.py", browser)
    try:
        if source["format"] == "html" and not env_ok:
            raise AuditError("HTML slide count unavailable because the environment check failed.")
        source.update(source_pages(path, source, qa.directory, args.browser_executable))
        if not source["page_count"]:
            raise AuditError("The source contains zero pages or slides.")
    except (AuditError, OSError, ValueError, KeyError, ImportError, SystemExit, zipfile.BadZipFile) as exc:
        qa.record("page-count", "FAIL", reason=str(exc))
    else:
        qa.record("page-count", "PASS")


def verify_html(args, qa):
    options = (flags("--require-font", args.require_font)
               + flags("--allow-offstage-text", args.allow_offstage_text)
               + flags("--allow-clipped-text", args.allow_clipped_text))
    browser = ["--browser-executable", args.browser_executable] if args.browser_executable else []
    if args.expect_slides is not None:
        options += ["--expect-slides", args.expect_slides]
    target_dir = qa.directory / "target"
    target = qa.run("html", "audit_html_slides.py", [args.target, "--render-dir", target_dir,
                    *browser, *options], structured=True)
    if not target or not target.get("slides"):
        return
    qa.warnings.extend(target.get("warnings", []))
    rows = [("target", target_dir)]
    if args.source:
        source_dir = qa.directory / "source"
        source = qa.run("source-html", "audit_html_slides.py", [args.source, "--render-dir",
                        source_dir, *browser], structured=True, baseline=True)
        if source and source.get("slides"):
            rows.insert(0, ("source", source_dir))
            before, after = source["slide_markup_sha256"], target["slide_markup_sha256"]
            changed = [page for page, pair in enumerate(zip(before, after), 1) if pair[0] != pair[1]]
            unexpected = sorted(set(changed) - args.pages)
            same_order_length = len(before) == len(after)
            ok = same_order_length and not unexpected and all(p <= len(after) for p in args.pages)
            qa.record("slide-markup", "PASS" if ok else "FAIL",
                      source_pages=len(before), target_pages=len(after), changed=changed,
                      outside_scope=unexpected)
            qa.run("pixels", "audit_rendered_pages.py", [source_dir, target_dir,
                   *flags("--allow-slides", args.allow_slides),
                   *flags("--allow-solid-slides", args.allow_solid_slides)], structured=True)
    qa.sheet(rows)


def native_copy(pptx, manifest):
    warnings = []
    drawing = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    with zipfile.ZipFile(pptx) as package:
        for slide in manifest["slides"]:
            page = ET.fromstring(package.read(slide["part"]))
            for para in page.iter(drawing + "p"):
                text = "".join(node.text or "" for node in para.iter(drawing + "t"))
                for phrase in flagged_phrases(text):
                    warnings.append(dict(slide=slide["page"], check="copy-review", detail=phrase))
    return warnings


def render(qa, name, path, engine, manifest):
    folder = qa.directory / name
    if not qa.run("render-" + name, "render_pptx.py", [path, folder, "--engine", engine, "--include-hidden"]):
        return None
    receipt = json.loads((folder / "render-manifest.json").read_text(encoding="utf-8-sig"))
    expected = {s["page"] for s in manifest["slides"]}
    rendered = {row["physical_index"] for row in receipt["rendered"]}
    verified = (expected == rendered and len(rendered) == len(receipt["rendered"])
                and receipt["source_sha256"].lower() == sha256(path)
                and (engine == "auto" or engine == receipt["engine"])
                and all((folder / f"slide-{p:03}.png").is_file() for p in expected))
    qa.record("render-coverage-" + name, "PASS" if verified else "FAIL",
              engine=receipt["engine"], pages=sorted(rendered))
    for warning in receipt.get("layout_warnings", []):
        qa.warnings.append(dict(deck=name, slide=warning["physical_index"], check=warning["code"],
                                detail=warning))
    return receipt["engine"] if verified else None


def verify_pptx(args, qa):
    audit = "audit_pptx_structure.py"
    target = qa.run("manifest", audit, ["manifest", args.target], structured=True)
    charts = qa.run("native-charts", "native_charts.py", ["audit", args.target], structured=True)
    if charts:
        qa.warnings.extend(charts.get("limitations", []))
    if not target or not target.get("integrity_ok"):
        return
    qa.warnings.extend(native_copy(args.target, target))
    source = None
    if args.source:
        source = qa.run("source-manifest", audit, ["manifest", args.source], structured=True)
        if not source or not source.get("integrity_ok"):
            return
        available = {slide["page"] for slide in source["slides"] + target["slides"]}
        if args.pages - available:
            qa.record("selected-pages", "FAIL", reason="Requested physical page does not exist.",
                      pages=sorted(args.pages - available))
            return
        # Scope rules already resolved by the property auditor include stable slide IDs.
        # Use that result for structural and visual checks when no page list was supplied.
        if args.scope or not args.pages:
            extra = ["--scope", args.scope] if args.scope else []
            prop = qa.run("properties", "audit_pptx_properties.py",
                          [args.source, args.target, *extra], structured=True)
            if args.scope and not args.pages and prop and "scope" in prop:
                ids = {sid for rule in prop["scope"]["rules"] for sid in rule["slide_ids"]}
                for slide in source["slides"] + target["slides"]:
                    if str(slide["slide_id"]) in ids:
                        args.pages.add(slide["page"])
        else:
            qa.record("properties", "NOT_REQUESTED", reason="Page-level scope supplied without a property allowlist.")
        options = flags("--allow-slides", sorted(args.pages))
        if args.target_language:
            options += ["--strict-translation", "--target-language", args.target_language]
        if args.translation_exceptions:
            options += ["--translation-exceptions", args.translation_exceptions]
        qa.run("structure", audit, ["compare", args.source, args.target, *options], structured=True)
        if args.backup_map:
            qa.run("backups", "audit_pptx_backups.py", [args.source, args.target,
                   *flags("--map", args.backup_map)], structured=True)
    if args.numbering:
        qa.run("page-numbers", "audit_pptx_page_numbers.py", [args.target, "--numbering", args.numbering])
    qa.run("typography", "audit_pptx_typography.py", [args.target, "--include-hidden",
           *flags("--expect", args.expect_font)], structured=True)
    if args.structural_only:
        qa.record("visual", "NOT_REQUESTED", reason="--structural-only")
        return
    engine = args.engine
    rows = []
    if source:
        engine = render(qa, "source", args.source, engine, source)
        if engine is None:
            return
        rows.append(("source", qa.directory / "source"))
    if not render(qa, "target", args.target, engine, target):
        return
    rows.append(("target", qa.directory / "target"))
    qa.sheet(rows)
    if source:
        common = [qa.directory / "source", qa.directory / "target"]
        qa.run("pixels", "audit_rendered_pages.py", [*common, *flags("--allow-slides", sorted(args.pages)),
               *flags("--allow-solid-slides", args.allow_solid_slides)], structured=True)
        if args.backup_map:
            qa.run("backup-pixels", "audit_rendered_pages.py", [*common,
                   *flags("--page-map", args.backup_map)], structured=True)


def parser():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    initial = sub.add_parser("preflight", help="record environment, source SHA-256 and page count")
    initial.add_argument("target", metavar="INPUT", type=Path)
    initial.add_argument("--out", type=Path, help="new evidence directory (default: a unique temp directory)")
    initial.add_argument("--json", action="store_true", help="print the summary JSON")
    initial.add_argument("--browser-executable", type=Path)
    initial.set_defaults(source=None, allow_slides=[])
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("target", type=Path)
    common.add_argument("--source", type=Path, help="original deck for scoped comparison")
    common.add_argument("--out", type=Path, help="new evidence directory (default: a unique temp directory)")
    common.add_argument("--allow-slides", action="append", default=[], metavar="RANGE",
                        help="physical pages allowed to change, e.g. 2-4,7")
    common.add_argument("--allow-solid-slides", action="append", default=[], metavar="RANGE",
                        help="allow an intentional solid/coverage change on these pages")
    common.add_argument("--json", action="store_true", help="print the summary JSON")
    html = sub.add_parser("verify-html", parents=[common], help="browser geometry, copy, renders and scope")
    html.add_argument("--expect-slides", type=int)
    html.add_argument("--browser-executable", type=Path)
    for flag in ("--require-font", "--allow-offstage-text", "--allow-clipped-text"):
        html.add_argument(flag, action="append", default=[])
    pptx = sub.add_parser("verify-pptx", parents=[common], help="native XML, rendered pages and scope")
    pptx.add_argument("--scope", type=Path, help="existing property-audit scope JSON")
    pptx.add_argument("--backup-map", action="append", default=[], metavar="SOURCE:TARGET")
    pptx.add_argument("--target-language", choices=("en", "zh"), help="strict translation audit")
    pptx.add_argument("--translation-exceptions", type=Path)
    pptx.add_argument("--numbering", choices=("physical", "visible", "none"))
    pptx.add_argument("--expect-font", action="append", default=[], metavar="ROLE=FONT,SIZE,BOLD")
    pptx.add_argument("--structural-only", action="store_true", help="explicitly omit native rendering")
    pptx.add_argument("--engine", choices=("auto", "powerpoint", "wps", "libreoffice"), default="auto")
    return ap


def main(argv=None):
    ap = parser()
    args = ap.parse_args(argv)
    compare_options = ("allow_slides", "allow_solid_slides", "scope", "backup_map",
                       "target_language", "translation_exceptions")
    if not args.source and any(getattr(args, key, None) for key in compare_options):
        ap.error("comparison options require --source")
    if getattr(args, "translation_exceptions", None) and not args.target_language:
        ap.error("--translation-exceptions requires --target-language")
    try:
        args.pages = set()
        for spec in args.allow_slides:
            args.pages.update(parse_slide_ranges(spec))
        is_preflight = args.command == "preflight"
        inputs = ([args.target.expanduser().absolute()] if is_preflight else
                  [p.resolve(strict=True) for p in (args.source, args.target) if p])
        if is_preflight and not inputs[0].is_file():
            raise ValueError(f"Preflight input must be an existing regular file: {inputs[0]}")
        before = {str(p): sha256(p) for p in inputs}
        if args.out:
            directory = args.out.absolute() if is_preflight else args.out.resolve()
            directory.mkdir(parents=True, exist_ok=False)
        else:
            prefix = "deck-forge-preflight-" if is_preflight else "deck-forge-verify-"
            directory = Path(tempfile.mkdtemp(prefix=prefix))
    except (OSError, AuditError, ValueError) as exc:
        ap.error(str(exc))
    qa = Verification(directory)
    source = None
    try:
        if is_preflight:
            path = inputs[0]
            fmt = path.suffix[1:].lower() or "unknown"
            source = dict(path=str(path), sha256=before[str(path)], format="html" if fmt == "htm" else fmt,
                          page_count=None)
            preflight(args, qa, path, source)
        elif args.command == "verify-html":
            verify_html(args, qa)
        else:
            verify_pptx(args, qa)
        qa.record("inputs-unchanged", "PASS" if all(sha256(p) == before[str(p)] for p in inputs) else "FAIL")
    except (OSError, ValueError, KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
        qa.record("verification", "FAIL", reason=str(exc))
    ok = all(item["status"] != "FAIL" for item in qa.checks)
    result = dict(status="PASS" if ok else "FAIL", command=args.command, directory=str(directory),
                  inputs=before, checks=qa.checks, warnings=qa.warnings)
    if source is not None:
        result["source"] = source
    text = json.dumps(result, indent=2, ensure_ascii=False)
    (directory / "report.json").write_text(text + "\n", encoding="utf-8")
    if args.json:
        print(text)
    else:
        if source is not None:
            pages = source["page_count"] if source["page_count"] is not None else "unknown"
            print(f"{source['path']} | pages: {pages} | SHA-256: {source['sha256']}")
        for item in qa.checks:
            print(item["status"], item["check"], item.get("reason", ""))
        for warning in qa.warnings:
            message = f"REVIEW {json.dumps(warning, ensure_ascii=False)}"
            print(f"\x1b[31m{message}\x1b[0m" if sys.stdout.isatty() else message)
        print(f"{result['status']} | {directory / 'report.json'}")
    return 0 if ok else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    raise SystemExit(main())
