# Template-native authoring

Read this when the deliverable is a PPTX made mostly of NEW pages authored on an
existing deck's or template's own masters, layouts, and theme. This is Native
edit with an authoring-sized scope: `source-contract.md` and
`edit-scope-contract.md` still govern, and the scope contract records kept
pages, deleted pages, added pages, and each added page's layout.

## Contents

- Strip the source, keep the design system
- Inventory native layouts before authoring
- Reuse template pages before rebuilding them
- Copy styled shapes, refill text
- Native text-frame mechanics
- Page numbers on added slides
- Storyline, fit, and QA routes

## Strip the source, keep the design system

When the source is a full deck rather than a bare template, strip it on a copy:

- Remove unwanted slides through the presentation part — drop each slide's
  relationship and its `sldIdLst` entry — never by slide-filename arithmetic.
  Removing the entry alone leaves the slide part and its media in the package.
- Keep every master, layout, and theme, plus all media they reference. Only
  slide-local media of removed pages may go.
- Run a zip-integrity check and `audit_pptx_structure.py compare` against the
  original; the diff must be exactly the declared removals. Open the stripped
  file in the target app before authoring on it.

## Inventory native layouts before authoring

Count which layouts the source actually uses before choosing any:

    from collections import Counter
    from pptx import Presentation
    p = Presentation(r"<source.pptx>")
    used = Counter(s.slide_layout.name for s in p.slides)
    for name, n in used.most_common():
        print(f"{n:5d}  {name}")
    print("unused:", [l.name for m in p.slide_masters
                      for l in m.slide_layouts if l.name not in used])

Map every planned page to a native layout, and confirm the page → layout
mapping together with the outline before building anything. Follow the source's
own distribution: a deck authored entirely on one layout when the source
alternates several reads as monotony, not restraint. Inspect each candidate
layout's placeholders and non-placeholder furniture (rules, side text, footers)
so the new page inherits the chrome instead of redrawing it.

## Reuse template pages before rebuilding them

Before authoring a page, check whether the source already has a page doing that
job — cover, back cover, client-logo wall, org or capability chart, contact
page. Keep the original page and edit its text. Original pages carry real assets
(logos, photographs, custom art, charts) that a rebuild silently downgrades to
text. Rebuild only when no existing page matches the content shape, and list
kept-as-is pages in the scope contract.

## Copy styled shapes, refill text

Author in the template's own language: deep-copy a styled shape or group
(`p:sp` / `p:grpSp`) from a template page into the new slide and replace its
text. Fill, line, corner radius, font stack, and custom geometry come along for
free, where redrawing only approximates them. Give each copy a fresh shape id.

If the copied shape references media, charts, or OLE objects, copy its
relationships too (`pptx-native-editing.md` → "Copying slides or slide
content"); a plain XML deep-copy leaves dangling references. Run the typography
baseline before authoring and re-audit after (`pptx-native-editing.md` →
"Typography baseline"): added pages must not introduce font families or size
variants beyond the agreed canon.

## Native text-frame mechanics

A slide has no layout engine. Three failures recur, and all three surface in
`visual-qa.md` as orphan characters, bad breaks, or labels merged into body
copy — fix the cause, not the symptom.

- **A shape's bounding box is not its ink.** Rotated or pointed autoshapes
  (`homePlate`, chevrons, arrows, callouts) leave unpainted zones inside the
  box, and the painted area can vary along the shape. Text centred in the box
  can sit off the fill. Anchor text to the painted region and verify on a
  render; coordinates alone will not show it.
- **Text frames carry default insets** of 0.1 in left/right and 0.05 in
  top/bottom — about 29 px horizontally on a 1920-wide slide. A narrow label box
  wraps into one-character lines until `lIns`/`rIns` are set explicitly or the
  box is widened to fit text plus insets.
- **Never stack paired label + body rows at a fixed vertical pitch.** Estimate
  the body's wrapped line count, or measure a render, and place each pair from
  accumulated height. One extra wrapped line otherwise shifts every later label
  and pairs it with the wrong paragraph — a defect that reads as nonsense rather
  than as a spacing error.

## Page numbers on added slides

python-pptx `add_slide()` clones only content placeholders; slide-number,
footer, and date placeholders are skipped. Added pages therefore lose their
numbers while kept pages keep theirs. Copy the layout's `sldNum` placeholder
element onto each added slide, or clone an existing slide instead of adding a
blank one. After adding pages run `audit_pptx_page_numbers.py` — usually
`--mode native` for a placeholder-numbered template — and resolve findings per
`pptx-native-editing.md` → "Page numbers, footers, and inherited placeholders".

## Storyline, fit, and QA routes

- Sequence and density: `AUTHORING.md` → "Plan the page sequence" and "Fit
  content without fabrication" apply to native authoring unchanged. A deck of
  accurate pages with no spine still fails.
- Visual grammar: the system is the template's. Extract its archetypes,
  density, and whitespace ratios per `native-redesign-fidelity.md` → "Learn the
  template's composition, not only its colors"; do not invent a parallel system.
- QA: finish on `visual-qa.md` and check every new page against its list.
  Correction passes introduce their own defects, so re-sweep all pages after
  fixing, not only the pages you touched.
