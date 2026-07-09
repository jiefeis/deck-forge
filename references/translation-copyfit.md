# Translation and copy fitting

Read this when translating slides, localizing a deck, or fitting rewritten copy
into an existing layout.

## Translation principles

- Translate the intended point, not word-for-word fragments.
- Use natural audience-facing language a presenter would say aloud.
- Preserve the source hierarchy: title, subtitle, section label, body, caption,
  footnote.
- Do not turn a fused source title into a separated side note unless the source
  layout does that.
- Avoid translationese in the target language: inflated noun clusters, literal
  connectors, and phrasing no native presenter would say.

## Copy fitting workflow

1. Map source and target by content, not only page number.
2. Translate titles and dense boxes in hierarchy order.
3. Shorten copy before shrinking font.
4. Render every translated page.
5. Fix clipping, overlap, line collisions, and awkward phrasing.

## Fit tactics

- Use shorter verbs and concrete nouns.
- Remove repeated qualifiers.
- Replace long explanatory sentences with presenter-friendly phrases.
- Keep labels and process steps parallel.
- For font-size change mechanics, follow `references/reformat-and-style.md` →
  "Font-size and whitespace changes" (the single authority for that pass).
- For arrows and other symbol glyphs, follow the shared policy in
  `references/source-contract.md`: real Unicode arrows first (verify rendered
  output), code-point generation when shell encoding is unreliable, ASCII
  arrows only as a last resort.

## Proofing marks

If exported slides show spelling/grammar marks, follow the proofing-marks
procedure in `references/pptx-native-editing.md`.
