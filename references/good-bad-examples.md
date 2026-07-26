# Good and bad examples

Read this when deciding how to handle ambiguous reformat, translation, image, or
cross-format deck tasks.

## Contents

- Reformat and scope control
- PPTX version comparison
- PPTX page numbers and footers
- Translation and copyfit
- Image-based material
- PDF/HTML output
- Slide copy and font enlargement

## Reformat

Good:

- Classify an existing-PPTX request as Native edit, freeze target slides and
  allowed properties, and compare the result against the baseline manifest.
- Render baseline/final with the same engine and fail unauthorized page-level
  pixel changes before relying on a contact sheet.
- Pair the page-level check with a property scope so a background/font task
  cannot silently alter text, geometry, media, notes, or animation.
- Extract style tokens from reference slides, then apply background, typography,
  and palette while preserving layout.
- Before adding or merging slides, inventory same-role typography across the
  target deck and resolve any inconsistent canon instead of sampling one page.
- Keep original object positions unless text no longer fits.
- Duplicate and hide original pages when the user asks for a backup/comparison.
- Verify every hidden copy against its source using both OOXML dependency hashes
  and explicit cross-page pixel comparison before delivery.
- When hidden pages offset a mother draft, record physical page, visible
  ordinal, stable ID, title, and reference page before editing.
- Express a feedback system as one shared backbone plus explicit split and
  return edges; trace the final graph against the source adjacency list.
- If a high-level authoring tool normalizes the package, keep its output as a
  visual candidate and transplant only the authorized slide-local component
  onto the baseline.
- Recheck the live source hash before overwriting and verify that the delivered
  file hash equals the audited candidate.

Bad:

- Run `extract_pptx.py` and rebuild HTML when the user asked for a native,
  minimal PPTX edit; hidden backups and layout fidelity will be lost.
- Inspect a few pages or only changed pages after a shared layout/theme edit.
- Treat `--allow-slides 3,7` as permission to change anything on pages 3 and 7.
- Redesign every slide into a new composition when the user only asked for
  background/color/font changes.
- Add a right-side explanation box that did not exist in the source layout.
- Change page order because XML slide filenames appear out of sequence.
- Update a shared PPTX layout and accidentally affect unrelated pages.
- Check only that backup pages are hidden without proving they still match the
  pre-edit originals and their dependent images/charts/notes.
- Copy foreign-font slides into an inconsistent target deck without first
  comparing Latin/East-Asian typefaces, sizes, and unresolved theme fonts.
- Treat physical page 31 as mother-draft page 31 after a hidden page was
  inserted, despite mismatched title/content anchors.
- Duplicate the shared D/A nodes to make two open rows and call them a
  "double flywheel" without visible return edges.
- Overwrite a source the user changed mid-session with a stale candidate.
- Silence order/hidden/master churn with `--allow-shared` because untouched
  slide renders happen to be pixel-identical.

## PPTX version comparison

Good:

- Compare candidate decks by page count, true slide order, and title/content
  fingerprints.
- Identify which pages are added, removed, reordered, or content-changed.
- Ask before deleting or reordering many pages if two sources could both be
  correct.

Bad:

- Assume `(2)` is newer or `v3` is the intended source without comparison.
- Compare only filenames and timestamps.
- Treat slide 41 in one deck as corresponding to slide 41 in another deck when
  content differs.

## PPTX page numbers and footers

Good:

- Audit page-number sources in slides, slide layouts, and slide masters before
  adding or resizing page numbers.
- Choose physical or visible numbering explicitly when hidden slides exist.
- Treat both `<p:ph type="sldNum">` placeholders and `<a:fld type="slidenum">`
  fields as page-number sources.
- If using custom direct page numbers, remove inherited layout/master page
  markers and verify exactly one page-number source per slide.

Bad:

- Trust a default audit that does not fail on duplicate direct markers, or bake a
  project-specific shape name/font size into a supposedly generic command.
- Add direct page-number text boxes while native layout/master page numbers are
  still active.
- Claim there are no duplicates after checking only `ppt/slides/slide*.xml`.
- Rely on WPS/PowerPoint visual impressions without tracing where each page
  marker originates.

## Translation

Good:

- Produce a source/target manifest and account for every title, label, body box,
  caption, and footnote before judging the translation complete.
- For a rebuilt chart, approve overlay/missing text boxes with page-scoped,
  reviewed translation-exception rules that fail when unused.
- Translate the message into concise, natural target-language phrasing.
- EN→ZH: render "Ship early, learn fast" as 「尽早发布，快速验证」 — what a
  Chinese presenter would actually say.
- Preserve title logic and box hierarchy.
- Shorten copy, render, and verify every translated page.
- Adjust wording when the translation overflows rather than simply shrinking
  all fonts.

Bad:

- Translate literally and leave awkward phrasing.
- Silence all extra/missing text boxes with a broad wildcard instead of mapping
  or reviewing the intentional chart reconstruction.
- EN→ZH: render "Ship early, learn fast" as 「运送早，学习快」 — a
  word-for-word gloss.
- Split a source headline into a theme label plus side note when the source uses
  one headline.
- Declare success after text extraction without checking rendered slides.

## Image-based source material

Good:

- Use the image as reference, rebuild important text as editable text, and keep
  charts/images only where rebuilding would be wasteful.
- Preserve a white source background when the requested output should remain
  white.
- Check OCR output against the image manually.

Bad:

- Paste screenshots as full-slide images when the user needs editable PPT.
- Add decorative backgrounds that conflict with the source.
- Enlarge low-resolution screenshots until text becomes blurry.

## PDF/HTML deck output

Good:

- Use fixed 1920x1080 HTML, render lossless screenshot PDF, inspect all pages,
  and keep HTML for edits.
- Explain that screenshot PDF text is not selectable.

Bad:

- Deliver only HTML when the user asked for a PDF.
- JPEG-compress slide pages and make text fuzzy.
- Trust a browser preview without checking the actual exported PDF pages.

## Slide copy and font enlargement

Good:

- Use `humanizer-zh` when Chinese slide copy is described as having "AI 味".
- Replace slogan-like copy with concrete presenter language while preserving
  facts, scores, dates, owners, and slide hierarchy.
- After increasing fonts, render the changed pages and fix orphan characters,
  awkward word breaks, and text box overflow.
- Keep repeated visual components, such as Harvey balls and process arrows, the
  same size and aligned on a shared axis.

Bad:

- Make the copy more ornate or literary when the problem is AI-sounding
  consulting prose.
- Use a global font multiplier and skip page-by-page copyfit.
- Merge labels and descriptions into one paragraph when the source uses separate
  hierarchy.
- Leave process arrows or Harvey balls visually "close enough" with inconsistent
  sizes or alignment.
