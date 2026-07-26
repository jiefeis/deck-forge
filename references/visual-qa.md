# Visual QA workflow

Read this for reformat, translation, or cross-format comparison tasks, before declaring the result complete. (Native deck generation runs are covered by workflow.md Phase 4's per-page verification.)

## Contents

- Render-first verification and Windows renderer
- Pixel-scope audit and aligned contact sheets
- Hidden-backup rendering
- Content and topology fidelity
- Page-level visual checks
- Final delivery checklist

## Render-first verification

Do not rely only on text extraction, XML diffs, or DOM inspection. Build a visual
proof loop:

1. Render source/reference pages to PNG.
2. Render target pages to PNG.
3. Create a contact sheet for fast comparison.
4. Inspect full-size PNGs for every changed dense/suspect page.
5. Fix and rerender until clean.

Every physical page must appear in the QA set; never sample. Inspect the full
contact sheet as the first pass, then inspect every changed/dense/suspect page at
full size. If a shared master, layout, theme, or renderer changed, inspect every
page full-size because any page may have regressed.

For native PPTX, render from a scratch copy with one stable engine
(PowerPoint, WPS, LibreOffice, or the environment's presentation tool). Export
only; do not save the source through the renderer. Close only the app instance
created for the export, and never kill a user's existing Office/WPS process.
Use the same engine for source and target comparisons so app-specific font/theme
differences do not masquerade as edits.

On Windows with PowerPoint or WPS installed, the bundled renderer exports from a
scratch copy and verifies that the source hash is unchanged:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  <skill-root>/scripts/render_pptx.ps1 `
  -InputPptx <deck.pptx> -OutputDir <scratch/render>
```

For a native preservation task containing any hidden slide, run a second
baseline/final render with `-IncludeHidden`. The normal render verifies the
visible delivery; the include-hidden render verifies every physical page,
including protected hidden history—not only requested backup slides. Output
uses physical filenames such as `slide-006.png`, so visible-page gaps stay
explicit.

Create an aligned source/target contact sheet without shifting missing physical
pages into the wrong columns:

```bash
python <skill-root>/scripts/make_contact_sheet.py \
  --row source=<scratch/source> --row target=<scratch/target> \
  --output <scratch/contact-sheet.png>
```

Before manual inspection, run the full-pixel scope audit. It fails on missing
physical pages, unauthorized visual changes, and white/black/low-variance
coverage regressions:

```bash
python <skill-root>/scripts/audit_rendered_pages.py \
  <scratch/source> <scratch/target> --allow-slides <target-pages>
```

Legitimate near-solid covers or section dividers may be listed with
`--allow-solid-slides` only after full-size review. Do not use that option to
silence a new white overlay or black-background regression.

Normal exports may omit hidden slides. Prefer per-slide export such as
`render_pptx.ps1 -IncludeHidden`, which does not need to unhide them. If the
chosen engine cannot export hidden pages directly, unhide only a scratch copy,
render it, and discard it. The deliverable must retain the original hidden state.

When a hidden backup sits at a different physical index from its source, compare
the actual pair explicitly instead of renaming images or relying on adjacent
position. First verify its native content and dependent parts, then compare its
render:

```bash
python <skill-root>/scripts/audit_pptx_backups.py \
  <source.pptx> <final.pptx> \
  --map <source-page>:<backup-page>
python <skill-root>/scripts/audit_rendered_pages.py \
  <scratch/source> <scratch/final-with-hidden> \
  --page-map <source-page>:<backup-page>
```

Repeat `--page-map` for every backup. A missing mapped render, reused target
page, dimension change, or pixel mismatch fails the audit by default.

## Content and topology fidelity

Visual neatness is not semantic correctness. For a slide rebuilt from a mother
draft or relationship graph:

1. Trace every required claim, explanation, analogy, conclusion, and transition
   to a visible final element.
2. Convert the source graph into a node/edge/cycle checklist.
3. Verify every source edge appears once and every visible connector has an
   authorized meaning.
4. Confirm shared nodes remain shared, branch points are correct, and every
   feedback path returns to the intended node.
5. Reject arrow-character prose, duplicated proxy nodes that change meaning,
   open chains presented as loops, and connector directions that require
   guessing.

For complex flywheels or systems, ask an independent reviewer to trace the raw
source graph against the final full-size render. Give the reviewer the source
contract and artifact, not the suspected flaw. A reviewer catching a missing
return edge is a required edit, even when the slide already looks balanced.
When an independent reviewer is unavailable, do a fresh second-pass trace from
the raw adjacency list after a break from authoring.

When the user finds a recurring defect in a sample—such as arrow chains,
excessive whitespace, orphan punctuation, or weak visual relationships—scan the
entire deck for the same pattern. Report all occurrences; modify only those
covered by the authorized scope or ask before expanding it.

## What to check

- final page count and order
- authorized-change scope versus the before-edit manifest
- correct source-to-target mapping
- physical page, visible ordinal, displayed marker, and reference page recorded
  as four separate page-address fields when hidden pages exist
- every required content block and graph edge accounted for
- title hierarchy and subtitle placement
- no unexpected side notes or added explanation boxes
- background, bars, rules, page numbers, footers, and logos
- page-number uniqueness across slide, layout, and master inheritance when PPTX
  page markers are changed
- text clipping, wrapping, overlap, or line collisions
- orphan characters, awkward word breaks, and labels merged into body copy after
  font-size changes
- inconsistent sizes/alignment in repeated components such as Harvey balls,
  arrows, badges, numbered boxes, and icon rows
- chart and image visibility
- color shifts or theme-fill regressions
- hidden backup slides still hidden
- proofing marks or app UI artifacts in exports (handling: see
  `references/pptx-native-editing.md`)

## Contact sheet usage

Use rows such as:

- reference
- current target
- translated target
- hidden backup/exported source when available

A contact sheet finds gross mismatches. Full-size inspection catches text
collisions and subtle overflow.

## Final delivery checklist

- Final file path matches the user's requested path.
- No unintended extra deliverables remain in the delivery folder.
- PPTX zip check passes, no duplicate entries.
- PDF page count matches expected slide count.
- The final artifact opens in the target app.
- A final full-deck render was produced after the last write, and every visible
  page was inspected. Changed/dense/suspect pages were also inspected full-size.
- If the deck contains hidden slides, baseline and final were also rendered with
  `-IncludeHidden`; every hidden physical page was compared and remains hidden.
- Requested source→backup mappings were additionally verified when a backup
  sits at a different physical index.
