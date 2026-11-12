# Author or minimally edit a native PowerPoint file

Use PowerPoint objects for repeated paragraph edits, tables, or chart data. A new presentation built
on an existing template inherits its real masters, layouts and theme. Deliver the edited `.pptx`.

## Contents

- [Freeze the baseline](#freeze-the-baseline)
- [Make the requested change](#make-the-requested-change)
- [Keep the original package](#keep-the-original-package)
- [Verify after the final write](#verify-after-the-final-write)

## Freeze the baseline

1. Work from a copy. Record source and final paths, SHA-256, package slide count and order, targets,
   allowed properties, numbering policy, and requested hidden backups. Use an explicit output path.
2. Make a baseline manifest. Resolve physical order from `ppt/presentation.xml` through the presentation
   relationships. Slide XML filenames and displayed page numbers can have a different order.
3. When pages were inserted, hidden or renumbered, map each target's physical page, stable slide ID,
   hidden state, visible ordinal, displayed marker, title and corresponding source page. Corroborate
   by content. Keep hidden slides in the manifest and QA even if the authoring source is visible-only.
4. For each redesigned page, map required claims, reasons, evidence, analogies and conclusions to
   visible elements. The mother draft supplies the teaching sequence, the case material supplies
   the evidence and the current PowerPoint owns the package. Recheck all affected mappings after
   a source revision.

~~~sh
python scripts/audit_pptx_structure.py manifest project/before.pptx --json -o project/qa/before.json
~~~

Freeze property scope as well as page scope. For example, a title rewrite on physical page 3 needs
a `scope.json` containing `{"version":1,"rules":[{"id":"rewrite","pages":"3","properties":["text"]}]}`.
Retain the title's shape identity and unchanged runs. For an explicitly inserted slide use
`target_pages` or `target_slide_ids` with `order`. The property families are `text`, `typography`,
`color`, `background`, `geometry`, `shape-tree`, `relationships`, `media-data`, `notes`, `timing`,
`hidden`, `order` and `other`. Shared layout, master, theme or canvas changes require their own explicit scope.

## Make the requested change

**Minimal edit or reformat.** Change the specified text runs, shapes or style properties on the
named slides. Preserve hierarchy, dimensions, geometry, hidden state, notes, animations, chart parts
and other relationships unless the task authorizes their change. A shared layout can affect many
pages. Prefer a slide-local fix. Copy or isolate a layout only within the approved scope. A visual
restyle takes its role sizes, palette, rules, margins, page furniture and rhythm from the reference.
For larger type, inspect the font roles, shorten copy when authorized, then adjust boxes or line
breaks within scope and check wrapping at full size.

**New editable pages.** Start from the actual presentation or an empty native presentation if no
template was supplied. Inventory layouts across all source masters, the layouts the deck actually
uses, placeholder roles and dimensions, slide archetypes and shared media. Keep suitable existing
pages such as the cover, contact slide or logo wall. Map new pages to a native layout, claim and
primary visual. For an argument, confirm a chain of conclusion titles with evidence notes before
building pages. Keep typography and layout-density decisions the user has already confirmed.

Before adding, filling or merging slides, run `python scripts/audit_pptx_typography.py project/before.pptx`.
Read same-role variance, theme/script faces and the incoming deck's fonts. If those conflict, report
the specific choice of canon or keep/harmonize behavior before mutating. Recheck the selected roles
afterward. Keep existing masters/layouts/theme and their dependencies when stripping unused pages
on a copy. Remove slide relationships and their entries in `sldIdLst` together, then check the
removals and open the stripped copy. Use actual text frames, linked native chart workbooks, tables,
and editable diagram shapes with connectors when recipients need to maintain them. Check the
recipient can edit a sample paragraph, table cell or series value as requested.

Copy styled native shapes/groups with fresh shape IDs. Copy image/chart/OLE/VML relationships and
content types as needed. Control text insets explicitly in narrow labels, center words over the
painted part of an arrow and position label/body pairs from their wrapped height. When cloning
pages, `sldNum`/footer/date placeholders may need copying separately. Inspect slide, layout and
master placeholders, `slidenum` fields and direct footer text for duplicate or missing markers.
Run `python scripts/audit_pptx_page_numbers.py project/after.pptx --mode auto --numbering physical`
with the actual numbering policy. Use native mode for a deliberate inherited system. For authorized
redesigns, the [diagram recipes](../assets/design/consulting-diagrams.md) cover shared backbones,
branches, return edges and proportional shapes. Trace each connector against the raw source in both
directions. Use a fresh second pass when reviewing a complex graph.

**Existing native charts.** `python scripts/native_charts.py inspect project/before.pptx` lists chart
addresses, supported fields, formulas and workbook status. The editor supports existing data points
in column, bar, line and scatter charts. Select the real physical page, shape ID
and field. For example, an existing field might accept this plan:

~~~json
{"edits":[{"page":1,"shape_id":"2","field":"series.0.category.0","from":"华东","to":"East"}]}
~~~

Run `python scripts/native_charts.py apply project/before.pptx project/edits.json project/after.pptx`.
Use the inspector's field addresses for titles, axes, series, categories and values. Reinspect the
saved package and open Edit Data when available. Preserve chart type, formulas, untouched data and
formatting. Report a field, range or workbook that the editor rejects. Do not flatten the chart or
silently adjust only the displayed cache. Give only the owning page(s) the `media-data` property in
the verification scope for changed chart XML/workbooks, plus `text` if slide text also changed.
The field-level edit plan and readback establish what changed inside that page-level permission.

## Keep the original package

Qualify an unfamiliar editor with a no-op import/export on a scratch copy. Check for churn in
stable IDs, true order, hidden flags, notes, relationships and shared parts. Equivalent relationship
IDs must resolve to the same type, mode and content. When the tool rewrites these, use its output as
an authoring candidate and keep the original package as the baseline.

For a direct-formatted shape tree whose dependencies already exist on the baseline target slide,
`python scripts/transplant_pptx_slides.py project/before.pptx scratch/candidate.pptx project/after.pptx --pages 3 --component shape-tree`
rebases only the authorized component. Use `--map source:candidate` if physical orders differ,
with corroborated titles or deliberate source/candidate title assertions. Ambiguous or new dependencies,
placeholder/theme inheritance and bindings to old shape IDs need a dependency-aware native editor.
After a transplant, render candidate and rebased pages with the same engine and verify equal target
pixels, then rerun the baseline scope checks. A visually similar contact sheet cannot waive package drift.

## Verify after the final write

~~~sh
python scripts/forge.py verify-pptx project/after.pptx --source project/before.pptx --allow-slides 3 --scope project/scope.json --out project/qa-native
~~~

Pass `--backup-map N:M` for each requested source-to-hidden-backup pair. Use `--numbering` for
specified page markers and `--expect-font ROLE=FONT,SIZE,BOLD` for a confirmed role. Use the same rendering
engine for both files. The bundle checks the package and authorized changes, and provides page images
and an aligned contact sheet for review. Use PowerPoint/WPS on Windows or LibreOffice Impress with
`pypdfium2` and Pillow. Where applicable the individual checks are
`audit_pptx_structure.py`, `audit_pptx_properties.py`, `audit_pptx_backups.py`,
`audit_pptx_typography.py`, `audit_pptx_page_numbers.py` and `audit_rendered_pages.py`.
New decks without a source use `verify-pptx` on the output alone. For insertions or reordering,
compare aligned physical page pairs using proven source/target mappings and check the actual new pages.

Inspect all visible and hidden pages, with full-size review for changed, dense or suspect content.
If a master, layout, theme or renderer changed, inspect the whole deck full-size. Check font fallback,
orphan glyphs, repeated icons, cover/background changes, obscured charts, proofing marks and inherited
numbers. Re-scan the entire deck for recurring issues found in a sample and repair only authorized
pages. Hidden renders belong in scratch. Verify backups' native dependencies and pixel matches.
An explicit `--structural-only` run reports no rendered coverage. Disclose the missing inspection if
a renderer is unavailable. Recheck the live-source and delivered hashes before handover.
