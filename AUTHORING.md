# Authoring Discipline

Distilled from the rollingai-decks `slide-design` rules. frontend-slides teaches
you to make slides *beautiful*; these rules keep a *multi-slide deck* coherent,
correctly paced, and free of the "empty slide" / "fabricated content" failures
that screenshot straight into the PDF. Read this in Phase 3 (Generate), before
authoring slides.

## 1. The content drives the structure — the template never does

A layout pack (presets, bold templates, the layout taxonomy in `LAYOUTS.md`) is a
**type system + component library**, NOT a storyline to fill in.

The correct loop:

1. Read ALL the user's source material first. Map **the source's own storyline**:
   how many distinct sections, how many points per section, and what *shape* each
   point is (parallel items? two-way contrast? data? timeline? single big claim?).
2. For each page in that storyline, ask "what is the information shape here?" then
   pick the layout whose shape matches (see `LAYOUTS.md`).
3. Standard pages (cover, section divider, closing) get reused verbatim.
4. **Never** the other way around: do not pick a pretty layout first and then bend
   the content to fill it.

Anti-patterns to refuse:

- ❌ A layout slot wants 5 cards but the source has 3 points → **do NOT invent
  points 4 and 5.** Use a 3-up layout, or a tighter section + text.
- ❌ "A nice example deck had 16 slides, so mine should too." → your deck is
  exactly as long as your source is.
- ❌ Adding an agenda page when the deck is too short to need one.
- ❌ Copying an example's narrative beats ("3 phases", "5 pillars") into your
  content's labels.

**Fabricated content is the worst outcome** — it screenshots straight into a PDF
the user will send to real people. When the source is thin, make a shorter deck,
not a padded one.

## 2. Match the layout to information density (the empty-bottom test)

A 1920×1080 slide is **tall**. Each layout has a natural fill. If you pick a
layout whose natural density is higher than your content, the slide leaves a dead
band at the bottom and reads as broken. Auto-fit only scales content DOWN on
overflow; it never scales UP to fill emptiness — you must size content to fit.

Before authoring each slide, ask three questions in order:

1. **What is the information shape?** (parallel / contrast / timeline / table /
   single stat / hero claim / quote)
2. **How many items?** (3 / 4 / 5 / 6 / table-rows / unbounded)
3. **Will the chosen layout naturally fill ~60–80% of slide height with this
   content?** If no, do ONE of:
   - swap to a layout with a denser natural footprint, OR
   - add a full-width summary band to claim the bottom third, OR
   - vertically center the block, OR
   - make each card heavier (bigger padding, larger headline, longer body).

**The empty-bottom test:** render the slide at 1920×1080. If the bottom ~30% is
pure background with nothing in it, the slide is under-filled — fix the *layout
choice*, not by padding the *content*.

Common rescues (no fabrication needed):

- 3 thin items look skinny → switch to big-number stat cards, or add a summary
  band underneath restating the three.
- 3 phases but a 4-column timeline → use 3 cards (one per phase), each stacking
  sub-task + deliverable + timing.
- "Reading-first" density that overflows → split into two slides; never shrink
  text below comfortable reading size.

## 3. Overflow and overlap are bugs, not style

After generating, the fixed stage means anything that doesn't fit gets clipped or
stacked on top of other panels — and that goes straight into the PDF. So:

- No scrolling, no overflow, no text spilling its card, no panels overlapping.
- `scrollHeight` checks alone are not enough — grid panels can *visually* cover
  each other while reporting no overflow. Verify with a real rendered screenshot
  at 1920×1080 (the `export_pdf.py` run is itself this check — inspect the PNGs /
  PDF pages before delivering).
- If a slide overflows, **split it or redesign its layout** — do not shrink until
  cramped.

## 4. One design system across the whole deck

- Once the user picks a style in Phase 2, expand THAT system across every slide:
  same fonts, palette, decorative vocabulary, spacing rhythm, component grammar.
- Design any missing layout from that system rather than importing a pattern from
  a different style.
- Keep every slide a fixed 1920×1080 stage, single self-contained file.

## 5. Deck rhythm

A coherent deck usually moves: **cover → (agenda, if long) → section dividers
between chapters → content/stats/quote slides sized to their information shape →
closing**. Use section dividers to reset attention between chapters; use quote /
single-stat slides as palate cleansers between dense slides. Match the chosen
density mode (speaker-led = more slides, fewer words; reading-first = denser,
self-contained slides).
