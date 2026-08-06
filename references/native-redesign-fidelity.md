# Native redesign fidelity and page mapping

Read this when redesigning selected pages in an existing PPTX from a mother
draft, teaching plan, case PDF, or reference template—especially when the deck
contains hidden pages or the user has changed the file between review rounds.

## Contents

- Rebaseline after every user-side revision
- Keep four page identities separate
- Freeze a page-level content contract
- Choose a visual grammar from the relationship
- Preserve graph topology
- Learn the template's composition, not only its colors
- Copyfit for projected training decks
- Recover from package-normalizing authoring tools
- Final fidelity ladder

## Rebaseline after every user-side revision

Hash gating and rebaseline follow `references/source-contract.md` →
"Rebaseline when the user changes the source".

## Keep four page identities separate

Never use one integer for all of these:

- **Physical page** — true presentation order, including hidden slides.
- **Visible ordinal** — sequence among visible slides, excluding hidden slides.
- **Displayed marker** — the page number or label printed on the slide; it may
  differ from both physical page and visible ordinal.
- **Source page** — mother-draft, lesson-plan, PDF, or reference-deck page.

Build a page-address table before redesigning:

| physical page | stable slide ID | hidden | visible ordinal | displayed marker | current title | source page/title |
| --- | --- | --- | --- | --- | --- | --- |

Use `ppt/presentation.xml` order through the structure manifest. Detect hidden
state from both the presentation slide entry and the slide root. Match source
pages by title and content anchors, not by arithmetic alone. A physical page 31
can legitimately have visible ordinal 30, displayed marker 130, and source page
30 after a hidden insertion.

When the user says their page numbers are “after adding hidden pages,” interpret
the named pages as physical pages and record that decision in the scope
contract. Never renumber the user's request silently.

## Freeze a page-level content contract

For every target slide, extract these fields before choosing a composition:

- exact title and claim
- must-keep facts or bullets
- explanation, rationale, or “why it matters”
- examples, analogies, cases, and quantitative evidence
- conclusion and transition to the next question
- named nodes and directed relationships
- source visual suggestion, if any
- allowed paraphrase or compression

A diagram does not automatically replace explanatory text. If the mother draft
contains a graph, two loop explanations, an analogy, and a final conclusion,
account for all four layers. Use a compact adjacent card or caption when the
diagram alone cannot carry the teaching meaning.

Maintain a traceability checklist from each source block to one visible final
element. Missing content is a fidelity failure even when the slide looks clean.

## Choose a visual grammar from the relationship

Identify the information shape before drawing:

- **Several kinds of flow** — use small multiples with one color and one
  self-contained path per flow.
- **Linear operating process** — use one ordered pipeline with clear handoffs.
- **Responsibility boundary** — use ownership zones plus a short handoff arrow.
- **Branch or choice** — use a shared origin and explicit fan-out.
- **Feedback loop** — show the shared backbone once, split at the exact node,
  and draw every return edge.
- **Comparison** — use aligned columns or rows with common criteria.
- **Hierarchy** — use levels, nesting, or a tree rather than arrow prose.

Avoid a paragraph made from line breaks and arrow characters. Avoid long return
arrows that travel around unrelated text, ambiguous arrowheads, and a single
tangled graph for multiple independent flows. Whitespace must reveal hierarchy;
it must not replace missing structure.

## Preserve graph topology

Translate every source relationship into an adjacency list before rendering.
For a source such as:

```text
A → B → C → D
D → E → G → A
D → F → H → A
```

the final slide must contain one shared A–D backbone, two visible branches from
D, and two visible returns to A. Do not duplicate D or A merely to make two rows
easier to lay out unless the equivalence and return edges remain explicit.
Duplicating a shared node can turn two closed flywheels into unrelated chains.

Keep node meaning stable. A node defined as “recommendation, prediction, audit,
and contribution evaluation” must not become “matching and experience” just
because the new label fits a box.

Before sign-off, trace every edge in both directions:

1. source edge → visible connector or unambiguous containment
2. visible connector → one authorized source edge

For complex loops, ask an independent reviewer to trace the final render
against the raw source graph without revealing the suspected defect. When no
independent reviewer is available, separate authoring from review and perform a
fresh second-pass trace from the raw adjacency list.

## Learn the template's composition, not only its colors

Style extraction includes more than logo, font, and palette. Capture:

- recurring page archetypes for process, comparison, summary, and exercise
- claim-first title pattern and conclusion placement
- side rails, section bars, numbered conclusions, and footer rhythm
- expected information density and whitespace ratio
- line lengths, card proportions, arrow treatment, and narrative voice

Choose a template page with the same information shape as the target. Matching
the font while ignoring the template's density, hierarchy, and storytelling
pattern is not template fidelity.

For executive training, prefer a visible teaching sequence:

```text
claim → relationship/model → explanation/evidence → conclusion/transition
```

## Copyfit for projected training decks

- Break lines at clauses, commas, or slash boundaries.
- Reject orphan punctuation, split CJK words, and one-word English remnants.
- Keep diagram and relationship labels at least 9 pt when the template and
  available space permit; do not rely on automatic shrink below the projection
  threshold.
- Shorten micro-labels while preserving the complete sentence in a nearby
  explanation card.
- Keep labels clear of node borders and arrowheads.
- For fit mechanics, follow `references/reformat-and-style.md` → "Font-size
  and whitespace changes" (the single authority for that pass).

## Recover from package-normalizing authoring tools

A high-level PPTX library may produce a visually correct candidate while
rewriting stable slide IDs, relationship IDs, hidden flags, slide order,
layouts, masters, or themes. Treat that export as an authoring intermediate,
not the package authority.

Run the structural audit before overwriting the source. If untouched pages are
pixel-identical but the package audit reports order, hidden, or shared-part
changes, do not authorize the churn with `--allow-shared` and do not dismiss it
as harmless. Transplant semantics, command syntax, identity proof, and
required follow-ups follow `references/pptx-native-editing.md` → "Tool
qualification and package-preserving rebase".

If the redesign introduces an image, SVG, chart, SmartArt, or other dependency
not already present on the baseline target slide, stop using the transplant
route. Continue with a package-preserving editor or a separately scoped,
dependency-aware copy workflow; never broaden to full-slide replacement merely
to bypass the failure.

## Final fidelity ladder

Run `references/edit-scope-contract.md` → "Verify after the final write" as
the sole execution backbone; hash gating and rebaseline follow
`references/source-contract.md` → "Rebaseline when the user changes the
source". On top of that standard verification, a redesign additionally
requires:

1. Check every target slide against its frozen content and topology contract.
2. Render the candidate target pages and fix copyfit at full slide size, not
   only on a contact-sheet thumbnail.
3. If the package was rebased through the transplant, rerun the structure,
   property, and rendered-page audits on the rebased file and require
   candidate-vs-rebased pixel equivalence
   (`references/pptx-native-editing.md` → "Tool qualification and
   package-preserving rebase").
