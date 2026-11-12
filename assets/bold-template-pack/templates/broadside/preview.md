# Broadside Preview Card

Use this small file for title-slide previews only. For final deck generation, read this template's full `design.md` after selection.

## Selection Metadata

- Slug: `broadside`

## Visual Snapshot

Cover recipe:

- Surface: full-bleed fire-orange #E85D26 — the declaration register. All chrome is suppressed on covers: no slide-chrome bar, no slide-foot bar.
- Frame: slide padding 106px horizontal / 59px vertical. The type is meant to crowd the frame, not float inside it.
- Catalogue mark: the `broadside-num` in IBM Plex Mono 21px, rgba(17,17,17,0.45), anchored top-left as a publication-style slide number.
- Kicker: IBM Plex Mono 14px uppercase, 0.14em tracking, ink at 55% opacity; optionally paired with the 36×2px ink-black stub rule.
- Title: Barlow weight 900 at 144px, lowercase, line-height 0.9, letter-spacing -0.03em, ink-black #111111, left-aligned. Reserve the 250px display size for a one-word statement cover.
- Support: a single lead line in Barlow 400 at 31px in rgba(17,17,17,0.75). One line — never a paragraph.
- Chrome: any page number that must reach the PDF is a slide-internal element, never the reserved .slide-counter class.

## Preview Ingredients

- Palette: ink-black #111111; ink-black-alt #1A1A18; fire-orange #E85D26; cream #F0ECE5; cream-muted #888880; cream-hint #505048; border-dark #282826
- Typography: Barlow; IBM Plex Mono
- Signature move: Massive Barlow display type at weight 900 in lowercase — never uppercase on display elements.
- Signature move: Two-register color system: dark slides with cream text, or orange slides with dark ink. No cream/white slides exist.
- Signature move: #E85D26 is both accent (on dark) and environment (on orange) — never a secondary color, always *the* color.
- Signature move: Single-typeface system on Barlow + IBM Plex Mono for chrome only. No serif, no script, no third face.
- Signature move: 1px hairline dividers (#282826 on dark; rgba(17,17,17,0.2) on orange) provide all hierarchy structure.
