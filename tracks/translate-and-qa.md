# Translate, polish or compare a deck

For translation or an authorized copy edit, save a copy in the requested format. An ordinary PPTX
translation stays native. For an audit or version comparison, leave every input untouched. Keep
reports, manifests and renders in a separate working folder.

## Identify the pages and content

Record the exact source, target, hashes and operation. Compare actual content when names such as
“v2” and “final” are ambiguous. Map physical page, stable slide ID, hidden state, visible ordinal,
displayed marker, title, source page and content anchors. Use the package's presentation order.
For a native translation, obtain a baseline with
`python scripts/audit_pptx_structure.py manifest project/source.pptx --json -o scratch/before.json`.
Corroborate reordered versions by titles, distinctive content and render evidence. A true-order
fallback is provisional until the mapping is reviewed. Keep source facts, permitted terminology,
page-level exceptions, output format and authorized text properties explicit.

Read-only audit requests go straight to **Compare the saved artifacts**. Report differences by
physical page and element, distinguishing a hidden-state or package change from a visual change.
A problem found on a sample page warrants checking every page for that pattern. Keep the findings
and the authority to fix them separate.

## Translate and fit the existing roles

1. Inventory titles, subtitles, labels, body, captions, source notes, tables, chart titles, axes,
   series, categories, diagram labels and text embedded in images. Map each source role to its target.
   Preserve title intent (statement or question), a fused heading, emphasis, numbering, originals
   hidden for reference and any agreed verbatim wording. Verify OCR against the original pixels,
   especially minus signs, decimal separators, units, symbols and small legends.
2. Work on a copy. For PPTX, edit native text runs, table cells and chart fields while retaining
   source layout, paragraph structure, shape IDs, formatting and package relationships. Avoid
   exporters that normalize shared masters, hidden flags, IDs or unrelated parts. For HTML,
   patch only the authorized strings and preserve unrelated source bytes, encoding and line endings.
3. Translate for the actual reader. Shorten wording before reducing type, keep labels parallel,
   preserve qualifiers, dates, score scales and attributions, and keep role labels separate from
   their descriptions. Widen existing boxes or adjust breaks only if permitted. Check real CJK
   glyphs, punctuation, font fallback and paired English/Chinese labels. Use Unicode arrows for
   actual relationships and verify their rendered shapes.
4. For a wording polish, replace vague agency and promises with evidenced actions and owners.
   “业务与 IT 形成落地飞轮” might become “业务每周定验收口径，IT 安排上线” **if the source supports both**.
   Keep established product names and the client's vocabulary. A static copy finding is a prompt
   to read the passage in context. Review [client-facing copy examples](../assets/design/copy-examples.md)
   for diagnosis and proposal pages. If available, `humanizer-zh` can suggest phrase-level edits
   for a Chinese “去 AI 味” request. Preserve approved wording and review each suggestion in its box.
5. For chart text, run `python scripts/native_charts.py inspect project/source.pptx`. Use the
   returned physical page, shape ID and field names to create `{"edits":[{"page":1,"shape_id":"2","field":"series.0.category.0","from":"华东","to":"East"}]}`,
   substituting actual source values. Run `python scripts/native_charts.py apply scratch/current-candidate.pptx scratch/edits.json scratch/chart-translated.pptx`
   on the current candidate so earlier translations survive. Verify supported workbook-backed labels
   and values together with the visible chart. Account for labels inside images, SmartArt, or unsupported
   chart parts in a separate human review. Report any unresolved text and its exact location.

## Compare the saved artifacts

~~~sh
python scripts/forge.py verify-pptx project/translated.pptx --source project/source.pptx --allow-slides 1-8 --scope scratch/scope.json --target-language en --out scratch/translation-qa
~~~

Use the actual translated physical pages and property allowlist. For plain slide text on pages 1–8,
`{"version":1,"rules":[{"id":"translation","pages":"1-8","properties":["text"]}]}` illustrates the
scope. Review any native chart/workbook changes against their specifically authorized fields and
dependent parts. Include `media-data` only on slides that own the edited chart or workbook. Choose
`zh` for an English-to-Chinese target. For an independent read-only check,
`python scripts/audit_pptx_structure.py compare source.pptx target.pptx --allow-slides 1-8 --map-slides id --translation-check --target-language en --strict-translation`
checks slide and box completeness, question titles and language residue. Box matches use shape ID,
then a unique placeholder, then conservative geometry. Review page- and box-specific exceptions
for legitimate image-overlay reconstruction or retained names. `compare --help` describes the JSON
schema for `--translation-exceptions`. A chart label uses a key such as `chart:2/series.0.name`.
`allow_chart_terms` accepts a reviewed entry with its target page, exact key and full unchanged
text. Resolve broad, ambiguous and unused rules. A strict check on the supported structures still
needs a visual reading.

For a comparison without translation, `python scripts/forge.py verify-pptx target.pptx --source source.pptx --out scratch/compare`
leaves both inputs intact. Differences outside the given scope produce a nonzero exit and a report
that identifies them. To render
independently, use `python scripts/render_pptx.py source.pptx scratch/source --engine auto --include-hidden`
and render the target with the **same** PowerPoint, WPS or LibreOffice engine. The Windows bridge is
`scripts/render_pptx.ps1`. Compare the visible sequence and the physically addressed hidden pages,
including backups at a different index. Use `--backup-map N:M` on the verification command when
specific original-to-backup pairs are part of the contract. The native package must retain its hidden flags.

For HTML, run `python scripts/forge.py verify-html project/index.html --out scratch/html-qa` and
exercise the delivered pages in a browser. For PDF or mixed inputs, render the actual delivered files
to consistently sized page images. Use `python scripts/make_contact_sheet.py --row source=scratch/source --row target=scratch/target --output scratch/sheet.png`
for aligned review. With known mappings, `audit_rendered_pages.py` can compare explicit
`--page-map N:M` pairs, or enforce `--allow-slides` for aligned page sets. For mixed renderers or
formats, inspect metric and font differences visually rather than treating every changed pixel as an edit.

Read every page and inspect changed, dense or suspicious pages full-size. Check missing/extra boxes,
titles, residue, tone, line wraps, orphan glyphs, overlap, chart legends, small source notes, theme fills,
numbers, logos and repeated elements. Check colour-only distinctions in grayscale. For spelling
squiggles, disable live proofing during export or mark the relevant runs no-proof when authorized,
then rerender. Recheck the written file after any correction. Report remaining limitations, including
missing renderer evidence if only `--structural-only` could run. For modified files, confirm that
the delivered hash matches the last audited file.
