# Layout Taxonomy

A brand-agnostic catalog of slide layouts, adapted from rollingai-decks'
`feishu-deck-h5` layout set. Use it as a **content-shape → layout** lookup while
planning the deck (Phase 1, applied again in Phase 3). These are *information structures*, not visual
styles — render each one in whatever style the user picked in Phase 2, on the
fixed 1920×1080 stage.

The point of this taxonomy: instead of free-styling every slide (which drifts
into "wall of bullets"), first name the information shape of each page, then pick
the matching structure. This is what keeps a generated deck looking *designed*.

## How to use

For each page in the source storyline, identify its shape in the left column,
then build that structure. Most decks use only 5–8 of these.

| Layout | Use when the page is… | Natural fill (items) | Key fields |
| --- | --- | --- | --- |
| **cover** | The title slide | 1 | title, subtitle, author, date |
| **agenda** | A table of contents (only if the deck is long) | 4–7 numbered items | numbered list (zh/en optional) |
| **section** | A chapter divider / attention reset | 1 (+ optional pills) | big section title, optional lede, optional tag pills |
| **content / 3up** | 3 parallel, comparable items | 3 cards, 5–8 lines each | per card: number, icon, title, body, footer/kpi |
| **content / 2col** | One explanation + one supporting visual/panel | text side + visual side | lede, feature list; visual = image/data-panel/svg |
| **content / blocks** | A few self-contained statements/callouts | 2–4 blocks | lede + body blocks (pullquote, cta, data-panel) |
| **content / before-after** | Two-sided contrast (pain vs solution, old vs new) | 4–6 items per side + pivot | before.items, after.items, pivot caption |
| **content / matrix** | A 2×2 quadrant framework | 4 quadrants | axes (x/y labels), 4 quadrants of items |
| **content / story-case** | A narrative case study with one hero image | 1 scene + caption + body | scene image, caption, body text |
| **stats / hero** | ONE headline number that anchors the slide | 1 giant stat | eyebrow, big number + unit, supporting line |
| **stats / row** | 2–4 KPIs side by side | 2–4 stat columns | per col: number+unit, label, trend, source |
| **stats / waterfall** | A buildup/breakdown of a total | 3–6 bars | bars (label, value, delta, kind) |
| **quote** | A customer voice / punchline as a breather | 1 quote | lead + accent + tail, attribution |
| **image-text** | A full-bleed image with overlaid headline | 1 image + headline | image src, title, lede |
| **table** | The source IS a table | rows × cols | headers[], rows[][], footnote |
| **flow / timeline** | A sequence of dated milestones | 3–6 nodes | nodes (when, what, desc) |
| **flow / process** | Numbered steps of a process | 3–6 steps | steps (num, title, body) |
| **flow / tree** | A hierarchy / decomposition | root + 2–5 branches | root (why), branches (title, leaves[]) |
| **flow / swim** | A multi-lane roadmap over time | lanes × time columns | time_axis[], lanes (name, milestones by column) |
| **logo-wall** | Client/partner logos grouped by category | N groups × M logos | industries (name, logos[]) |
| **arch-stack** | A layered architecture / tech stack | 2–5 layers | layers (name, module pills[]) |
| **end** | The closing slide | 1 | contact, optional slogan |

## Picking by information shape (quick map)

- **parallel items (3)** → content/3up
- **parallel items (2 or 4)** → content/3up variant or stats/row
- **two-way contrast** → content/before-after (or a 2col split)
- **single big number** → stats/hero
- **2–4 numbers** → stats/row
- **buildup to a total** → stats/waterfall
- **sequence in time** → flow/timeline (linear) or flow/swim (multi-lane)
- **ordered steps** → flow/process
- **hierarchy** → flow/tree or arch-stack
- **2×2 framework** → content/matrix
- **rows of data** → table
- **a memorable line** → quote
- **explanation + visual** → content/2col or image-text
- **chapter break** → section

## Notes

- These are the *information shapes that recur in real decks* — the value is the
  mapping, not any specific CSS. Implement each in the user's chosen style.
- Honor the empty-bottom test in `AUTHORING.md`: each layout's "natural fill"
  column tells you roughly how much content it needs to look right. Below that,
  switch layouts rather than padding content.
- You are not limited to this list. If a page has a sharper, more specific design
  opportunity, design it freely (the "wildcard" path) — this
  taxonomy is a floor for coherence, not a ceiling on creativity.
