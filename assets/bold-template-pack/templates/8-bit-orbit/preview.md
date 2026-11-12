# 8-Bit Orbit Preview Card

Use this small file for title-slide previews only. For final deck generation, read this template's full `design.md` after selection.

## Selection Metadata

- Slug: `8-bit-orbit`

## Visual Snapshot

Cover recipe:

- Surface: dark-void #0A0E27 under the 40px cyan-on-navy grid; slide padding 32px top/bottom, 77px sides; inner content column capped at 1200px and centered.
- Atmosphere is mandatory, not optional: grain (opacity 0.035) + CRT scanlines (multiply blend) + radial vignette, with a twinkling starfield and floating 8px pixel squares behind the content.
- Eyebrow: navy label pill holding Space Mono 12px uppercase at 0.2em tracking in neon-yellow, sitting above the title.
- Title: Tektur weight 900 at 192px, line-height 1.05, +0.04em tracking, neon-cyan, always carrying the two-layer text shadow `4px 4px 0 #F4D03F, 8px 8px 0 #0F1B3D`. Centering is permitted here and nowhere else.
- Tagline: one or two lines of Chakra Petch 29px, line-height 1.8, in rgba(255,255,255,0.7) directly under the title.
- Badge cluster below the tagline: outline-only chips with a 2px neon-yellow border, 8px/16px padding, Space Mono 11.2px uppercase at 0.1em.
- Framing: 24×24 neon-cyan L-brackets with 4px stroke at the title region's top-left and bottom-right, offset 8px outside it — no rounded corners anywhere.
- Chrome: square nav pips on a right rail and a Space Mono `01 / 10` counter at bottom center; any page number that must survive PDF export is a slide-internal element.

## Preview Ingredients

- Palette: dark-void #0A0E27; deep-navy #0F1B3D; neon-cyan #5EDCF4; neon-pink #F0A6CA; neon-yellow #F4D03F; soft-lavender #E2D5F2; white #FFFFFF
- Typography: Tektur; Chakra Petch; Space Mono
- Signature move: Three-font stack: Tektur (display), Chakra Petch (body), Space Mono (HUD/labels) — never substitute, never mix outside their roles.
- Signature move: Navy ground (#0A0E27 / #0F1B3D) alternates with colored-grid surfaces (pink, cyan, lavender) — both carry the 40px etched grid.
- Signature move: Three neons (cyan, pink, yellow) reserved for display, stats, rules, and label fills — never for body text.
- Signature move: All measurements snap to the 4px pixel unit: borders 2-4px, shadow offsets 4px / 8px, corner brackets 24×24 with 4px stroke.
- Signature move: Stacked hard offset shadows are the system's depth language — never blurred, never colored on text shadows except in the yellow→navy cascade.
