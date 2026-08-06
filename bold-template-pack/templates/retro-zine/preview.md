# Retro Zine Preview Card

Use this small file for title-slide previews only. For final deck generation, read this template's full `design.md` after selection.

## Selection Metadata

- Slug: `retro-zine`

## Visual Snapshot

Cover recipe:

- Surface: full-bleed warm khaki paper #C8B99A under the SVG grain overlay at 0.07 opacity; 60px slide padding (60px 80px on column spreads); zero rounded corners.
- Eyebrow: Bebas Neue uppercase 17–22px at 0.2em tracking in forest green #008F4D, sitting directly above the title.
- Title: Bebas Neue 400 uppercase at 233px, line-height 0.88, 0.04em tracking, green on khaki, left-aligned and hard against the left padding edge.
- Support: one Space Grotesk 400 line at 30px (line-height 1.6) in ink-black, optionally signed with a Caveat hand-script note at 70px.
- Structure: a 3px solid black rule separates the title block from the meta row; region borders never drop below 1.5px and are always black.
- Decoration: one stamp-mark badge (black fill, green text, 2px green border) rotated -8deg pinned into a corner, plus an optional taped collage piece at -5deg.
- Chrome: bottom meta row in tracked caps; any page number that must survive PDF export is a slide-internal element, never `.progress-bar` / `.slide-counter`.

## Preview Ingredients

- Palette: bg #C8B99A; bg-dark #B8A98A; green #008F4D; green-light #00A85D; black #1A1A1A; white #F4EFE6
- Typography: Bebas Neue; Space Grotesk; Caveat
- Signature move: Warm khaki paper canvas (#C8B99A) + deep forest-green accent (#008F4D) + ink-black structure (#1A1A1A).
- Signature move: An SVG grain overlay (`grain-overlay`) sits over every slide at 0.07 opacity, reinforcing the printed-paper register.
- Signature move: Bebas Neue uppercase + tracked for every display moment; Space Grotesk at small sizes for body; Caveat for hand-script emphasis.
- Signature move: 3px solid black structural borders divide regions; 2px and 1.5px borders subdivide.
- Signature move: Paper-on-paper offset cards: green slab sits 12px behind a white card via ::before.
