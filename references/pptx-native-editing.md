# PPTX native editing guardrails

Guardrails and audit checklist for when native PPTX edits are performed in this
task (directly or via another tool). Read this before modifying a `.pptx`
package, copying native slides, translating PPTX content, hiding backup pages,
or comparing PPTX versions.

Do not route a native-edit request through `extract_pptx.py` or rebuild it as an
HTML/PDF deck. Freeze the authorized slide/property scope using
`references/edit-scope-contract.md`, work on a copy, and compare before/after.

## Contents

- Structural and shared-layout rules
- Tool qualification and package-preserving rebase
- Typography baseline when adding or merging slides
- Page numbers, footers, and hidden-slide numbering
- Copying slides and relationships
- Proofing marks and visual regressions

## Structural rules

- Use the presentation slide order from `ppt/presentation.xml` and
  `ppt/_rels/presentation.xml.rels`.
- Do not map pages by `ppt/slides/slideN.xml` filenames.
- Use structured OOXML APIs or XML parsing; avoid ad hoc string edits except for
  simple, verified text changes.
- Always keep backups before destructive edits.
- Preserve each slide's hidden `show` state unless the scope explicitly changes
  it. Decide whether numbering follows physical slides or visible slides before
  adding page markers.

## Tool qualification and package-preserving rebase

Before trusting a high-level library for a source-preserving edit, perform a
no-op import/export on a scratch copy and compare it to the baseline. A library
is not qualified for minimal native edits when the no-op round trip changes
stable slide IDs, true order, hidden flags, notes, media dependencies, or shared
masters/layouts/themes.

ZIP order or XML serialization can differ without changing meaning, but
relationship IDs are only semantically equivalent when every reference still
resolves to the same relationship type, target mode, and dependency payload.
Never treat equal `rId` strings as proof, and never use `--allow-shared` to hide
an unexplained round-trip failure.

If the tool is useful for authoring the target pages but rewrites the package:

1. Keep its output as a candidate only.
2. Complete full-size visual and content/topology QA on the candidate pages.
3. Rebase the authorized slide-local component onto the untouched baseline:

   ```bash
   python <skill-root>/scripts/transplant_pptx_slides.py \
     <baseline.pptx> <candidate.pptx> <rebased.pptx> \
     --pages <target-pages> --component shape-tree
   ```

4. Use explicit `--map source:candidate` when their physical orders differ.
   Every mapping must be proven; equal slide counts are not identity evidence.
   A matching stable slide ID alone is never accepted (normalizing tools
   regenerate IDs positionally): corroborate it with matching titles, or —
   when the redesign legitimately changed the title — with reviewed
   `--expect-source-title` / `--expect-candidate-title` assertions.
5. Render the candidate and rebased target pages with the same engine. Their
   authorized target-page pixels must match before the candidate's visual work
   is considered preserved.
6. Run structure, property, page-number, and rendered-page audits on the
   rebased file.

The transplant is intentionally narrow. It keeps baseline slide relationships,
notes, order, stable IDs, hidden state, layouts, masters, themes, and package
parts. It reuses only dependencies already present on the baseline target slide
and fails on unmatched or ambiguous resources. It also rejects shape-tree-only
replacement when timing/comments/controls may bind to old shape IDs, or when
the candidate shape tree uses placeholders, scheme colors, theme fonts, or
style-matrix references that could change under the baseline layout/theme.
`cSld` and full-slide replacement are intentionally unsupported. Use a broader
copy workflow only after expanding the user's scope and proving the entire
dependency graph.

The static theme gate rejects only explicit theme markup; implicit inheritance
(runs with no direct properties) cannot be excluded statically. The tool
therefore reports a `required_followup` list — pixel equivalence of candidate
vs rebased renders and the baseline-scope re-audit — and the transplant is not
delivery-ready until both are done.

## Typography baseline when adding or merging slides

Mandatory whenever the task inserts newly authored slides into an existing deck,
merges slides from another deck, or fills template pages — run this BEFORE
authoring or copying anything:

```bash
python <skill-root>/scripts/audit_pptx_typography.py <target-deck.pptx>
```

Then:

1. If the target deck's same-role typography is already inconsistent (title,
   eyebrow/kicker, lead-in, source line, page number, or repeated body
   components varying in font, size, or weight across pages), report the
   inconsistency to the user before mutating, and ask whether new pages should
   (a) follow one stated canonical style, or (b) the whole deck should be
   normalized as part of the task. Do not silently pick a single reference page.
2. Never derive new-page styles by sampling one slide of an inconsistent deck;
   the result matches that slide and mismatches the rest.
3. When merging a slide from another deck, list its font families
   (latin/eastAsia/cs) against the target deck's. If they differ, tell the user
   and agree on keep-source-fonts vs harmonize before the merge — imported pages
   with foreign fonts (e.g. Arial + 思源黑体 into a 微软雅黑 deck) are a
   frequent silent mismatch, and they render differently on machines without
   those fonts installed.
4. Mojibake typeface names (e.g. `typeface="????"`) and an empty theme
   eastAsia typeface are latent substitution bugs; surface them in the same
   report even if outside the edit scope.
5. Re-run the audit on the final file and compare against the baseline; new
   pages must not introduce additional font families or size variants beyond
   the agreed canon.

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
2. Choose the numbering policy first: `physical` counts hidden slides; `visible`
   excludes them. Add exactly one direct page-number shape per page in that
   policy, with a stable name, fixed position, fixed font size, and `noAutofit`.
3. Verify the full package contains zero remaining `slidenum` fields and zero
   `sldNum` placeholders unless using the native placeholder system deliberately.
4. Render the full deck after the last edit and inspect affected/suspect pages
   full-size. XML checks catch inheritance bugs; visual checks catch overlap and
   app-specific rendering quirks.

Useful command:

```bash
python <skill-root>/scripts/audit_pptx_page_numbers.py <deck.pptx> \
  --mode auto --numbering physical
```

The default is strict: it fails on missing/duplicate direct markers, direct plus
inherited/native coexistence, sequence errors, duplicate ZIP parts, and corrupt
ZIP members. Use `--numbering visible` only when hidden pages intentionally do
not participate. Add `--expect-name` and `--expect-size` only after reading those
values from the actual deck; never bake a project name or old font size into the
generic workflow. Use `--mode native` for a deliberate inherited-placeholder
system and `--numbering none` only when checking source conflicts without
requiring page numbers.

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
- run `scripts/audit_pptx_structure.py` against the baseline with the authorized
  slide set; reject unexpected slide/shared-part changes
- run `scripts/audit_pptx_properties.py` with the frozen property scope; a page
  appearing in `--allow-slides` does not authorize unrelated text, geometry,
  media, notes, or animation edits
- when originals were duplicated and hidden, run
  `scripts/audit_pptx_backups.py` for every explicit source→backup pair
- open or export the deck in PowerPoint/WPS/LibreOffice
- verify page count, true order, hidden state, and every rendered page after the
  final write

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

XML/text checks are necessary but not sufficient. Render every visible page
after the final write; inspect changed/dense/suspect pages full-size.
