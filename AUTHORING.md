# Deck authoring discipline

Use this guide when authoring new deck pages — a new HTML/PDF deck, or new
native slides on an existing template (template-native authoring). It is a
quality contract for the authored story, not a license to invent missing
content.

## Contents

- Establish the source boundary
- Plan the page sequence
- Build one visual system
- Fit content without fabrication
- Verify the delivered artifact

## Establish the source boundary

Read all supplied material before choosing layouts. Separate four kinds of
information:

- facts and claims that must remain unchanged
- optional supporting material that may be condensed
- gaps that require a user decision or an explicit placeholder
- proposals — comments, tracked changes, suggested rewrites（批注里的「拟改为…」）:
  author from the body text; use their wording only after the user confirms it
  was adopted

For a delivery version, distinguish the purpose of each gap:

- **Live-fill fields:** answers or scores produced during use need an editable
  blank with a meaningful field label. Follow the template's label styling.
  In PPTX prefer a line shape to repeated underscore glyphs, and check the
  filled layout in the target renderer.
- **Missing facts:** request information necessary for delivery when it is
  unavailable and no treatment has been agreed. State what is missing and keep
  the affected content provisional; a tidy empty table must not imply that an
  analysis is complete. Never invent values or commitments.
- **Approved placeholders:** retain user-specified placeholders, agreed blanks,
  and wording protected by a verbatim or translation contract. Do not ask again
  for information the user has already agreed to supply later.

Replace production prompts such as TBD or 待填 with designed fields only when
that serves the requested delivery and does not override these contracts.

Do not manufacture metrics, customers, dates, quotes, owners, or conclusions to
make a template look complete. In client-facing proposals, forward-looking
numbers are commitments, not texture: write only figures the user will stand
behind; degrade the rest（「8–15 名」→「若干名」）or cut them. Numbers
describing delivered work stay. When the evidence supports six pages, make six
pages. A shorter accurate deck is better than a longer synthetic one.

## Plan the page sequence

For a deck that argues a case, the page list itself comes from a confirmed
title chain (`references/storyline.md`); this section governs each page inside
that chain.

Give every page one job. Before authoring it, write down:

1. the point the audience should retain
2. the evidence or visual object that supports that point
3. the page structure that makes the relationship easy to scan

Turn item 2 into a concrete visual brief using
[references/visual-evidence.md](references/visual-evidence.md): what the viewer
must see, the source or production method, and the treatment. This applies to
text-only briefs too. Resolve planned images before final layout; a placeholder,
decorative icon, or text box does not fulfill a photo/illustration brief.

A useful sequence usually alternates density: orient, explain, prove, pause,
then conclude. Avoid ten consecutive pages with the same card grid or identical
text-to-image split.

Keep narrative transitions explicit. A section page should mark a real change
of subject; it should not exist only because a template includes one.

## Build one visual system

Choose typography, palette, spacing, rule weight, image treatment, and motion as
a system before polishing individual pages. Repeated roles must remain stable:

- title and section title
- lead, body, caption, and source
- page number and footer
- cards, badges, chart labels, and callouts

When authoring on an existing template, the system is the template's: inventory
its roles and follow them (`references/native-redesign-fidelity.md` → "Learn
the template's composition"); do not invent a parallel one.

Variation should come from composition and emphasis, not accidental font or
color drift. Use one dominant visual idea per page and keep decorative elements
subordinate to the information. On a dense page, lead and body sit about two
points apart; a third body size is drift, not emphasis.

Preserve the template's title, label, weight, and semantic-color roles. Within
authored body copy, use emphasis to make the key comparison, decision, or
evidence easy to find:

- Separate scan labels from their explanations when the content uses that
  structure. Do not treat a title prefix as another body label.
- Bold the meaningful phrase or paired terms, not every sentence or list item.
  In tables, distinguish the important result from reference values; a short
  evidence-only numeric cell may be bold in full, including its unit.
- Focus added body accents on the page's point. One or two is a useful starting
  point, not a quota; existing brand colors, chart series, and role labels are
  not extra body emphasis to remove.
- Keep qualifiers attached to their claims and sufficiently prominent. If
  “estimated” or “not yet deployed” is the important distinction, it may deserve
  emphasis. Do not make a number conspicuous while weakening its limitation.

Avoid uniform emphasis across whole body columns or unrelated parallel terms.
There is no per-sentence minimum or character-percentage target; check the
reading hierarchy at presentation size and keep same-role treatment consistent.
For text-heavy pages, recheck `references/text-to-visual.md` when relationships
or repeated bolding make the reading hierarchy hard to see.

## Fit content without fabrication

Choose a layout because it matches the information shape. Do not stretch the
content to satisfy a layout's slot count.

- Three points do not become five cards.
- A comparison needs comparable dimensions, not decorative symmetry.
- A process needs an actual sequence and direction.
- A chart needs a quantitative relationship worth plotting.
- A quote needs a real source, and names its speaker beside it — inline quotes
  included; unnamed, it reads as the words of whoever the page last named.

When copy does not fit, use this order:

1. remove repeated or nonessential words
2. widen or rebalance the existing content region
3. split a genuinely compound idea across pages
4. reduce the role's type token consistently and only as a last resort

Never hide overflow, crop text, shrink one isolated box into illegibility, or
leave a large accidental void at the bottom. The occupied area should feel
intentional when viewed at presentation size.

## Motion

Motion should reveal reading order or state change. Use one coherent entrance
language and keep timing short. Avoid continuous decoration, unrelated bouncing,
or animation that is required to understand a static PDF export.

## Verify the delivered artifact

After the final write:

1. render every page at its actual 16:9 output size
2. inspect the full contact sheet for rhythm and large regressions;
   squint-test each page — at thumbnail size the eye must still land on its
   one message
3. inspect every dense or changed page at full size
4. check clipping, overlap, weak contrast, image quality, page count, and order
   — where color carries a category, attribution, or grouping, confirm the
   meaning survives a grayscale render; a second cue (label, position, weight,
   or pattern) must distinguish them, not hue alone
5. rerender after any correction; an earlier preview is not final evidence

Also run the visual-evidence review: inspect whether exhibits actually support
the title, image crops retain the subject, charts encode the supplied values,
and diagram arrows express the intended relationships. Review the contact
sheet for unintentional runs of text/card pages. The HTML audit detects broken
assets; it cannot judge visual sufficiency or consulting quality.

When the deck states facts, numbers, quotes, or attributions taken from the
supplied material, trace each back to a source span before delivery, matching
subject, unit, time range, and status: a target, a proposal, and an achieved
result are different claims even when the number is identical (a target margin
of 50% is not an achieved 50%). Cut or mark as an explicit placeholder anything
with no source. Run this pass even when the draft reads clean — inserted detail
is invisible to the author who wrote it, so believing the draft is faithful is
not evidence that it is.

For PDF generation, confirm the exported file rather than trusting the browser
preview. For native PPTX work, follow the separate source-preserving audit
workflow in `references/edit-scope-contract.md`.
