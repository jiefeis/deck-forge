# Blue Professional Preview Card

Use this small file for title-slide previews only. For final deck generation, read this template's full `design.md` after selection.

## Selection Metadata

- Slug: `blue-professional`

## Visual Snapshot

Cover recipe:

- Surface: warm cream #fdfae7 full-bleed; the cover drops the usual slide-header (eyebrow + tag pill) and runs a single left-aligned text block inside 77px side / 67px top padding.
- Split: text occupies the left ~60%; a cobalt-at-8% diagonal panel fills the right ~35%, cut by `clip-path: polygon(30% 0, 100% 0, 100% 100%, 0% 100%)`.
- Rule: the 60×4px cobalt accent-line (2px radius) sits directly above the title — the cover's signature opener.
- Title: Space Grotesk weight 700 at 128px, line-height 1.1, letter-spacing -0.02em, in near-black #111111 — never cobalt.
- Support: one Inter 28px line at line-height 1.6 in #6b6b6b beneath the title; a Space Grotesk 25px meta line (date / confidential marker) in #9a9a9a below that.
- Decoration: a 3×3 grid of 6px cobalt dots at 12px gap, 25% opacity, tucked into an open corner.
- Chrome: 3px cobalt progress strip, counter bottom-left, circular nav buttons bottom-right — all reserved presentation chrome; any page number that must appear in the PDF has to be a slide-internal element instead.

## Preview Ingredients

- Palette: bg #FDFAE7; primary #1E2BFA; text #111111; text-muted #6B6B6B; text-light #9A9A9A; positive #059669; negative #DC2626
- Typography: Space Grotesk; Inter
- Signature move: Warm cream ground (#fdfae7) on every surface — never pure white, never gray.
- Signature move: Single saturated cobalt (#1e2bfa) as the only accent — used for every eyebrow, metric, CTA, chart fill, and progress indicator.
- Signature move: Space Grotesk (display + chrome) + Inter (body) — never substitute either.
- Signature move: Cards are 4% cobalt tints with 1.5px cobalt-at-20% borders and 10-14px rounded corners.
- Signature move: Soft pill-shaped chrome (`tag-pill`, `cta-button`) with full 100px border-radius.
