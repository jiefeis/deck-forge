---
name: deck-forge
description: >-
  Build design-rich slide/deck-style PDF presentations from notes, outlines,
  docs, images, screenshots, HTML, PDFs, PPTX files, or topics plus a theme/look.
  Use for visual decks, deck-like reformat/restyle work, visual slide QA, and
  prompts such as "做成PDF演示/幻灯片/deck" or "turn this into slides". Do NOT use
  for plain reports, contracts, forms, resumes, spreadsheets, or PDFs needing
  flowing prose/selectable body text. Produces a self-contained 1920x1080 HTML
  deck as the editable intermediate and a crisp lossless screenshot PDF as the
  deliverable.
---

<!-- Maintainers: when editing the frontmatter description above, check that
     agents/openai.yaml (short_description / default_prompt) still matches. -->

# deck-forge

Give it **materials + a theme**, get back a **design-rich PDF deck**. deck-forge
authors a single self-contained 1920×1080 HTML deck (distinctive design, no "AI
slop"), then renders a crisp **lossless screenshot PDF** — the PDF is the
deliverable; the HTML is an editable intermediate.

Fuses **frontend-slides** (brand-free design engine: visual style discovery,
fixed-stage HTML, presets + bold templates) with **rollingai-decks** (structure +
discipline: a layout taxonomy, authoring rules, and a `data-text-id` text
round-trip for editing every word in one file).

> **Full step-by-step detail lives in [references/workflow.md](references/workflow.md).**
> This file is the entry point: trigger, non-negotiables, commands, and routing.

## Preflight & commands

Scripts in `scripts/` are standalone (paths are arguments, cwd-independent).
`<skill-root>` = the absolute path of the folder containing this SKILL.md (you
know it because you just read this file); do not use `~` on Windows. Call
scripts by absolute path (`<skill-root>/scripts/...`); write the generated deck
HTML/PDF into the **user's** working directory, never the skill folder.

```bash
# Verify deps once per Python environment (then install anything it flags):
python <skill-root>/scripts/check_env.py
#   pip install playwright img2pdf lxml   (+ python-pptx for .pptx input)
#   python -m playwright install chromium

# Export the deck to PDF (the deliverable):
python <skill-root>/scripts/export_pdf.py <deck>/index.html [out.pdf] [--compact | --scale N]

# Edit all deck text in one file, then re-export:
python <skill-root>/scripts/edit_texts.py extract <deck>/index.html
python <skill-root>/scripts/edit_texts.py apply   <deck>/index.html <deck>/index.texts.md

# Optional: import a .pptx as source material:
python <skill-root>/scripts/extract_pptx.py <in.pptx> <out_dir>
```

## Non-negotiables

1. **PDF is the product.** Always finish by producing a PDF; never stop at HTML
   unless the user explicitly asks. HTML is the intermediate you build + verify.
2. **Materials drive structure.** Map the source's own storyline first, then pick
   layouts to fit it; the deck is exactly as long as the source is
   (`AUTHORING.md` §1). Never fabricate content to fill a layout.
3. **Fixed 16:9 stage.** Every slide authored at 1920×1080 and scaled as a whole.
   No reflow / scroll / overflow / overlap — anything that doesn't fit screenshots
   into the PDF as a bug (`viewport-base.css`, `AUTHORING.md` §3).
4. **Distinctive design, no AI slop.** Non-system fonts, a committed palette,
   atmosphere, one orchestrated load animation (full guidance in
   [references/workflow.md](references/workflow.md) → "Design Aesthetics").
5. **Verify the PDF.** Inspect every page for overflow / overlap / clipped text /
   empty-bottom / fabrication. The export IS the visual check; fix the HTML and
   re-export until clean. Crispness: the PDF must be lossless (no `DCTDecode`).
6. **Reformat and cross-format QA.** If the task touches PPTX/PDF/images/HTML,
   translation, screenshots, or "reformat/restyle", first read the relevant
   reference files from the "Files & when to read them" table below
   (*Cross-format references* group). Preserve layout unless the user asks for
   relayout.

## Workflow at a glance

Each step is one line here; read [references/workflow.md](references/workflow.md)
for the full instructions before doing it.

0. **Intake** — pull *materials* + *theme* from the request; confirm only purpose
   / length / density. A `.pptx` → run `extract_pptx.py` first.
1. **Map the storyline** — name each page's information shape, pick a matching
   layout from `LAYOUTS.md`, decide deck rhythm; confirm the outline.
2. **Style discovery** — honor a given theme, else generate 3 genuinely different
   preview slides (`STYLE_PRESETS.md`, `bold-template-pack/selection-index.json`);
   user picks. Read a template's full `design.md` only after it's chosen.
3. **Generate the HTML deck** — full `viewport-base.css` inline, `.slide`/
   `.active`, `.reveal`; apply `AUTHORING.md`; one coherent design system.
4. **Render the PDF** — `export_pdf.py` (lossless 2×; `--compact` for size); then
   verify every page.
5. **Deliver** — open the PDF; report path / size / style / slide count; offer
   revisions.
6. **Edit the words** — `edit_texts.py` extract → user edits one file → apply →
   re-export (writes `.bak` by default; in-browser inline edit is NOT bundled).

## Files & when to read them

| File | Purpose | Read in |
| --- | --- | --- |
| `references/workflow.md` | Full Phase 0–6 instructions + Design Aesthetics | any generation run (Phase 0–6) |
| **Cross-format references** (non-negotiable 6) | | |
| `references/source-contract.md` | Source-of-truth, file/version, path, encoding, and open-file rules | multiple source files, version comparison, "only one file", Windows paths, source file open in Office/WPS |
| `references/reformat-and-style.md` | Preserve-layout reformat rules and style extraction | reformat/restyle/font/color/background tasks |
| `references/pptx-native-editing.md` | Native PPTX package, slide order, layout/master, relationship, and hidden-slide guardrails | editing/copying/translating native PPTX |
| `references/image-and-ocr-input.md` | Image, screenshot, chart-image, and OCR input handling | image-to-slide or screenshot source material |
| `references/translation-copyfit.md` | Natural translation and copy fitting in existing layouts | translation/localization tasks |
| `references/visual-qa.md` | Rendered-page contact sheets and final QA checklist | reformat / translation / cross-format comparison |
| `references/good-bad-examples.md` | Examples of good and bad handling patterns | ambiguous cross-format/reformat decisions |
| **Generation assets** | | |
| `AUTHORING.md` | Deck-coherence discipline (rollingai) | Phase 1, 3, 4 |
| `LAYOUTS.md` | Content-shape → layout taxonomy (rollingai) | Phase 1, 3 |
| `STYLE_PRESETS.md` | 12 curated visual presets (frontend-slides) | Phase 2 |
| `bold-template-pack/selection-index.json` | Bold-template index | Phase 2 |
| `bold-template-pack/templates/*/preview.md` | Bold-template preview cards | Phase 2 (shortlist) |
| `bold-template-pack/templates/*/design.md` | Full design recipe (selected only) | Phase 3 |
| `viewport-base.css` | Mandatory fixed-stage CSS | Phase 3 |
| `html-template.md` | HTML/JS architecture | Phase 3 |
| `animation-patterns.md` | Animation reference | Phase 3 |
| `examples/*/index.html` | Reference implementations: lumen-2026 = canonical deck with full `data-text-id` coverage; aurora-metrics = exporter-compatibility stress sample (deliberately deviates from `viewport-base.css`) | Phase 3, when an end-to-end example helps |
| **Scripts** | | |
| `scripts/check_env.py` | verify deps (playwright/img2pdf/lxml + Chromium) | preflight |
| `scripts/export_pdf.py` | HTML → crisp lossless screenshot PDF (deliverable) | Phase 4 |
| `scripts/edit_texts.py` | extract/apply all deck text via one file (rollingai) | Phase 6 |
| `scripts/extract_pptx.py` | PPTX → content JSON (optional input) | Phase 0 |
| `scripts/audit_pptx_page_numbers.py` | audit page-number sources across slides, layouts, and masters | native PPTX page-number/footer edits |

