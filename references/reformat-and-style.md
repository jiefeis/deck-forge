# Reformat versus relayout

Read this when the user asks to reformat, restyle, unify fonts/colors, match a
reference style, or preserve an original deck while improving appearance.

## Default interpretation

Most "reformat" requests mean:

- preserve layout and content hierarchy
- change visual treatment such as background, colors, typography, spacing
  consistency, and brand chrome
- fix only obvious fit problems created by the style change

Do not redesign, move major content blocks, simplify diagrams, add new side
notes, or change the story unless the user explicitly asks for relayout.

## Extract style before editing

From the reference pages or deck, capture:

- canvas size and aspect ratio
- background, top/bottom rules, footers, page numbers, logos, and recurring
  chrome
- palette, accent colors, line weights, fills, shadows, and border radii
- font family, title/body sizes, weights, line spacing, and case conventions
- margins, grid rhythm, column widths, and spacing between object groups
- chart, table, card, and callout treatment

Apply these as tokens. Do not infer a completely new design system unless the
user asked for a redesign.

## Preserve during reformat

- page count and page order
- original content order and emphasis
- object positions, unless they are broken or overflow
- hidden backup slides, if requested
- page markers, dates, logos, and repeated footer language

If the user asks for a backup/comparison version, duplicate and hide the original
before changing it. Verify the hidden state afterwards.

## Fit rules

- Shorten translated or rewritten copy before shrinking font.
- If copy still does not fit, reduce font size modestly and consistently across
  similar elements.
- Avoid adding side explanation boxes when the source fused subtitle/context into
  the main title.
- Use visual rendering, not text inspection, to decide whether the page is clean.
