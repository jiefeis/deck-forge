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

Before editing a native PPTX, freeze the target pages and allowed properties in
`references/edit-scope-contract.md`. If the user limits the change to background,
palette, font, or text, all unlisted geometry and content are forbidden changes.

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

## Font-size and whitespace changes

When the user asks for larger text or says a page looks sparse, treat this as a
copyfit task, not just a global font multiplier.

- Inventory the deck's actual type roles first: cover title, page title,
  subtitle, section label, body, caption, footer, and page number. Normalize
  peers within a role; do not force every role to one size or weight.
- Resolve explicit run fonts plus theme/master fonts before declaring typography
  unified. Keep CJK and Latin fallback families intentional and verify that the
  target app did not substitute them.
- Inventory only the authorized visible pages first; hidden originals are
  excluded unless explicitly requested:

  ```bash
  python <skill-root>/scripts/audit_pptx_typography.py <deck.pptx> \
    --slides <target-pages> --json
  ```

  After deriving role tokens from the reference/source, use repeated `--expect`
  values or `--fail-inconsistent-role` on that same scope. Do not make a whole
  deck fail because untouched historical pages or hidden backups use a different
  type system.
- Increase peer elements consistently, then render every changed page.
- Watch for orphan characters, awkward word breaks, line collisions, and labels
  merging into descriptions.
- Fix fit in this order: shorten wording, widen the existing text box if the
  layout allows it, adjust line breaks, then reduce font size modestly and
  consistently across peer elements.
- Reduce bottom whitespace by redistributing existing objects or expanding
  existing containers before adding new decoration.
- For process arrows, Harvey balls, badges, and other repeated visual components,
  set exact shared dimensions and alignment instead of sizing by eye.
