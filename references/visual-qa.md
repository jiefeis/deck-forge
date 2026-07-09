# Visual QA workflow

Read this for reformat, translation, or cross-format comparison tasks, before declaring the result complete. (Native deck generation runs are covered by workflow.md Phase 4's per-page verification.)

## Render-first verification

Do not rely only on text extraction, XML diffs, or DOM inspection. Build a visual
proof loop:

1. Render source/reference pages to PNG.
2. Render target pages to PNG.
3. Create a contact sheet for fast comparison.
4. Inspect full-size PNGs for every changed dense/suspect page.
5. Fix and rerender until clean.

Always inspect every page before delivery; contact sheets are for triage only.

## What to check

- final page count and order
- correct source-to-target mapping
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
- Every changed page has been rendered after the last edit.
- Pages changed for copy tone or font size have been inspected full-size, not
  only on a contact sheet.
