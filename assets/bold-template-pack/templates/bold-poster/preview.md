# Bold Poster Preview Card

Use this small file for title-slide previews only. For final deck generation, read this template's full `design.md` after selection.

## Selection Metadata

- Slug: `bold-poster`

## Visual Snapshot

Cover recipe:

- Surface: flat white sheet #FFFFFF, no panel or border enclosing the composition; slide padding 48px 56px, content anchored top-left, square corners and zero shadows everywhere.
- Meta line: Libre Baskerville 23px in ink #1C1410 sits above the title stack, optionally preceded by a Space Grotesk 21px uppercase red eyebrow at 3px tracking.
- Title: a three-line Shrikhand stack, left-aligned — line 1 at 369px in ink (no rotation), line 2 at 415px in red #D8000F rotated -4°, line 3 at 323px in ink rotated +2°. At least one line red and at least one tilted is non-negotiable.
- Tagline: Libre Baskerville 28px at line-height 1.6, parked bottom-right against the lower corner so it counterweights the top-left title mass.
- Decoration: none — negative space plus the tilt does the work. No cards, no rules, no dots on the cover.
- Chrome: 5px red trim strip along the bottom edge (implement as `.poster-trim`, never `.progress-bar`) and a Space Grotesk 23px uppercase counter at bottom-right, 50% opacity; a page number that must survive PDF export has to be a slide-internal element.

## Preview Ingredients

- Palette: bg #FFFFFF; dark #1C1410; red #D8000F; light #F5F2EF
- Typography: Shrikhand; Libre Baskerville; Space Grotesk
- Signature move: White (#FFFFFF) canvas alternating with off-white (#F5F2EF) panels for striping, plus dark (#1C1410) and red (#D8000F) full-bleed panel surfaces for statement moments.
- Signature move: Single tomato red (#D8000F) as the only accent — used for every numerical figure, every section rule, every label, every left-bar marker.
- Signature move: Three-face stack: Shrikhand (display + numerical), Libre Baskerville (body), Space Grotesk (mono labels + bullets + chrome).
- Signature move: Display Shrikhand is routinely tilted (-6° to +2°) — the rotation is the system's signature movement.
- Signature move: Heavy ink borders: 3px on tabular grid containers, 1.5-2px on cells, 4px red on editorial leftbar cards, 1px hairlines between bullet rows.
