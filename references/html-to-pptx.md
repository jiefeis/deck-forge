# Generated deck → editable PPTX

Read this when the user has a deck-forge HTML/PDF deck and asks for a
PowerPoint file ("变成 PPT", "能改字的版本", "give me the pptx"). It is a Phase 5
next step, not a mode: Generate still delivers the PDF; this adds an editable
companion built from the same HTML.

## Confirm the reading first

Two different artifacts hide behind "make it a PPT", and the wrong one is a full
redo. Ask before building:

- **native** (default) — real text boxes, autoshapes, tables, pictures for
  SVG/IMG. Editable; not pixel-identical, because PowerPoint lays type out
  differently from a browser.
- **image-only** — one full-bleed screenshot per slide. Pixel-identical;
  nothing editable. `--image-only`.

## Run

```bash
python <skill-root>/scripts/export_pptx.py build <deck>/index.html <deck>/<name>.pptx --font "<deck font>"
```

Build from the HTML, never from the PDF: the script measures the rendered
deck in Playwright and emits shapes at the measured boxes, so it needs the
source. Pass the deck's own CJK font with `--font`; the default (Microsoft
YaHei) is the Windows-safe choice when the file will be forwarded, and the
deck's font is the choice when the user compares it with the PDF they saw.

The four PowerPoint defaults that otherwise corrupt CJK output (Latin
line-breaking, theme-font fallback, autofit shrink, frames pushed off-canvas)
are handled in the script; do not hand-author around them.

## Verify — every page, rendered

```bash
python <skill-root>/scripts/export_pdf.py <deck>/index.html <scratch>/ref.pdf --keep-pngs <scratch>/ref
powershell -NoProfile -ExecutionPolicy Bypass -File <skill-root>/scripts/render_pptx.ps1 -InputPptx <deck>/<name>.pptx -OutputDir <scratch>/pptx
python <skill-root>/scripts/export_pptx.py diff <scratch>/ref <scratch>/pptx
```

Read the two columns differently. **Raw diff of 10–12 % on CJK pages is
normal**: glyph rasterisation, plus PowerPoint setting fullwidth punctuation
（：""，）at full em width where browsers compress it, which widens titles a few
percent without changing wrapping. **Solid diff** is what survives erosion —
blocks, not strokes — and is the only number that flags a layout defect. Open
every page it flags at full size (`visual-qa.md`); do not chase raw.

When both PowerPoint and WPS are installed, render with both: two engines
agreeing separates "the file is wrong" from "one renderer is odd".

## Hand over

Name the chrome the deck inherited from its template — an edge bar, a corner
block, a rule that touches the page edge. Full-bleed elements read as
conversion artifacts to someone opening the PPTX cold, and a design decision
gets reported back as overflow.
