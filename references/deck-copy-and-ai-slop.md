# Deck copy and AI-slop cleanup

Read this when slide language sounds AI-generated, too slogan-like, or too
mechanical, especially in Chinese consulting/report decks. If the
`humanizer-zh` skill is available and the user mentions "AI 味道太重",
"太像 AI 写的", "语言太 AI 化", or "去 AI 味", use it together with this reference.

On conflict, this file wins for slide copy: take humanizer-zh's pattern
checklist (AI vocabulary, paired structures, dash overuse, rule-of-three,
vague attribution), but ignore its prose-oriented advice to inject
personality, first-person voice, or looseness — deck copy stays short,
factual, and impersonal.

## Goal

Make the copy sound like something a real presenter would say in a meeting:
shorter, more concrete, and less performative. Preserve the source facts,
numbers, named frameworks, page hierarchy, and visual layout.

## Deck-specific rules

- Prefer direct business wording over slogans. Replace vague phrases such as
  "关键抓手", "形成飞轮", "复利化", "全面赋能", and "闭环放大" with the actual action,
  owner, metric, or next step.
- Avoid mechanical paired structures unless the source explicitly needs them:
  "不是……而是……", "从……到……", "先……再……", and three-part slogans.
- Remove decorative arrows such as `->` from prose. Use normal punctuation or
  convert the relation into a short sentence.
- Keep the source's own domain terms (product names, framework acronyms,
  role/owner labels, scoring devices such as Harvey balls); do not "translate"
  them into plain language.
- Do not make copy "more literary". In decks, humanizing usually means shorter
  and more specific, not more elaborate.
- Do not change facts, dates, scores, quantities, departments, source labels, or
  page numbering.

## Copyfit after language edits

After humanizing copy (or any font-size change), run the copyfit pass in
`references/reformat-and-style.md` → "Font-size and whitespace changes" —
that section is the single authority for the mechanics (render changed pages,
orphans, breaks, collisions, uniform repeated components). Deck-copy addition:

- Keep the label separate from its description. Do not merge a section label
  and explanatory sentence into one paragraph if the source uses a label/value
  hierarchy.

## Good pattern

Source-like AI copy:

> 通过建立高频协同机制，形成业务与 IT 双轮驱动的 AI 落地飞轮。

Better deck copy:

> 业务每周定场景和验收口径，IT 负责接入和上线节奏。

## Bad pattern

- Rewriting a slide into a new storyline because the language feels awkward.
- Shrinking all text until it fits instead of improving the wording.
- Adding side-note boxes or new explanation areas when the user asked for a
  minimal language/layout fix.
- Leaving a page unrendered after text edits because XML/text extraction looked
  correct.
