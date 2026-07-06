# PPTX native editing guardrails

Guardrails and audit checklist for when native PPTX edits are performed in this
task (directly or via another tool). Read this before modifying a `.pptx`
package, copying native slides, translating PPTX content, hiding backup pages,
or comparing PPTX versions.

## Structural rules

- Use the presentation slide order from `ppt/presentation.xml` and
  `ppt/_rels/presentation.xml.rels`.
- Do not map pages by `ppt/slides/slideN.xml` filenames.
- Use structured OOXML APIs or XML parsing; avoid ad hoc string edits except for
  simple, verified text changes.
- Always keep backups before destructive edits.

## Shared master/layout risks

- Slide masters and slide layouts are often shared by many pages.
- Do not overwrite a shared layout to fix one page; it can change unrelated
  pages.
- If a page needs a copied reference layout, create or copy a separate layout and
  point only the intended slides to it.
- After changing layouts, inspect pages that use the same master/layout for
  regressions.

## Page numbers, footers, and inherited placeholders

Page numbers are not necessarily slide-local. Before adding, deleting, resizing,
or normalizing page numbers/footers, enumerate all possible visible sources:

- slide XML: `ppt/slides/slide*.xml`
- slide layout XML: `ppt/slideLayouts/slideLayout*.xml`
- slide master XML: `ppt/slideMasters/slideMaster*.xml`
- placeholder objects: `<p:ph type="sldNum">`
- field objects without placeholder markers: `<a:fld type="slidenum">`
- manually inserted numeric text boxes near the footer

Do not declare page numbers clean after checking only `ppt/slides`. Layout and
master inheritance can render a second page number even when the slide itself
has only one visible text box.

When replacing page numbers with a custom direct shape:

1. Remove old page-number sources from slides, layouts, and masters, or confirm
   they are intentionally hidden and cannot render.
2. Add exactly one direct page-number shape per visible slide with a stable name,
   fixed position, fixed font size, and `noAutofit`.
3. Verify the full package contains zero remaining `slidenum` fields and zero
   `sldNum` placeholders unless using the native placeholder system deliberately.
4. Render suspect pages after the last edit. XML checks catch inheritance bugs;
   visual checks catch overlap and app-specific rendering quirks.

Useful command:

```bash
python <skill-root>/scripts/audit_pptx_page_numbers.py <deck.pptx> \
  --expect-name dfn_page_number --expect-size 1100 --fail-on-inherited
```

## Copying slides or slide content

When copying native slides, copy the slide XML and its relationships:

- slide layout/master references
- images and media
- charts and chart relationships
- embedded OLE objects
- VML drawings and VML relationships
- tags
- `[Content_Types].xml` overrides/defaults

After writing the PPTX:

- run zip integrity checks
- check for duplicate zip entries
- open or export the deck in PowerPoint/WPS/LibreOffice
- verify page count and order

## Proofing marks

Canonical procedure when exported slides show spelling/grammar squiggles or
other proofing artifacts (referenced from `translation-copyfit.md` and
`visual-qa.md`):

1. Disable live proofing in the exporting app during export if possible.
2. Mark the affected runs as no-proof in the PPTX when appropriate.
3. Re-render the affected pages and confirm the marks are gone.

## Visual regressions to watch

- unexpected black backgrounds or white overlays
- missing or duplicated background art
- charts hidden behind shapes or text
- page numbers changed, duplicated, inherited from layout/master, or missing
- proofing marks appearing in exported images
- fonts silently substituted
- hidden backup slides becoming visible

XML/text checks are necessary but not sufficient. Render the changed pages.
