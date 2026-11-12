# Build or revise an HTML deck

Use this track for a fixed 1920 × 1080 web presentation and for static PDF delivery.
Record HTML, PDF or both as the deliverables. An HTML-only job ends after the browser checks.

## Contents

- [Revise selected slides or export an existing file](#revise-selected-slides-or-export-an-existing-file)
- [Plan the deck](#plan-the-deck)
- [Select the visual system](#select-the-visual-system)
- [Compose and verify](#compose-and-verify)
- [Requested outputs and later edits](#requested-outputs-and-later-edits)

## Revise selected slides or export an existing file

For a scoped revision, start from a byte-for-byte baseline and its SHA-256. Identify each target slide
and allowed property. `python scripts/forge.py preflight project/before.html --out scratch/baseline`
records the source hash and the slide count in Chromium. Patch those bytes, keeping untouched text, markup, motion, encoding and newline
style. A shared CSS token, selector or controller affects every page that uses it. Compare the file
actually written with the frozen source and check all affected pages and interactions. A colour-only
request permits only the named colour changes. The whole-document text round-trip below reserializes
the source and is unsuitable here. A direct export uses the existing HTML's parent as the asset
root. Report the exact missing paths if it cannot load a relative resource.

For a same-page-count edit, run `python scripts/forge.py verify-html project/after.html --source project/before.html --allow-slides 3 --out project/qa-revision`
with the authorized physical pages. It compares parsed slide markup and rendered pages. Inspect
the scoped source diff too, including any CSS or JS outside the slides.

## Plan the deck

- Read the supplied materials. Set the audience, decision or learning objective, speaking time,
  and whether the audience will have a presenter. A worked case should teach the user's intended
  transferable skill when that is the brief. A single-operation demonstration can stay a single operation.
- When a PPTX supplies material for a new deck, `python scripts/extract_pptx.py source.pptx scratch/input --visible-only`
  extracts visible content and images. Record the excluded hidden pages. Requiring original masters,
  editable data or paragraph-level PowerPoint editing changes the route to native PowerPoint.
- For an argument, submit a chain of conclusion titles with one evidence note per page. The titles
  should tell the story alone and each exhibit should support the title. Build on the user's confirmed
  chain or agreed outline. Use the [storyline examples](../assets/design/storyline.md) for a difficult
  recommendation, pitch, progress update or diagnosis.
- For each page identify the claim, primary visual, what it shows, its source and production status.
  Fit the page count to the evidence. A quote needs a source, a KPI needs a real value, unit and time
  period, and an illustrative example needs a label. Preserve approved blanks and unrevised source facts.
- Identify sequence, ownership, comparison, scale or feedback before choosing a layout. Use the
  [layout catalog](../assets/html/layouts.md) or the [worked text-to-visual examples](../assets/design/text-to-visual.md)
  as needed. For a relationship exhibit, trace the nodes, typed connections, split points and return
  edges against the source. The [diagram recipes](../assets/design/consulting-diagrams.md) include
  swimlanes, proportional value chains, driver trees and matrices.
- Produce the planned visuals before composing the page. Use an authentic photo, screenshot or
  attributable chart for evidence. Label generated concept art as illustrative. For an OCR source,
  check unclear text and every axis, unit, date and footnote against the image. Keep uncertainty visible.
  The [visual evidence guide](../assets/design/visual-evidence.md) includes crop, provenance and overlay examples.

## Select the visual system

Honor a supplied look or an already confirmed choice. Test it with real content, usually a dense
exhibit for a board deck. When the look is open, show three genuinely different one-slide previews
of the same page. Use a [style preset](../assets/html/style-presets.md), a candidate from the
[bold HTML catalog](../assets/bold-template-pack/selection-index.json), and a distinct third choice.
Use the catalog metadata to shortlist and read only each candidate's preview card. After selection,
open that template's `templates/<slug>/design.md` inside the pack. The selected recipe and the
HTML skeleton supply the implementation. Keep style names, file paths and preview labels off the slides.

Commit to one type hierarchy, palette and grid. Grid labels may repeat consistently. Reserve
the strongest emphasis for the decisive comparison, action or evidence. Keep a qualifier such as
“estimated” attached to the number it governs. Use a label, position or pattern when colour encodes
meaning. For CJK, use a font with
the required glyph coverage, zero letter spacing as a starting point, and natural clause breaks.
A table or text-only page is appropriate when exact lookup or wording is its job.

## Compose and verify

Inline the full [fixed-stage CSS](../assets/html/viewport-base.css) and use the
[HTML skeleton and controller](../assets/html/html-template.md). Place `.slide` elements in
`.deck-stage` and scale the stage as a unit. Keep CSS/JS inline and assets embedded or in a
relative folder that ships with the HTML. The [motion snippets](../assets/html/animation-patterns.md)
show reduced-motion and export behavior. Each slide must settle into a complete printable state.

Run from the skill folder with project paths, using a browser that can load the deck's fonts.
Use one Python environment for Playwright, img2pdf, lxml and Pillow. PPTX extraction or a PowerPoint
companion also needs python-pptx.

~~~sh
python scripts/check_env.py
python scripts/forge.py verify-html project/index.html --expect-slides 8 --out project/qa-html
~~~

Replace `8` with the actual agreed count, or omit that option. If managed Chromium is missing,
pass an installed Chrome/Chromium/Edge binary with `--browser-executable` or set
`DECK_FORGE_BROWSER_EXECUTABLE` for audit and export. For geometry details, run
`python scripts/audit_html_slides.py --help`. Investigate missing resources, fonts, clipping,
offstage text, large empty regions and overlap. Audit reports and advisory copy flags do not
establish that claims are correct or planned figures are present.

Open the final HTML and visit every page in a real browser. Inspect charts, image crops, navigation,
footer visibility and CJK breaks at a desktop and smaller viewport. Test next/previous boundaries
and background shortcuts. A clicked previous/next button must keep its own Enter/Space activation
and still support deck arrow/navigation shortcuts. Text inputs, links, editable regions, other
controls, modified keys and composition events keep their native keyboard behavior.

## Requested outputs and later edits

| Output | Procedure |
| --- | --- |
| HTML | Deliver the entry point with its relative assets and licensed fonts. For one-file output embed the necessary assets. State any actual font or network dependency. |
| PDF | `python scripts/export_pdf.py project/index.html project/slides.pdf --keep-pngs project/qa-pdf`. The screenshot PDF uses lossless PNG pages. Check the final PDF page count/dimensions, inspect all pages and verify the images use lossless compression (no `/DCTDecode`). `--compact` reduces resolution while preserving lossless compression. |
| Both | Run both checks and hand over the HTML source and its assets alongside the PDF. The PDF contains static page images. |
| Optional PowerPoint companion to existing HTML | `python scripts/export_pptx.py build project/index.html project/slides.pptx` converts supported elements into native objects. The recipient can edit supported text and tables. SVG charts become pictures and complex text layout can fragment. Choose `--image-only` only when the user wants full-slide images. |

For a companion, render every page with `python scripts/render_pptx.py project/slides.pptx project/qa-pptx`
and compare with the HTML captures using `python scripts/export_pptx.py diff project/qa-html/target project/qa-pptx`.
Inspect every difference at presentation size. If someone needs to reflow paragraphs or update chart
data routinely, author those objects directly in native PowerPoint. Use `--font` on the companion
build to choose the actual presentation font. The visual diff helper requires NumPy.

For an authorized whole-document wording revision, `python scripts/edit_texts.py extract project/index.html`
adds stable IDs and produces `index.texts.md`. Keep its markers while editing, then run
`python scripts/edit_texts.py apply project/index.html project/index.texts.md`. The tool writes a
backup by default. Recheck all pages, including font coverage for new glyphs, and rebuild only the
requested outputs. For two versions with the same pagination, `audit_rendered_pages.py` checks
pixel changes against `--allow-slides` and `make_contact_sheet.py` aligns the page images for inspection.
