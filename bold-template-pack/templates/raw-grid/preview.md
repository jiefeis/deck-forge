# Raw Grid Preview Card

Use this small file for title-slide previews only. For final deck generation, read this template's full `design.md` after selection.

## Selection Metadata

- Slug: `raw-grid`

## Visual Snapshot

Cover recipe:

- Surface: white #FFFFFF canvas divided by 3px solid black borders into edge-to-edge regions — a shallow header band above a full-width title region; no gaps, no margins, no rounded corners.
- Padding: 77px inside the title region, 48px inside the header band; regions abut the border line directly.
- Header band: black label pill at left (white uppercase 18px / weight 800 / 0.08em, 10px 22px padding) beside a 48px white icon-box with 3px black border; 19px / 700 / 0.08em uppercase caption meta at right.
- Title: 134px weight 900 uppercase, -0.02em tracking, black, left-aligned — sentence-case display does not exist here.
- Subtitle: 27px / 700 uppercase at 0.04em, separated from the title by a 60px × 4px solid black rule stub.
- Accent: one flanking or lower region filled blush pink #F2D4CF or sage green #E5EDD6 — accent fills are surfaces only, never text color, and never sit behind the title.
- Decoration: an oversized weight-900 numeral at 0.15–0.35 opacity as wallpaper inside the accent region; if a card is lifted, one 6px 6px 0 solid black hard offset shadow, zero blur.
- Chrome: no header/footer chrome on the cover; any page number must be a slide-internal element in the caption row.

## Preview Ingredients

- Palette: black #0A0A0A; white #FFFFFF; pink #F2D4CF; green #E5EDD6; gray #F5F5F5; darkgray #333333
- Typography: Segoe UI
- Signature move: White (#FFFFFF) canvas with 3px solid black (#0A0A0A) borders dividing every region. No gaps between cells — borders meet edge-to-edge.
- Signature move: System sans-serif at weight 900 uppercase for all display type; weight 500 sentence case for all body type.
- Signature move: Hard offset shadows at 6px and 4px in solid black, no blur, ever.
- Signature move: Two muted pastel accent surfaces — blush pink and sage green — used as region fills, never as text colors.
- Signature move: A signature black-pill label component (`label`) — white uppercase text in a small black rectangle — appears as the universal section tag.
