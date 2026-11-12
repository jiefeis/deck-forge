# Grove Preview Card

Use this small file for title-slide previews only. For final deck generation, read this template's full `design.md` after selection.

## Selection Metadata

- Slug: `grove`

## Visual Snapshot

Cover recipe:

- Surface: full-bleed deep forest green #192B1B with warm cream #D4CFBF type; padding 70px vertical / 154px horizontal; the cover hides both the slide-chrome and slide-foot bars.
- Kicker: JetBrains Mono 300 uppercase 19px at 0.14em tracking in terracotta coral #C8524A.
- Rule: the signature 36px × 1px coral rule directly beneath the kicker — kicker, rule, and title are one compositional unit.
- Title: Playfair Display 400 at 267px, line-height 1, -0.01em tracking, left-aligned, never bold; one `<em>` word switches to italic coral.
- Support: a single Jost 300 lead line at 39px (line-height 1.65) in muted cream.
- Decoration: the 480px Playfair watermark numeral at 6% opacity, anchored right 154px / bottom -0.15em; zero shadows, zero rounded corners.
- Chrome: bottom nav dots only — any page number that must survive PDF export is a slide-internal element, never `.progress-bar` / `.slide-counter`.

## Preview Ingredients

- Palette: bg #192B1B; bg-alt #1E3221; bg-light #E8E4D6; bg-light-alt #DEDAD0; fg #D4CFBF; fg-light #192B1B; accent #C8524A
- Typography: Playfair Display; Jost; JetBrains Mono
- Signature move: Playfair Display at weight 400 carries every headline, every quote, every stat figure, and every watermark numeral. Bold serif is not permitted — the no-bold rule is the system's most important typographic commitment.
- Signature move: Jost at weight 300 carries every paragraph and bullet body. The light weight is the "good paper" feel — it sits back and lets the serif lead.
- Signature move: JetBrains Mono at weight 300 carries every label, kicker, footline, slide counter, and stat caption. Always uppercase, always with at least 0.12em letter-spacing.
- Signature move: Noto Serif SC / Noto Sans SC at weight 300–500 are loaded as Chinese fallbacks for every role. The deck is built bilingually-aware — Chinese characters render through the Noto cuts when present in the content.
- Signature move: Playfair Display at weight 400 — never bold — for every serif moment. Italic in #c8524a is the headline accent.
