---
name: deck-forge
description: >-
  Build, minimally edit, compare, and verify presentations, slide decks, and
  PowerPoint files from notes, images, screenshots, HTML, PDF, or PPTX. Use for
  three modes: new HTML/PDF deck generation; source-preserving native PPTX
  editing — reformat, translation, copy polish, or a new deck authored on an
  existing deck's own template (masters/layouts/theme, delivered as PPTX); and
  read-only deck/version comparison plus visual QA. Also use when slide language
  sounds AI-generated, or for prompts like "turn this into slides", "make a pitch deck",
  "做成PDF演示/幻灯片/deck", "改 PPT", "美化 PPT", or "把 PPT 翻译成英文".
  Do NOT use for plain reports, contracts, forms, resumes, spreadsheets,
  or flowing-prose PDFs.
  Native PPTX mode preserves the source package/layout and delivers the edited
  .pptx; never rebuild a native-edit request through HTML; a new deck on the
  source's own template is native mode too.
---

<!-- Maintainers: when editing the frontmatter description above, check that
     agents/openai.yaml (short_description / default_prompt) still matches. -->

# deck-forge

Choose the artifact mode before touching a file:

- **Generate** — turn materials into a new 1920×1080 HTML deck and lossless PDF.
- **Native edit** — change an existing PPTX inside its own package and deliver
  PPTX: minimal in-place edits (package, page order, hidden slides, geometry,
  and requested output format preserved), or template-native authoring — a
  mostly-new deck built on the source's own masters, layouts, and theme.
- **Audit/compare** — inspect versions, translations, or rendered pages without
  modifying the source.

Pick the mode from the request: existing PPTX + "keep the original / minimal
change / deliver PPTX" → Native edit; PPTX used only as material for a new
deck, PDF delivery accepted → Generate; report differences, change nothing →
Audit/compare. A new deck that must be built on an existing deck's or
template's own masters, layouts, and theme with PPTX delivery is **Native edit
(template-native authoring)**, not Generate, however many pages are new — see
`references/native-template-authoring.md`. If an existing PPTX is input and the
delivery format (PDF vs editable PPTX) is not explicit, confirm with the user
before choosing a mode (`references/source-contract.md` → "Decide the artifact
contract").

Only **Generate** follows the HTML Phase 0–6 workflow. Native edit and
Audit/compare use the cross-format references and audit scripts below.

> **Full step-by-step detail lives in [references/workflow.md](references/workflow.md).**
> This file is the entry point: trigger, non-negotiables, commands, and routing.

## Preflight & commands

Scripts in `scripts/` are standalone (paths are arguments, cwd-independent).
`<skill-root>` = the absolute path of the folder containing this SKILL.md (you
know it because you just read this file); do not use `~` on Windows. Call
scripts by absolute path (`<skill-root>/scripts/...`); write the generated deck
HTML/PDF into the **user's** working directory, never the skill folder.
Requires Python 3.9+ (driven by Playwright).

```bash
# Verify deps once per Python environment (then install anything it flags):
python <skill-root>/scripts/check_env.py
#   pip install playwright img2pdf lxml Pillow   (+ python-pptx for .pptx input)
#   python -m playwright install chromium

# Deterministic pre-export audit of the generated HTML deck (Phase 3→4 gate):
python <skill-root>/scripts/audit_html_slides.py <deck>/index.html

# Export the deck to PDF (the deliverable; fails closed on font/asset errors):
python <skill-root>/scripts/export_pdf.py <deck>/index.html [out.pdf] [--compact | --scale N] [--browser-executable PATH]

# On Windows, when Playwright's managed Chromium cache is missing or mismatched,
# reuse an existing local chrome.exe with this flag (or set DECK_FORGE_BROWSER_EXECUTABLE
# once for both audit and export); only download when none launches.

# Edit all deck text in one file, then re-export:
python <skill-root>/scripts/edit_texts.py extract <deck>/index.html
python <skill-root>/scripts/edit_texts.py apply   <deck>/index.html <deck>/index.texts.md

# Optional, GENERATE mode only: use visible PPTX pages as source material:
python <skill-root>/scripts/extract_pptx.py <in.pptx> <out_dir> --visible-only
```

Native PPTX audit/transplant command syntax lives in the Native-edit references;
the Scripts table below is the script→purpose→when index.

## Non-negotiables

1. **Mode is the artifact contract.** Generate delivers PDF; Native edit delivers
   the edited PPTX; Audit/compare is read-only. Never silently change modes.
2. **Scope before mutation.** For native edits, record target slides, allowed
   properties, forbidden changes, output path, and hidden-backup policy using
   `references/edit-scope-contract.md`; verify untouched scope afterwards.
3. **Materials drive generated structure.** Map the source's own storyline, then pick
   layouts to fit it; slide count follows the evidence and the narrative — never
   pad pages to fill a template (`AUTHORING.md` → "Establish the source
   boundary"). Never fabricate content to fill a layout.
4. **Fixed 16:9 generation stage.** Every HTML slide is authored at 1920×1080
   and scaled as a whole.
   No reflow / scroll / overflow / overlap — anything that doesn't fit screenshots
   into the PDF as a bug (`viewport-base.css`; `AUTHORING.md` → "Fit content
   without fabrication").
5. **Generated design is distinctive, not generic.** In Generate mode, use
   deliberate fonts, a committed palette, atmosphere, and one orchestrated load
   animation (full guidance in
   [references/workflow.md](references/workflow.md) → "Design Aesthetics").
6. **Verify the final artifact after the final write.** Inspect every page, not a
   sample. For native PPTX, also verify package integrity, page order, hidden
   state, and unauthorized changes. For generated PDF, require no `DCTDecode`.
7. **Reformat and cross-format QA.** For cross-format, translation, or
   reformat/restyle tasks, read the matching references from the "Files & when
   to read them" table. Preserve layout unless the user asks for relayout.
8. **Page identities are separate namespaces.** When hidden pages, inserted
   pages, displayed markers, or a mother draft exist, freeze physical page,
   visible ordinal, displayed marker, stable slide ID, title, and source-page
   mapping before editing. "Ignore hidden pages" may govern source mapping; it
   never removes hidden pages from package preservation or QA.
9. **The baseline owns the native package.** A high-level library's export is
   only a candidate until order, hidden state, notes, relationships, and shared
   parts pass structural audit. If the exporter churns the package, rebase only
   the authorized slide-local component onto the baseline; never waive shared
   changes because untouched renders look identical.

## Workflow at a glance

For **Native edit**, read `source-contract.md` → `edit-scope-contract.md` → the
task-specific references → `visual-qa.md`; use a dedicated PPTX tool when
available and never run the generation phases. For selected-page redesign from
a mother draft or reference template—especially with hidden pages—also read
`native-redesign-fidelity.md` and build its page-address/content/topology
contracts. If the edit adds newly authored slides, merges slides from another
deck, or fills template pages, first run `audit_pptx_typography.py` on the
target deck and report same-role font/size inconsistencies to the user before mutating
(`references/pptx-native-editing.md` → Typography baseline). For
template-native authoring (a mostly-new deck on the source's own
masters/layouts/theme), also read `references/native-template-authoring.md` plus
`AUTHORING.md` → "Plan the page sequence" and "Fit content without fabrication".
For **Audit/compare**, remain read-only and use the manifests/audit scripts
before rendering.

The following Phase 0–6 sequence is **Generate mode only**.

Each step is one line here; read [references/workflow.md](references/workflow.md)
for the full instructions before doing it.

0. **Intake** — pull *materials* + *theme* from the request; confirm only purpose
   / length / density. A source `.pptx` being repurposed into a new deck may be
   extracted with `--visible-only`; a native-edit PPTX must not be extracted.
1. **Map the storyline** — name each page's information shape, pick a matching
   layout from `LAYOUTS.md`, decide deck rhythm; confirm the outline.
2. **Style discovery** — honor a given theme, else generate 3 genuinely different
   preview slides (`STYLE_PRESETS.md`, `bold-template-pack/selection-index.json`);
   user picks. Read a template's full `design.md` only after it's chosen.
3. **Generate the HTML deck** — full `viewport-base.css` inline, `.slide`/
   `.active`, `.reveal`; apply `AUTHORING.md`; one coherent design system.
4. **Render the PDF** — `audit_html_slides.py` gate, then `export_pdf.py`
   (lossless 2×; `--compact` for size); then verify every page.
5. **Deliver** — open the PDF; report path / size / style / slide count; offer
   revisions.
6. **Edit the words** — `edit_texts.py` extract → user edits one file → apply →
   re-export (writes `.bak` by default; in-browser inline edit is NOT bundled).

## Files & when to read them

| File | Purpose | Read in |
| --- | --- | --- |
| `references/workflow.md` | Full Phase 0–6 instructions + Design Aesthetics | any generation run (Phase 0–6) |
| **Cross-format references** (non-negotiable 7) | | |
| `references/source-contract.md` | Source-of-truth, file/version, path, encoding, and open-file rules | first read for any native edit; also multiple source files, version comparison, "only one file", Windows paths, source file open in Office/WPS |
| `references/edit-scope-contract.md` | Target-slide/allowed-change contract and before/after verification | native PPTX edits, "minimal change", selected pages/elements, untouched-slide guarantees |
| `references/native-redesign-fidelity.md` | Physical / visible ordinal / displayed marker / source page mapping, mother-draft fidelity, relationship topology, template composition, and safe candidate rebasing | selected-page native redesign, hidden-page offsets, mother drafts, teaching plans, complex loops/flows |
| `references/native-template-authoring.md` | Layout inventory, template-page reuse, shape copying, text-frame mechanics, and page numbers when authoring a new deck on an existing template | template-native authoring: mostly-new pages on an existing PPTX's masters/layouts, PPTX delivery |
| `references/reformat-and-style.md` | Preserve-layout reformat rules and style extraction | reformat/restyle/font/color/background tasks |
| `references/pptx-native-editing.md` | Native PPTX package, slide order, layout/master, relationship, and hidden-slide guardrails | editing/copying/translating native PPTX |
| `references/image-and-ocr-input.md` | Image, screenshot, chart-image, and OCR input handling | image-to-slide or screenshot source material |
| `references/translation-copyfit.md` | Natural translation and copy fitting in existing layouts | translation/localization tasks |
| `references/deck-copy-and-ai-slop.md` | Make slide copy sound like a real presenter while preserving layout and fit | "AI 味" / "太像 AI 写的" deck copy, presenter-language polish |
| `references/visual-qa.md` | Rendered-page contact sheets and final QA checklist | native PPTX edits, reformat / translation / cross-format comparison |
| `references/good-bad-examples.md` | Examples of good and bad handling patterns | ambiguous cross-format/reformat decisions |
| **Generation assets** | | |
| `AUTHORING.md` | Source fidelity, deck coherence, fit, and final verification | Phase 1, 3, 4; template-native authoring (storyline and fit sections) |
| `LAYOUTS.md` | Information-shape → composition selection guide | Phase 1, 3 |
| `STYLE_PRESETS.md` | 12 curated visual presets (frontend-slides) | Phase 2 |
| `bold-template-pack/selection-index.json` | Bold-template index | Phase 2 |
| `bold-template-pack/templates/*/preview.md` | Bold-template preview cards | Phase 2 (shortlist) |
| `bold-template-pack/templates/*/design.md` | Full design recipe (selected only) | Phase 3 |
| `viewport-base.css` | Mandatory fixed-stage CSS | Phase 3 |
| `html-template.md` | HTML/JS architecture | Phase 3 |
| `animation-patterns.md` | Animation reference | Phase 3 |
| `examples/*/index.html` | Reference implementations: lumen-2026 = canonical deck with full `data-text-id` coverage; aurora-metrics = exporter-compatibility stress sample (deliberately deviates from `viewport-base.css`) | Phase 3, when an end-to-end example helps |
| **Scripts** | | |
| `scripts/check_env.py` | verify deps (playwright/img2pdf/lxml + Chromium); accepts `--browser-executable` for an existing local browser | preflight |
| `scripts/audit_html_slides.py` | deterministic HTML-deck audit: clipped/offstage text, broken assets, fonts, geometry, blank pages; supports `--browser-executable` | Phase 3→4 gate, before every export |
| `scripts/export_pdf.py` | HTML → crisp lossless screenshot PDF (deliverable); fails closed on font/asset errors; supports `--browser-executable` and `--keep-pngs` | Phase 4 |
| `scripts/edit_texts.py` | extract/apply all deck text through one Markdown companion | Phase 6 |
| `scripts/extract_pptx.py` | visible PPTX pages → content JSON (generation input only) | Generate mode Phase 0; never native edit |
| `scripts/audit_pptx_page_numbers.py` | audit page-number sources across slides, layouts, and masters | native PPTX page-number/footer edits |
| `scripts/audit_pptx_structure.py` | manifest/compare PPTX order, hidden state, scope changes, and translation completeness | native edit baseline/final checks, version/order comparison, bilingual deck QA |
| `scripts/audit_pptx_properties.py` | fail-closed per-slide property allowlist for text/style/geometry/content changes | native minimal-edit verification after the final write |
| `scripts/audit_pptx_backups.py` | compare explicit source→hidden-backup pairs including dependent media/charts/notes | native edit tasks that require hidden original backups |
| `scripts/audit_pptx_typography.py` | inventory fonts/sizes/bold by semantic role and enforce expected peers | native font normalization and typography QA |
| `scripts/transplant_pptx_slides.py` | fail-closed, direct-format shape-tree transplant from a rewritten candidate onto the untouched baseline | high-level PPTX authoring tools that normalize hidden/order/shared package state |
| `scripts/render_pptx.ps1` | render visible or hidden native PPTX pages from a scratch copy via PowerPoint/WPS | native PPTX visual QA on Windows (non-Windows alternative: see visual-qa.md) |
| `scripts/make_contact_sheet.py` | align multiple render folders by physical slide number | source/target/translation/hidden-backup comparison |
| `scripts/audit_rendered_pages.py` | enforce physical-page or explicit source→target render mapping, authorized pixel changes, and coverage-risk checks | final native PPTX visual scope and hidden-backup audit |
| `scripts/validate_template_pack.py` | validate bold-template index, paths, and runtime contracts | skill/template maintenance |
| `scripts/validate_skill_structure.py` | validate routing, links, long-doc TOCs, and UI metadata | skill maintenance |
| `scripts/run_self_checks.py` | run skill validation plus every standalone regression test | after skill/script maintenance |
