# Pink Script — After Hours Preview Card

Use this small file for title-slide previews only. For final deck generation, read this template's full `design.md` after selection.

## Selection Metadata

- Slug: `pink-script`

## Visual Snapshot

Cover recipe:

- Surface: the three mandatory layers — warm-black radial ellipse (#1A1218 at 30%/30% fading to #050306), film grain at opacity 0.08 with screen blend, and the 1px paper-blush-at-14% hairline frame at inset 36px.
- Composition: one hero script lockup and a preamble line, nothing else. Content sits inside 60px side margins with 140px top and bottom reserves; the script should own 60–70% of the canvas.
- Preamble: JetBrains Mono uppercase 28px at 0.42em tracking — the widest tracking in the system — in muted paper-blush, placed above the title.
- Title: DM Serif Display weight 400 at 280px in pink #ED3D8C, carrying the pink halo (text-shadow `0 0 80px rgba(237,61,140,0.18)`) and `padding-bottom: .1em` to compensate for descenders.
- Two-line lockup: the second line is indented for a hanging effect (the source hardcodes `padding-left: 180px`); re-tune the indent to the actual word length rather than copying the value.
- Top runner: 60px top / 60px sides, JetBrains Mono uppercase 24px at 0.14em — brand name in pink on the left, section tag in muted paper-blush on the right.
- Footer: 60px bottom / 60px sides, same mono — source or confidentiality string left, page position (`01 / 09`) right with the current number wrapped in `<em>` to render pink, as a slide-internal element.

## Preview Ingredients

- Palette: ink-deep #060507; ink-violet #0F0D11; paper-blush #F5EDF1; pink #ED3D8C; pink-light #FF66A8; pink-deep #B81D67
- Typography: DM Serif Display; Inter; JetBrains Mono
- Signature move: Deep warm-black surface (`slide-surface`) lit from the upper-left by a radial gradient ellipse.
- Signature move: A subtle film-grain overlay (`film-grain`) on every slide — opacity 0.08, screen blend.
- Signature move: A 1px paper-blush interior frame (`hairline-frame`) inset 36px from each edge, present on every slide.
- Signature move: Hot fuchsia pink (#ED3D8C) is the single chromatic accent — used as script color, kicker color, line color, pill outline, inline emphasis, and the soft halo behind hero scripts.
- Signature move: DM Serif Display carries every editorial moment, scaling from 32px to 600px. There is no second display face.
