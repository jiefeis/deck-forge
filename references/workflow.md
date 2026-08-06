# deck-forge — full workflow

Detailed Phase 0–6 reference for `SKILL.md`. The main file holds the trigger,
non-negotiables, preflight/commands, and one-line-per-step routing; this file is
the expanded version of each step. Read it for **Generate mode only** (Phase
0–6). Native PPTX edits and read-only comparisons use the cross-format route in
`SKILL.md` and do not enter these phases.

Script commands below use `<skill-root>/` — the absolute path of the folder
containing `SKILL.md`, as defined in its Preflight section (do not use `~` on
Windows). Write generated deck HTML/PDF into the **user's** working directory.

## Contents

- Design Aesthetics
- Phase 0: intake and generation-only PPTX input
- Phase 1: map the storyline
- Phase 2: style discovery
- Phase 3: generate the HTML deck
- Phase 4: render and verify the PDF
- Phase 5: deliver
- Phase 6: edit the words

## Design Aesthetics

You tend to converge toward generic, "on-distribution" output — the "AI slop"
look. Resist it. Choose beautiful, deliberate typography — webfonts from
Fontshare / Google Fonts by default; a brand or locally installed font is right
when the user's brand, offline delivery, or CJK glyph coverage requires it, and
a default-look font picked out of convenience is never right. Commit to a
cohesive palette with dominant colors and sharp
accents over timid even distributions; draw from IDE themes and cultural
aesthetics. Use motion for high-impact moments (one staggered page-load reveal
beats scattered micro-interactions). Build atmosphere with layered gradients,
patterns, and contextual effects rather than flat fills. Avoid overused fonts,
purple-gradient-on-white clichés, predictable card/dashboard layouts, and
cookie-cutter design. Vary between light and dark, and across decks.

---

## Phase 0: Intake — materials + theme

The user comes in with two things; pull both out of the request, and ask only
for what is genuinely missing.

1. **Materials** — the content. Could be: pasted notes, an outline, a file/folder,
   a `.pptx`, or just a topic. If it's a `.pptx`, see "PPTX input" below. If it's
   "topic only", you will draft the content in Phase 3. Drafting boundary:
   framing, explanations, and clearly illustrative examples are fine; invented
   specifics presented as real are not — no fabricated numbers, dates, named
   customers, quotes, or benchmark claims. A fact only the user can supply gets
   an explicit placeholder (e.g. "[Q3 revenue]"), not a plausible guess.
2. **Theme** — the subject AND/OR the desired look. "A theme" may mean the
   subject matter, a vibe ("clean and corporate", "bold and editorial"), or a
   named preset/template. Capture whatever the user gave.

Then confirm the few things that change the build, in ONE message (use a
structured-question UI if available):

- **Purpose** — pitch / teaching / conference talk / internal report
- **Length** — short (5–10) / medium (10–20) / long (20+)
- **Density** — *speaker-led* (big ideas, few words, more slides) vs
  *reading-first* (self-contained, denser slides). This drives slide count, type
  scale, and words per slide. See `AUTHORING.md` → "Plan the page sequence".

If the user already implied any of these, don't re-ask — proceed.

### PPTX input for a new generated deck (optional)

Use this only when the user wants to repurpose visible PPTX content into a new
HTML/PDF deck. Do not use it for source-preserving native edits, reordering,
translation, font cleanup, hidden backups, or minimal changes.

`python <skill-root>/scripts/extract_pptx.py <input.pptx> <output_dir> --visible-only`
(needs `pip install python-pptx`). It writes `extracted-slides.json` + an
`assets/` folder of images. Summarize the extracted titles/content/images for the
user, confirm that hidden pages were excluded, then treat that as the materials
and continue.

### Reformat / cross-format input

If the request involves PPTX/PDF/images/HTML, screenshots, translation, visual
comparison, or "reformat/restyle", start with `references/source-contract.md`
and then read the task-specific files named in `SKILL.md`'s Files table before
planning edits. Establish the source of truth, final format, page count/order,
and whether layout must be preserved.
If a dedicated PPTX-editing skill/tool is available in this environment, prefer
it for native slide edits; otherwise follow `references/pptx-native-editing.md`
to edit the OOXML directly and audit with
`<skill-root>/scripts/audit_pptx_page_numbers.py`.

If the selected mode is Native edit or Audit/compare, stop this generation
workflow here. Follow `references/edit-scope-contract.md` and the relevant
cross-format references instead of Phase 1–6.

---

## Phase 1: Map the storyline

Before any design, read ALL the materials and lay out the deck structure
(`AUTHORING.md` → "Establish the source boundary" and "Plan the page
sequence"):

- How many sections? How many points per section?
- For each page, name its **information shape** (parallel items / contrast / data
  / timeline / hierarchy / single stat / quote / explanation+visual / chapter
  break), then pick a matching layout from `LAYOUTS.md`.
- Decide deck rhythm: cover → (agenda if long) → sections → content sized to
  shape → closing (`AUTHORING.md` → "Plan the page sequence").

Confirm the outline with the user (one structured question: looks good / adjust
outline / adjust scope). If images were provided, co-design the outline around
them — design with both text and images from the start, don't bolt images on
later.

---

## Phase 2: Style discovery

If the user already gave a clear theme/look, honor it — generate ONE preview to
confirm direction, then proceed. Otherwise do visual discovery:

1. Read `STYLE_PRESETS.md` (12 safe presets) and, if present,
   `bold-template-pack/selection-index.json` (compact bold-template index). Do
   **not** read any `design.md` yet.
2. Generate **3 distinct single-slide HTML previews** of a real first slide:
   1 safe preset, ≥1 bold template, 1 wildcard (a second template or a free
   custom design). Make them genuinely different. Match purpose / audience / mood
   / density.
3. **Preview authenticity (non-negotiable):** a preview must look like a real
   first slide of THIS deck. Never render workflow/meta text on a slide — no
   "preview", "Option A/B/C", "wildcard", preset/template/slug names, file paths,
   or requirement notes. Style names go only in your message to the user.
4. Save previews to `.deck-forge/slide-previews/` (`style-a.html`, …), open them,
   and ask which they prefer (or "mix elements").

For a shortlisted bold template, read only its `preview.md` for the preview; read
its full `design.md` only after the user picks it (Phase 3).

### Preview file protocol

Applies to every preview slide, template-based or not:

- Build exactly one title slide at 1920×1080 inside the fixed-stage model,
  preserving the template's palette, type roles, and decorative vocabulary as
  described in its `preview.md`.
- Previews render only real deck content (see preview authenticity above). All
  visible chrome — dates, page numbers, section labels — must come from the
  user's real material.
- CJK previews: keep CJK letter-spacing at 0, loosen line-height, and avoid
  uppercase transforms on CJK runs. If the deck's language is CJK, render the
  preview in that language. After selection, follow the chosen design's CJK
  section for exact font pairings and script-specific adjustments.
- `template.html` files are not bundled with this skill. If a selected
  `design.md` is missing a critical implementation detail, fill it in from
  `html-template.md`'s architecture plus the design's own token tables — do not
  search external repositories.

---

## Phase 3: Generate the HTML deck

Build the full deck using the Phase 1 outline + Phase 2 style.

**Read before generating:**
- `viewport-base.css` — mandatory fixed-stage CSS; include its FULL contents in
  the deck's `<style>`.
- `html-template.md` — HTML structure, slide markup (`.slide`/`.active`),
  navigation JS, code-quality standards.
- `animation-patterns.md` — animation snippets for the chosen feeling.
- `AUTHORING.md` — the discipline rules. Apply them per slide.
- The selected bold template's `design.md` (if one was chosen).

**Requirements:**
- One HTML entrypoint with all CSS/JS inline; assets may be embedded or stored in
  a local relative assets folder served alongside it.
- Include the FULL `viewport-base.css` so `.slide`/`.active` and the print stage
  behave correctly (the PDF exporter relies on `.slide` + `.active`).
- Every slide is a `<section class="slide">` (or `<div class="slide">`) inside the
  `.deck-stage`. Use `.reveal` for load-in animations.
- Fonts: Fontshare/Google Fonts webfonts by default; brand or locally installed
  fonts when brand, offline delivery, or CJK glyph coverage requires them. Verify
  the chosen fonts actually load — a fallback-rendered deck fails Phase 4.
- One coherent design system across all slides (`AUTHORING.md` → "Build one
  visual system").
- Comment each section: `/* === SECTION NAME === */`.

**Then self-check against `AUTHORING.md`:** the accidental-void and
overflow/overlap rules ("Fit content without fabrication"), and the
no-fabrication source boundary ("Establish the source boundary"). Then run
the deterministic audit before rendering:

```bash
python <skill-root>/scripts/audit_html_slides.py <deck-name>/index.html
```

It fails hard on clipped text, text crossing the stage boundary, broken
images, failed fonts, wrong slide geometry, and blank slides — fix those in
the HTML before exporting (deliberate bleed past the stage edge or a
deliberate text mask can be excused with `--allow-offstage-text` /
`--allow-clipped-text` after you have looked at it). Treat its warnings
(text overlap, empty bottom) as a checklist for the visual pass. It cannot
judge design intent: the Phase 4 page-by-page inspection still happens.

Save the deck to a working folder, e.g. `<deck-name>/index.html`.

---

## Phase 4: Render the PDF (the deliverable)

This is the point of the skill. Render the HTML deck to a screenshot PDF:

```bash
python <skill-root>/scripts/export_pdf.py <deck-name>/index.html [<deck-name>/<deck-name>.pdf]
```

- The exporter serves the deck folder locally, activates each `.slide`, forces
  `.reveal` elements to their final state, screenshots each slide at **2× device
  scale** (3840×2160 — supersampled for sharp text), and assembles them into one
  **lossless** PDF (one slide per page) with `img2pdf` (FlateDecode).
- **Crispness matters:** do NOT JPEG-compress pages — that mushes text edges and
  is what makes a screenshot PDF look "rough". `img2pdf` embeds the PNGs without
  recompression. (If you ever see `DCTDecode` in the PDF, something re-encoded to
  JPEG — fix it.)
- Requires `playwright` + `img2pdf` and a Chromium binary
  (`python -m playwright install chromium`, one-time ~150MB download).
- **Font/asset failures fail the export** — a failed font, stylesheet, image,
  or script request (or an errored FontFace) means the capture would silently
  use fallback fonts or missing assets, which changes line breaks and metrics.
  The exporter aborts by default; fix the loading problem instead of reaching
  for `--ignore-resource-errors`. Pin the families the design depends on with
  `--require-font "<Family>"` (repeatable).
- File size: ~0.7MB/slide at 2×. For a smaller file (email/Slack) use
  `--compact` (= `--scale 1`, ~half the size, still lossless and crisp at 100%),
  or `--scale 3` for print. Offer `--compact` if the PDF exceeds ~10MB.
- The PDF preserves colors, fonts, gradients, and the FINAL state of animations.
  It is a static snapshot — say so, so the user isn't surprised that motion isn't
  interactive, and that PDF text isn't selectable (each page is an image; to
  change words, use Phase 6).

**Verify the PDF before delivering:** open the produced PDF (or the screenshot
pages) and check every slide — no overflow, no overlap, no clipped text, no
empty-bottom slides, no fabricated content, no off-canvas objects, no missing
fonts/images, consistent page dimensions, and no unexpected animation state
(the exporter deactivates animations globally and forces reveals to their final
state, but confirm visually — a half-faded or blurred element is a bug). If a
slide is wrong, fix the HTML and re-run Phase 4. The PDF is what the user
receives, so it must be clean. This Phase is the single authority for PDF
output rules.

For reformat, translation, or mixed PPTX/PDF/image tasks, also follow
`references/visual-qa.md`: render source/reference and target pages, compare
visually, and verify the full affected page set rather than relying on text/XML
checks alone.

---

## Phase 5: Deliver

1. Clean up `.deck-forge/slide-previews/` if it exists.
2. Open the PDF for the user (if the environment can display files; otherwise
   report the absolute path).
3. Tell them: PDF location + size, style name, slide count; that the HTML
   intermediate is kept alongside it for edits; that motion is captured at its
   final state.
4. Offer the natural next steps: edit the words (Phase 6), revise
   content/structure, retheme (re-run Phase 2 + 3), or re-export `--compact` for a
   smaller file. Any HTML edit goes back through the audit gate
   (`audit_html_slides.py`, Phase 3) and then Phase 4 — an edit can introduce
   exactly the clipped/offstage overflow the gate detects.

For a revision round, produce page-level evidence of what changed instead of
asking the user to eyeball two PDFs: export each version with
`--keep-pngs <scratch>/v1` / `--keep-pngs <scratch>/v2`, then

```bash
python <skill-root>/scripts/make_contact_sheet.py \
  --row v1=<scratch>/v1 --row v2=<scratch>/v2 --output <scratch>/diff.png
python <skill-root>/scripts/audit_rendered_pages.py \
  <scratch>/v1 <scratch>/v2 --allow-slides <changed-pages>
```

The pixel audit proves only the intended pages changed (same-slide-count
revisions; if the page count changed, use the contact sheet alone).

---

## Phase 6: Edit the words (text round-trip)

Because the PDF is a screenshot, its text is not editable in the PDF itself — you
change the words in the source and re-export. `scripts/edit_texts.py` makes this a
clean one-file round-trip (the bundled `data-text-id` mechanism, with IDs
auto-injected so it works on any deck):

```bash
# 1. pull every string into an editable file (also stamps stable ids into the HTML)
python <skill-root>/scripts/edit_texts.py extract <deck>/index.html
# 2. the user edits <deck>/index.texts.md (change words; leave the id-marker comments)
# 3. write the edits back into the HTML
python <skill-root>/scripts/edit_texts.py apply <deck>/index.html <deck>/index.texts.md
# 4. re-run the audit gate (longer wording can newly clip or overflow), then
#    regenerate the PDF
python <skill-root>/scripts/audit_html_slides.py <deck>/index.html
python <skill-root>/scripts/export_pdf.py <deck>/index.html
```

- Each editable string keeps its inline tags (line breaks, `<em>`, accent
  `<span>`) so highlights survive an edit.
- `extract`/`apply` write a one-shot `<file>.bak` backup before modifying the
  HTML in place (pass `--no-backup` to skip).
- Use this when the user wants wording/copy changes without touching layout. For
  structural or visual changes, edit the HTML directly (or re-run Phase 3).
- NOTE: frontend-slides' in-browser inline editing (press `E`, click text) is
  **not bundled** in this skill — `edit_texts.py` is the supported text-editing
  path here. If a user specifically wants click-to-edit in the browser, add the
  edit-mode JS to the generated HTML on request; don't assume it's already there.
