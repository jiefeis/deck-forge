# Long Table Preview Card

Use this small file for title-slide previews only. For final deck generation, read this template's full `design.md` after selection.

## Selection Metadata

- Slug: `long-table`

## Visual Snapshot

Cover recipe:

- Surface: full-bleed cream paper #FAF1E2 under the 4px radial-dot ink texture at 10% opacity; padding 65px top, 96px sides. Every mark on the slide is the one rust ink #B53D2A.
- Split: the title block occupies the left, the jumbo edition numeral fills the right half in place of an illustration.
- Title: Bricolage Grotesque weight 800 uppercase at 194px, line-height 0.92, letter-spacing -0.012em, left-aligned.
- Beneath it: italic Fraunces tagline at 32px, then a stats line ("N seats · M cities · L hours") in italic Fraunces 28px.
- Action row: 2–3 outlined pills (radius 999px, 1.5px ink border, 11px/38px padding, italic Fraunces 25px), joined by a `·` divider at 70% opacity. No fills — outline only.
- Hero anchor: italic Fraunces numeral at 492px on the right, with a tracked Bricolage 700 uppercase label (25px, 0.18em) directly beneath.
- Chrome: page number bottom-right (italic Fraunces 22px, right 69px / bottom 43px) and a 45%-opacity nav-hint bottom-left — both as slide-internal elements, never `.progress-bar` / `.slide-counter`.

## Preview Ingredients

- Palette: paper #FAF1E2; paper-d #F2E5CF; paper-vd #E8D7B6; ink #B53D2A; ink-dp #8E2D1F; rule #B53D2A
- Typography: Fraunces; Bricolage Grotesque
- Signature move: Bricolage Grotesque at weights 700 and 800 in strict uppercase carries every display moment — covers, headlines, card titles, course names, quote bodies, info values, who-tags.
- Signature move: Fraunces at weight 400–600 carries every body paragraph, every metadata field, every pill, every page number, every edition label. Italic Fraunces is the default body style — the slanted serif is the system's body voice, lending warmth and editorial personality.
- Signature move: One ink color (#B53D2A — warm rust terracotta) on cream paper (#FAF1E2). Opacity variants are the only color variation.
- Signature move: Bricolage Grotesque weight 700–800 uppercase for every display moment; Fraunces 400–600 italic-default for every body and metadata moment.
- Signature move: Subtle 4px radial-dot paper texture on every slide via .stage::before — invisible at distance, present up close.
