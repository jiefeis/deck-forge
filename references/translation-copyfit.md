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

1. Create source/target manifests and map slides by stable slide ID or verified
   content/structure, not only page number.
2. Map each source text role to one target role: title, subtitle, section label,
   body, caption, and footnote. Do not silently drop or add boxes.
3. Preserve rhetorical intent and punctuation logic. A statement must not become
   a question; a fused headline must not become a headline plus side note.
4. Translate titles and dense boxes in hierarchy order.
5. Shorten copy before shrinking font.
6. Audit missing/extra text boxes and unexpected source-language residue in the
   target, using an explicit whitelist for product names and proper nouns.
7. Render every translated page after the final write.
8. Fix clipping, overlap, line collisions, and awkward phrasing, then rerun both
   structural and visual checks.

Keep a reviewed mapping ledger with source/target physical page, visible ordinal,
slide ID, hidden state, title, mapping method, confidence, and visual evidence.
A unique shared slide ID is strong evidence for decks from the same lineage.
True-order fallback is provisional when versions may have been reordered; do not
treat it as confirmed without title/content/visual corroboration. In strict
translation mode, automatic order fallback is a failure until the user selects
`--map-slides order` deliberately or supplies confirmed mappings.

For native bilingual decks, make the intended target language explicit and
authorize only the pages that were meant to change:

```bash
python <skill-root>/scripts/audit_pptx_structure.py compare \
  <source.pptx> <target.pptx> --allow-slides <translated-pages> \
  --map-slides id --translation-check --target-language en --strict-translation
```

Use `--target-language zh` for an English-to-Chinese target. Without that flag,
the audit still checks slide/text-box completeness and question-title logic but
does not guess which script is residue. Text boxes are mapped by stable shape
ID, then unique placeholder, then conservative geometry fallback.

Image/chart reconstruction can legitimately add overlay text boxes or replace
source boxes. Do not weaken the global checks. After visually reviewing each
exception, record page-scoped `allow_extra`, `allow_missing`, or explicit
`box_mappings` in a JSON file and pass `--translation-exceptions <file.json>`.
Run the script's `compare --help` for the single authoritative schema. Broad,
ambiguous, conflicting, and unused rules are reported and fail strict mode.

## Fit tactics

- Use shorter verbs and concrete nouns.
- Remove repeated qualifiers.
- Replace long explanatory sentences with presenter-friendly phrases.
- Keep labels and process steps parallel.
- Keep title type, punctuation intent, emphasis, and bold segmentation aligned
  with the source even when the target wording is not literal.
- For font-size change mechanics, follow `references/reformat-and-style.md` →
  "Font-size and whitespace changes" (the single authority for that pass).
- For arrows and other symbol glyphs, follow the shared policy in
  `references/source-contract.md`: real Unicode arrows first (verify rendered
  output), code-point generation when shell encoding is unreliable, ASCII
  arrows only as a last resort.

## Proofing marks

If exported slides show spelling/grammar marks, follow the proofing-marks
procedure in `references/pptx-native-editing.md`.
