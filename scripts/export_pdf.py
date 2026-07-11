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

Usage:
    python export_pdf.py <input.html> [output.pdf] [--scale N] [--compact]
      --scale N   device scale factor (default 2; sharper + bigger file)
      --compact   shortcut for --scale 1 (about half the size, still lossless)

Requires: pip install playwright img2pdf  +  python -m playwright install chromium
"""
from __future__ import annotations

import argparse
import http.server
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


def _capture(port: int, html_name: str, tmp: Path, scale: int) -> list[str]:
    """Screenshot every slide; returns the PNG paths. Browser always closed."""
    W, H = 1920, 1080
    shots: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": W, "height": H},
                                    device_scale_factor=scale)
            page.goto(f"http://127.0.0.1:{port}/{quote(html_name)}",
                      wait_until="networkidle")
            page.add_style_tag(content=EXPORT_CSS)
            page.evaluate("() => document.fonts.ready")
            page.wait_for_timeout(1200)

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
        finally:
            browser.close()
    return shots


def export(input_html: Path, output_pdf: Path, scale: int) -> None:
    W, H = 1920, 1080
    httpd, port = _start_server(input_html.parent)
    tmp = Path(tempfile.mkdtemp(prefix="deckforge-"))
    try:
        shots = _capture(port, input_html.name, tmp, scale)

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
    ap = argparse.ArgumentParser(description="Export an HTML deck to a crisp screenshot PDF.")
    ap.add_argument("input_html")
    ap.add_argument("output_pdf", nargs="?")
    size = ap.add_mutually_exclusive_group()
    size.add_argument("--scale", type=int, default=2,
                      help="device scale factor (default 2; sharper + larger)")
    size.add_argument("--compact", action="store_true",
                      help="shortcut for --scale 1 (smaller file, still lossless)")
    args = ap.parse_args()

    input_html = Path(args.input_html).resolve()
    if not input_html.is_file():
        sys.exit(f"export_pdf: file not found: {input_html}")
    output_pdf = (Path(args.output_pdf).resolve() if args.output_pdf
                  else input_html.with_suffix(".pdf"))
    scale = 1 if args.compact else max(1, args.scale)

    print(f"Exporting {input_html.name} -> {output_pdf.name} (scale {scale})")
    export(input_html, output_pdf, scale)


if __name__ == "__main__":
    main()
