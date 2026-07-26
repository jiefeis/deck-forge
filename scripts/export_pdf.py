#!/usr/bin/env python3
"""
export_pdf.py - Export a deck-forge HTML presentation to a crisp, screenshot PDF.

Windows-friendly Python port of frontend-slides' bash exporter, hardened for
fidelity AND generality (it should not depend on a specific deck's internals):

  - Crisp: renders each slide at a 2x device scale (default) -> supersampled,
    sharp text, and embeds the PNGs LOSSLESSLY with img2pdf (FlateDecode). The
    old Pillow path JPEG-compressed every page (DCTDecode), which mushed text.
  - No chrome leaks: before capture it injects a stylesheet that (a) normalizes
    the `.deck-stage` to a native 1:1 position (transform/offset removed) so the
    clip is always exactly the 1920x1080 stage, and (b) HIDES presentation chrome
    (control bars, progress bars, nav, edit toggles, anything marked
    data-export-hide / .no-export / .no-print) so it never screenshots into PDF.
  - Mechanism-agnostic activation: to show one slide it calls the deck's own
    controller if present (goToSlide/goTo/showSlide/show/select), toggles every
    common "active" class, and clears leftover inline display so a deck's own
    `.slide.active{display:...}` rule wins - covering class-, controller-,
    visibility-, and display-based decks.

Resource-safe: the temp screenshot dir and the browser are always cleaned up
(finally blocks), and the served URL is percent-encoded so filenames with
spaces / CJK / # / ? work.

Fail-closed on degraded rendering: a failed font/stylesheet/image/script
request or an errored FontFace means the capture would silently use fallback
fonts or missing assets, so the export aborts by default
(--ignore-resource-errors downgrades this to a warning). --require-font
asserts a specific family actually resolved before anything is captured.

Usage:
    python export_pdf.py <input.html> [output.pdf] [--scale N] [--compact]
                         [--browser-executable PATH] [--require-font FAMILY]... [--keep-pngs DIR]
                         [--ignore-resource-errors]
      --scale N       device scale factor (default 2; sharper + bigger file)
      --compact       shortcut for --scale 1 (about half the size, still lossless)
      --browser-executable PATH
                      use an existing Chromium/Chrome executable when the
                      installed Playwright package expects a different cache
                      revision
      --require-font  assert this font family resolved (repeatable)
      --keep-pngs DIR also save the per-slide PNGs (slide-NNN.png) into DIR for
                      v1/v2 comparison via make_contact_sheet.py /
                      audit_rendered_pages.py
      --ignore-resource-errors  report font/asset failures but export anyway

Requires: pip install playwright img2pdf  +  python -m playwright install chromium
"""
from __future__ import annotations

import argparse
import http.server
import os
import shutil
import socketserver
import sys
import tempfile
import threading
from pathlib import Path
from urllib.parse import quote

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("export_pdf: Playwright required. Run: pip install playwright "
             "&& python -m playwright install chromium")

try:
    import img2pdf
except ImportError:
    sys.exit("export_pdf: img2pdf required (lossless PDF embedding). "
             "Run: pip install img2pdf")

# Injected before any capture: pin the stage to native 1:1 and hide chrome.
# The hide list below is a contract: reserved chrome class names, documented in
# html-template.md; slide-internal design elements must not use these names.
EXPORT_CSS = """
/* deck-forge export: pin stage to native 1:1 so the clip is exactly the stage */
.deck-stage{transform:none!important;left:0!important;top:0!important;margin:0!important;}
/* deck-forge export: never screenshot presentation chrome into the PDF */
.deck-controls,.deck-control,.deck-nav,.deck-navigation,.deck-progress,
.progress,.progress-bar,.slide-nav,.slide-counter,.page-counter,.nav-dots,
.edit-toggle,.edit-hotzone,.edit-mode-banner,.boot-check,
[data-export-hide],.no-export,.no-print{display:none!important;visibility:hidden!important;}
/* deck-forge export: kill transitions/animations so every capture is at final
   state, regardless of the deck's own duration/delay parameters */
*,*::before,*::after{transition-duration:0s!important;transition-delay:0s!important;animation-duration:0s!important;animation-delay:0s!important;}
"""

# Show exactly one slide, mechanism-agnostically.
_ACTIVATE_JS = r"""
(index) => {
  const ACTIVE = ['active','visible','current','is-active','is-current','selected','shown'];
  const slides = Array.from(document.querySelectorAll('.slide'));
  slides.forEach((s, i) => {
    const on = i === index;
    ACTIVE.forEach(c => s.classList.toggle(c, on));
    s.style.removeProperty('display');           // let deck's own .active{display:...} win
    s.style.visibility = on ? 'visible' : 'hidden';
    s.style.opacity    = on ? '1' : '0';
  });
  const ctrl = window.presentation || window.deck || window.Deck || window.app;
  for (const m of ['goToSlide','goTo','showSlide','show','select']) {
    if (ctrl && typeof ctrl[m] === 'function') { try { ctrl[m](index); } catch (e) {} break; }
  }
}
"""

# document.fonts.check() returns true for families with NO registered FontFace
# (the spec treats them as system fonts), so it cannot assert availability.
# Metrics can: a family that fails to resolve falls to the browser's
# last-resort font — the same place a guaranteed-nonexistent family lands —
# so equal probe widths mean the family did not load. (Comparing serif vs
# monospace fallbacks does NOT work: Playwright's bundled Chromium maps both
# generics to one last-resort font on Windows.)
_FONT_AVAILABLE_JS = r"""
(family) => {
  const GENERIC = ['serif', 'sans-serif', 'monospace', 'cursive', 'fantasy',
                   'system-ui', 'ui-serif', 'ui-sans-serif', 'ui-monospace',
                   'ui-rounded', 'math'];
  if (GENERIC.includes(family.trim().toLowerCase())) return true;
  const measure = (name) => {
    const s = document.createElement('span');
    s.style.cssText = 'position:absolute;left:-99999px;top:0;' +
                      'visibility:hidden;font-size:64px;white-space:pre';
    s.style.fontFamily = name;
    s.textContent = 'mmmmmwwwwwiiiii10101';
    document.body.appendChild(s);
    const w = s.getBoundingClientRect().width;
    s.remove();
    return w;
  };
  return measure(JSON.stringify(family)) !== measure('"__deckforge_nonexistent__"');
}
"""

# Force load-in animations to their final state (triggers don't fire in a
# headless single-shot capture).
_FORCE_REVEAL_JS = r"""
(index) => {
  const cur = document.querySelectorAll('.slide')[index];
  if (!cur) return;
  cur.querySelectorAll('[class*="reveal"],[data-reveal],[data-anim],.fade-in,.animate,.anim').forEach(el => {
    el.classList.add('revealed','is-visible','in-view','show');
    el.style.opacity = '1';
    el.style.transform = 'none';
    el.style.visibility = 'visible';
  });
}
"""


def _start_server(serve_dir: Path):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(serve_dir), **kw)

        def log_message(self, *a):
            pass

    httpd = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def resolve_browser_executable(raw: str | None) -> Path | None:
    """Resolve an explicit or shared browser path before Playwright launches."""
    raw = raw or os.environ.get("DECK_FORGE_BROWSER_EXECUTABLE")
    if not raw:
        return None
    path = Path(raw).expanduser().resolve()
    if not path.is_file():
        sys.exit("deck-forge: --browser-executable is not a file "
                 "(or DECK_FORGE_BROWSER_EXECUTABLE): "
                 f"{path}")
    return path


def _flush_resource_failures(failures: list[str], ignore: bool) -> None:
    """Fail closed on font/asset problems; --ignore-resource-errors downgrades."""
    if not failures:
        return
    label = "WARNING (ignored)" if ignore else "ERROR"
    for failure in dict.fromkeys(failures):          # de-duped, order kept
        print(f"  {label}: {failure}")
    if not ignore:
        sys.exit("export_pdf: the failures above would produce a silently "
                 "degraded PDF (fallback fonts / missing assets). Fix them or "
                 "rerun with --ignore-resource-errors.")
    failures.clear()


def _capture(port: int, html_name: str, tmp: Path, scale: int,
             require_fonts: tuple[str, ...] = (),
             ignore_resource_errors: bool = False,
             browser_executable: Path | None = None) -> list[str]:
    """Screenshot every slide; returns the PNG paths. Browser always closed."""
    W, H = 1920, 1080
    shots: list[str] = []
    # Resource types whose failure visibly degrades the capture.
    tracked = {"stylesheet", "font", "image", "media", "script"}
    failures: list[str] = []
    with sync_playwright() as p:
        launch_args = ({} if browser_executable is None
                       else {"executable_path": str(browser_executable)})
        browser = p.chromium.launch(**launch_args)
        try:
            page = browser.new_page(viewport={"width": W, "height": H},
                                    device_scale_factor=scale)
            # ERR_ABORTED is routinely benign (media range requests, cancelled
            # speculative loads); real font damage still surfaces via the
            # FontFace status check below.
            page.on("requestfailed", lambda req: failures.append(
                f"request failed: [{req.resource_type}] {req.url} ({req.failure})")
                if req.resource_type in tracked
                and "ERR_ABORTED" not in str(req.failure or "") else None)
            page.on("response", lambda resp: failures.append(
                f"HTTP {resp.status}: [{resp.request.resource_type}] {resp.url}")
                if resp.status >= 400 and resp.request.resource_type in tracked
                else None)
            page.goto(f"http://127.0.0.1:{port}/{quote(html_name)}",
                      wait_until="networkidle")
            page.add_style_tag(content=EXPORT_CSS)
            page.evaluate("() => document.fonts.ready")
            page.wait_for_timeout(1200)

            # fonts.ready resolving does NOT mean the fonts loaded — a 404'd or
            # corrupt FontFace still resolves it and the page silently renders
            # with fallback fonts, changing metrics and line breaks.
            failures.extend(page.evaluate(
                "() => [...document.fonts]"
                ".filter(f => f.status === 'error')"
                ".map(f => `font failed to load: ${f.family} ${f.style} ${f.weight}`)"))
            for family in require_fonts:
                if not page.evaluate(_FONT_AVAILABLE_JS, family):
                    failures.append(f"required font not available: {family}")
            _flush_resource_failures(failures, ignore_resource_errors)

            count = page.evaluate("() => document.querySelectorAll('.slide').length")
            if not count:
                sys.exit("export_pdf: 0 slides found. Decks must use "
                         "<section class=\"slide\"> / <div class=\"slide\">.")
            print(f"  Found {count} slides (capturing at {W*scale}x{H*scale})")

            for i in range(count):
                page.evaluate(_ACTIVATE_JS, i)
                page.wait_for_timeout(350)
                page.evaluate(_FORCE_REVEAL_JS, i)
                page.wait_for_timeout(150)
                shot = tmp / f"slide-{i + 1:03d}.png"
                page.screenshot(path=str(shot),
                                clip={"x": 0, "y": 0, "width": W, "height": H})
                shots.append(str(shot))
                print(f"  Captured slide {i + 1}/{count}")
            # Slide activation can trigger lazy per-slide asset loads; give
            # in-flight requests a moment to fail before the final check (a
            # stall longer than this can still slip through — the audit
            # script's broken-image check is the second line of defense).
            page.wait_for_timeout(250)
            _flush_resource_failures(failures, ignore_resource_errors)
        finally:
            browser.close()
    return shots


def export(input_html: Path, output_pdf: Path, scale: int,
           require_fonts: tuple[str, ...] = (),
           ignore_resource_errors: bool = False,
           keep_pngs: Path | None = None,
           browser_executable: Path | None = None) -> None:
    W, H = 1920, 1080
    httpd, port = _start_server(input_html.parent)
    tmp = Path(tempfile.mkdtemp(prefix="deckforge-"))
    try:
        shots = _capture(port, input_html.name, tmp, scale,
                         require_fonts, ignore_resource_errors,
                         browser_executable)

        if keep_pngs is not None:
            keep_pngs.mkdir(parents=True, exist_ok=True)
            # A previous export's extra pages would corrupt v1/v2 comparison.
            for stale in keep_pngs.glob("slide-*.png"):
                stale.unlink()
            for shot in shots:
                shutil.copy2(shot, keep_pngs / Path(shot).name)
            print(f"  Kept {len(shots)} per-slide PNGs in {keep_pngs} "
                  "(compare versions with make_contact_sheet.py / "
                  "audit_rendered_pages.py)")

        print("  Assembling PDF (lossless)...")
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        layout = img2pdf.get_layout_fun(
            (img2pdf.in_to_pt(W / 96.0), img2pdf.in_to_pt(H / 96.0)))
        with open(output_pdf, "wb") as f:
            f.write(img2pdf.convert(shots, layout_fun=layout))
    finally:
        httpd.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)   # never leave screenshots in %TEMP%

    size_mb = output_pdf.stat().st_size / (1024 * 1024)
    print(f"\n  OK  PDF saved: {output_pdf}  ({size_mb:.1f} MB)")
    print("  Note: animations are captured at their final state (static export).")


def main() -> None:
    # Failure details can echo font family names and CJK paths; never let a
    # cp936 console pipe kill the export with UnicodeEncodeError.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description="Export an HTML deck to a crisp screenshot PDF.")
    ap.add_argument("input_html")
    ap.add_argument("output_pdf", nargs="?")
    size = ap.add_mutually_exclusive_group()
    size.add_argument("--scale", type=int, default=2,
                      help="device scale factor (default 2; sharper + larger)")
    size.add_argument("--compact", action="store_true",
                      help="shortcut for --scale 1 (smaller file, still lossless)")
    ap.add_argument("--browser-executable", metavar="PATH",
                    help="use an existing Chromium/Chrome executable instead of "
                         "Playwright's managed browser")
    ap.add_argument("--require-font", action="append", default=[],
                    metavar="FAMILY",
                    help="assert this font family resolved before capturing "
                         "(repeatable)")
    ap.add_argument("--keep-pngs", metavar="DIR",
                    help="also save the per-slide PNGs (slide-NNN.png) into DIR")
    ap.add_argument("--ignore-resource-errors", action="store_true",
                    help="report font/asset load failures but export anyway")
    args = ap.parse_args()

    input_html = Path(args.input_html).resolve()
    if not input_html.is_file():
        sys.exit(f"export_pdf: file not found: {input_html}")
    output_pdf = (Path(args.output_pdf).resolve() if args.output_pdf
                  else input_html.with_suffix(".pdf"))
    scale = 1 if args.compact else max(1, args.scale)

    browser_executable = resolve_browser_executable(args.browser_executable)

    keep_pngs = Path(args.keep_pngs).resolve() if args.keep_pngs else None
    if keep_pngs is not None and keep_pngs.exists() and not keep_pngs.is_dir():
        sys.exit(f"export_pdf: --keep-pngs target is not a directory: {keep_pngs}")

    print(f"Exporting {input_html.name} -> {output_pdf.name} (scale {scale})")
    export(input_html, output_pdf, scale,
           require_fonts=tuple(args.require_font),
           ignore_resource_errors=args.ignore_resource_errors,
           keep_pngs=keep_pngs,
           browser_executable=browser_executable)


if __name__ == "__main__":
    main()
