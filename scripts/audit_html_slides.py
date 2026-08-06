#!/usr/bin/env python3
"""
audit_html_slides.py - deterministic pre-export audit for GENERATED HTML decks.

Runs the deck under the exact same normalization the PDF exporter uses (same
chrome-hiding CSS, same slide activation, same forced reveal state — imported
from export_pdf.py, so the two can never drift apart) and checks each slide for
machine-decidable defects. It complements — never replaces — the Phase 4
visual inspection: pass this audit first, then look at every page.

HARD FAILURES (exit 1) — deterministic bugs in the deliverable:
  - zero slides, or --expect-slides mismatch
  - active slide box is not exactly 1920x1080 at the stage origin
    (the exporter clips that region; anything else exports wrong)
  - failed font/stylesheet/image/media/script requests, or an errored FontFace
  - a --require-font family that did not resolve
  - broken or never-loaded <img>
  - clipped text: glyph rects extending past a clipping ancestor's box on the
    clipping axis (text measured directly, so decorative children bleeding
    inside an overflow:hidden card do not false-fail); a deliberate text mask
    can be excused per snippet with --allow-clipped-text
  - text glyphs crossing the 1920x1080 stage boundary (cut off in the PDF);
    deliberate decorative bleed can be excused per snippet with
    --allow-offstage-text; unused excuses of either kind fail closed
  - a completely blank slide (no visible text, media, or styled element)

WARNINGS (exit 0) — heuristics with legitimate exceptions; inspect visually:
  - two text nodes whose glyph rects overlap (legal for badges/overlays)
  - bottom third of the slide entirely empty (legal for emphasis layouts)

Usage:
    python audit_html_slides.py <deck.html> [--expect-slides N]
        [--require-font FAMILY]... [--allow-offstage-text SNIPPET]...
        [--allow-clipped-text SNIPPET]... [--json]

Requires: pip install playwright img2pdf  +  python -m playwright install chromium
(img2pdf only because the shared exporter module imports it).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import quote

# Reuse the exporter's normalization contract (EXPORT_CSS, activation, reveal
# forcing, local server). export_pdf exits with install hints if playwright or
# img2pdf are missing, which is the right behavior here too.
import export_pdf as _exporter

from playwright.sync_api import sync_playwright

TOL = 2  # px tolerance for rounding in geometry checks

# All geometry checks for one activated slide, in one page round-trip.
_SLIDE_CHECKS_JS = r"""
(index) => {
  const W = 1920, H = 1080, TOL = 2;
  const slide = document.querySelectorAll('.slide')[index];
  const out = {slideRect: null, clipped: [], offstage: [], brokenImages: [],
               overlaps: [], blank: false, maxBottom: 0};

  // Own computed visibility is authoritative (a visibility:visible descendant
  // inside a hidden ancestor still renders); display and opacity are not
  // overridable, so those two walk the ancestor chain.
  const visible = (el) => {
    if (getComputedStyle(el).visibility === 'hidden') return false;
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const s = getComputedStyle(n);
      if (s.display === 'none' || parseFloat(s.opacity) === 0) return false;
    }
    return true;
  };
  const label = (el, text) => {
    const cls = (typeof el.className === 'string' && el.className.trim())
      ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '';
    const t = (text ?? el.textContent ?? '').trim().replace(/\s+/g, ' ');
    return el.tagName.toLowerCase() + cls + (t ? ` "${t.slice(0, 60)}"` : '');
  };

  const r = slide.getBoundingClientRect();
  out.slideRect = {x: r.x, y: r.y, w: r.width, h: r.height};

  // Broken / never-loaded images.
  for (const img of slide.querySelectorAll('img')) {
    if (!visible(img)) continue;
    if (!img.complete) out.brokenImages.push('never loaded: ' + (img.currentSrc || img.src));
    else if (!img.naturalWidth) out.brokenImages.push('broken: ' + (img.currentSrc || img.src));
  }

  // Text nodes with their per-line glyph rects. Ranges report layout
  // positions even where an ancestor clips, so the same rects drive the
  // offstage, clipped, overlap, and bottom-coverage checks — and non-text
  // decoration never counts.
  const stage = {left: -TOL, top: -TOL, right: W + TOL, bottom: H + TOL};
  const nodes = [];
  const walker = document.createTreeWalker(slide, NodeFilter.SHOW_TEXT);
  for (let n; (n = walker.nextNode()); ) {
    if (!n.textContent.trim() || !visible(n.parentElement)) continue;
    const range = document.createRange();
    range.selectNodeContents(n);
    const rects = [...range.getClientRects()].filter(g => g.width >= 1 && g.height >= 1);
    if (!rects.length) continue;
    nodes.push({el: n.parentElement, rects, text: n.textContent});
    if (rects.some(g => g.left < stage.left || g.top < stage.top ||
                        g.right > stage.right || g.bottom > stage.bottom))
      out.offstage.push(label(n.parentElement, n.textContent));
  }

  // Clipped text: glyphs extending past a clipping ancestor's border box on
  // the clipping axis. Measuring the text's own rects (not element scroll
  // sizes) keeps decorative children that bleed inside an overflow:hidden
  // card from false-failing. The slide's own edge is the offstage check's job.
  const CLIPS = ['hidden', 'clip', 'auto', 'scroll'];
  for (const node of nodes) {
    for (let anc = node.el; anc && anc !== slide; anc = anc.parentElement) {
      const s = getComputedStyle(anc);
      const cx = CLIPS.includes(s.overflowX), cy = CLIPS.includes(s.overflowY);
      if (!cx && !cy) continue;
      const b = anc.getBoundingClientRect();
      if (node.rects.some(g =>
          (cx && (g.left < b.left - TOL || g.right > b.right + TOL)) ||
          (cy && (g.top < b.top - TOL || g.bottom > b.bottom + TOL)))) {
        out.clipped.push(label(node.el, node.text));
        break;
      }
    }
  }

  // Pairwise glyph-rect collisions. Rect-level comparison, so wrapped sibling
  // spans whose union boxes would overlap do not false-positive.
  for (let i = 0; i < nodes.length && out.overlaps.length < 20; i++) {
    for (let j = i + 1; j < nodes.length && out.overlaps.length < 20; j++) {
      const a = nodes[i], b = nodes[j];
      if (a.el === b.el || a.el.contains(b.el) || b.el.contains(a.el)) continue;
      const hit = a.rects.some(ga => b.rects.some(gb => {
        const w = Math.min(ga.right, gb.right) - Math.max(ga.left, gb.left);
        const h = Math.min(ga.bottom, gb.bottom) - Math.max(ga.top, gb.top);
        return w > 4 && h > 4;
      }));
      if (hit)
        out.overlaps.push(label(a.el, a.text) + '  x  ' + label(b.el, b.text));
    }
  }

  // Blank-slide + bottom-coverage evidence: text, media, or styled elements
  // that do not just paint the whole stage. Background art (the slide's own
  // background-image plus ::before/::after generated text, images, or fills)
  // counts as content for the blank check, but not as bottom coverage —
  // pseudo-element geometry is unmeasurable here, a known maxBottom blind spot.
  let hasContent = nodes.length > 0;
  const bgArt = (el) => [null, '::before', '::after'].some(pseudo => {
    const s = getComputedStyle(el, pseudo);
    if (pseudo) {
      const c = s.content;
      if (c === 'none' || c === 'normal') return false;
      if (c.startsWith('"') && c !== '""') return true;   // generated text
      return s.backgroundImage !== 'none' ||
             (s.backgroundColor !== 'rgba(0, 0, 0, 0)' &&
              s.backgroundColor !== 'transparent');
    }
    return s.backgroundImage !== 'none';
  });
  if (!hasContent && bgArt(slide)) hasContent = true;
  for (const el of slide.querySelectorAll('*')) {
    if (hasContent) break;
    if (visible(el) && bgArt(el)) hasContent = true;
  }
  for (const el of slide.querySelectorAll('*')) {
    if (out.maxBottom >= H && hasContent) break;
    if (!visible(el)) continue;
    const b = el.getBoundingClientRect();
    if (b.width < 1 || b.height < 1) continue;
    // toUpperCase: inline SVG reports a lowercase tagName.
    const media = ['IMG', 'SVG', 'CANVAS', 'VIDEO'].includes(el.tagName.toUpperCase());
    const s = media ? null : getComputedStyle(el);
    const styled = media || (s && (
      s.backgroundImage !== 'none' ||
      (s.backgroundColor !== 'rgba(0, 0, 0, 0)' && s.backgroundColor !== 'transparent') ||
      s.boxShadow !== 'none' || parseFloat(s.borderTopWidth) > 0));
    if (!styled) continue;
    // Full-bleed media (a full-page photo) is real content; full-bleed
    // background paint is not. Neither counts toward bottom coverage.
    const fullBleed = b.width >= W * 0.95 && b.height >= H * 0.95;
    if (media) hasContent = true;
    if (!fullBleed) {
      hasContent = true;
      out.maxBottom = Math.max(out.maxBottom, Math.min(b.bottom, H));
    }
  }
  for (const n of nodes)
    for (const g of n.rects)
      out.maxBottom = Math.max(out.maxBottom, Math.min(g.bottom, H));
  out.blank = !hasContent;
  return out;
}
"""


def audit(input_html: Path, expect_slides: int | None,
          require_fonts: tuple[str, ...],
          allow_offstage: tuple[str, ...],
          allow_clipped: tuple[str, ...],
          browser_executable: Path | None = None) -> dict:
    failures: list[dict] = []
    warnings: list[dict] = []

    def fail(slide: int | None, check: str, detail: str) -> None:
        failures.append({"slide": slide, "check": check, "detail": detail})

    def warn(slide: int | None, check: str, detail: str) -> None:
        warnings.append({"slide": slide, "check": check, "detail": detail})

    tracked = {"stylesheet", "font", "image", "media", "script"}
    net_failures: list[str] = []
    httpd, port = _exporter._start_server(input_html.parent)
    try:
        with sync_playwright() as p:
            browser = _exporter.launch_chromium(p, browser_executable)
            try:
                page = browser.new_page(viewport={"width": 1920, "height": 1080})
                # ERR_ABORTED is routinely benign (media range requests,
                # cancelled speculative loads); real font/image damage still
                # surfaces via FontFace status and the broken-image check.
                page.on("requestfailed", lambda req: net_failures.append(
                    f"request failed: [{req.resource_type}] {req.url} ({req.failure})")
                    if req.resource_type in tracked
                    and "ERR_ABORTED" not in str(req.failure or "") else None)
                page.on("response", lambda resp: net_failures.append(
                    f"HTTP {resp.status}: [{resp.request.resource_type}] {resp.url}")
                    if resp.status >= 400 and resp.request.resource_type in tracked
                    else None)
                page.goto(f"http://127.0.0.1:{port}/{quote(input_html.name)}",
                          wait_until="networkidle")
                page.add_style_tag(content=_exporter.EXPORT_CSS)
                page.evaluate("() => document.fonts.ready")
                page.wait_for_timeout(1200)

                for entry in page.evaluate(
                        "() => [...document.fonts]"
                        ".filter(f => f.status === 'error')"
                        ".map(f => `${f.family} ${f.style} ${f.weight}`)"):
                    fail(None, "font-error", f"font failed to load: {entry}")
                for family in require_fonts:
                    if not page.evaluate(_exporter._FONT_AVAILABLE_JS, family):
                        fail(None, "font-missing",
                             f"required font not available: {family}")

                count = page.evaluate(
                    "() => document.querySelectorAll('.slide').length")
                if not count:
                    fail(None, "no-slides",
                         "0 slides found; decks must use .slide sections")
                if expect_slides is not None and count != expect_slides:
                    fail(None, "slide-count",
                         f"expected {expect_slides} slides, found {count}")

                used_excuses = {"offstage": set(), "clipped": set()}

                def excused(item: str, kind: str,
                            excuses: tuple[str, ...]) -> bool:
                    matched = [a for a in excuses if a in item]
                    used_excuses[kind].update(matched)   # credit EVERY match
                    return bool(matched)

                for i in range(count):
                    page.evaluate(_exporter._ACTIVATE_JS, i)
                    page.wait_for_timeout(350)
                    page.evaluate(_exporter._FORCE_REVEAL_JS, i)
                    page.wait_for_timeout(150)
                    res = page.evaluate(_SLIDE_CHECKS_JS, i)
                    n = i + 1

                    r = res["slideRect"]
                    if (abs(r["x"]) > TOL or abs(r["y"]) > TOL or
                            abs(r["w"] - 1920) > TOL or abs(r["h"] - 1080) > TOL):
                        fail(n, "slide-geometry",
                             f"slide box is ({r['x']:.0f},{r['y']:.0f} "
                             f"{r['w']:.0f}x{r['h']:.0f}), expected (0,0 1920x1080); "
                             "the exporter clips exactly that region")
                    for item in res["brokenImages"]:
                        fail(n, "broken-image", item)
                    for item in res["clipped"]:
                        if not excused(item, "clipped", allow_clipped):
                            fail(n, "clipped-text",
                                 f"{item} — text extends past a clipping "
                                 "container and will be cut in the PDF (excuse "
                                 "a deliberate mask, after visual review, with "
                                 "--allow-clipped-text)")
                    for item in res["offstage"]:
                        if not excused(item, "offstage", allow_offstage):
                            fail(n, "offstage-text",
                                 f"{item} — text crosses the 1920x1080 stage "
                                 "boundary and will be cut in the PDF (excuse "
                                 "deliberate bleed with --allow-offstage-text)")
                    if res["blank"]:
                        fail(n, "blank-slide",
                             "no visible text, media, or styled element")
                    for item in res["overlaps"]:
                        warn(n, "text-overlap", item)
                    if not res["blank"] and res["maxBottom"] < 1080 * 2 / 3:
                        warn(n, "empty-bottom",
                             f"no content below y={res['maxBottom']:.0f}; "
                             "large bottom void — confirm it is intentional")

                for flag, kind, excuses in (
                        ("--allow-offstage-text", "offstage", allow_offstage),
                        ("--allow-clipped-text", "clipped", allow_clipped)):
                    for excuse in excuses:
                        if excuse not in used_excuses[kind]:
                            fail(None, "unused-excuse",
                                 f"{flag} {excuse!r} matched nothing; remove "
                                 "it or fix the snippet (excuses fail closed)")
            finally:
                browser.close()
    finally:
        httpd.shutdown()

    for item in dict.fromkeys(net_failures):
        fail(None, "resource-error", item)

    return {"status": "FAIL" if failures else "OK", "slides": count,
            "failures": failures, "warnings": warnings}


def main() -> int:
    # Findings echo raw slide text (CJK, emoji, dingbats); never let a cp936
    # console pipe kill the audit with UnicodeEncodeError.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(
        description="Deterministic pre-export audit for generated HTML decks.")
    ap.add_argument("input_html")
    ap.add_argument("--browser-executable", metavar="PATH",
                    help="use an existing Chromium/Chrome executable instead of "
                         "Playwright's managed browser")
    ap.add_argument("--expect-slides", type=int, default=None,
                    help="fail unless the deck has exactly this many slides")
    ap.add_argument("--require-font", action="append", default=[],
                    metavar="FAMILY",
                    help="assert this font family resolved (repeatable)")
    ap.add_argument("--allow-offstage-text", action="append", default=[],
                    metavar="SNIPPET",
                    help="excuse one reported offstage finding whose label "
                         "contains SNIPPET, after visual review (repeatable; "
                         "unused excuses fail)")
    ap.add_argument("--allow-clipped-text", action="append", default=[],
                    metavar="SNIPPET",
                    help="excuse one reported clipped finding whose label "
                         "contains SNIPPET, after visual review (repeatable; "
                         "unused excuses fail)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    input_html = Path(args.input_html).resolve()
    if not input_html.is_file():
        sys.exit(f"audit_html_slides: file not found: {input_html}")
    browser_executable = _exporter.resolve_browser_executable(
        args.browser_executable)

    report = audit(input_html, args.expect_slides,
                   tuple(args.require_font), tuple(args.allow_offstage_text),
                   tuple(args.allow_clipped_text), browser_executable)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"audit_html_slides: {report['status']}  "
              f"({report['slides']} slides, {len(report['failures'])} failures, "
              f"{len(report['warnings'])} warnings)")
        for f in report["failures"]:
            where = f"slide {f['slide']}" if f["slide"] else "deck"
            print(f"  FAIL  [{where}] {f['check']}: {f['detail']}")
        for w in report["warnings"]:
            print(f"  warn  [slide {w['slide']}] {w['check']}: {w['detail']}")
        if report["status"] == "OK":
            print("  Deterministic checks passed. Now render and inspect every "
                  "page visually (workflow.md Phase 4) — this audit cannot "
                  "judge design intent.")
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
