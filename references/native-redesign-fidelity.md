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

Treat statements such as “I deleted the old versions,” “I inserted two hidden
pages,” “I saved a newer copy,” or “use the current file” as a source revision
event.

1. Resolve the current source path again.
2. Hash it and create a new manifest before editing.
3. Recompute page order, hidden state, stable IDs, titles, and source mappings.
4. Discard page-number assumptions from the previous round.
5. Keep the new baseline outside the delivery folder.

Before the final overwrite, hash the current source again. If it no longer
matches the baseline, do not overwrite it with the candidate. Rebase the
authorized edits onto the new source or ask the user which version wins. This
optimistic-concurrency check prevents erasing edits made while the agent was
working.

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
- Inspect at full slide size, not only a contact-sheet thumbnail.

Fix fit in this order: clarify wording, widen within the existing grid, add
semantic line breaks, then reduce peer font sizes modestly and consistently.

## Recover from package-normalizing authoring tools

A high-level PPTX library may produce a visually correct candidate while
rewriting stable slide IDs, relationship IDs, hidden flags, slide order,
layouts, masters, or themes. Treat that export as an authoring intermediate,
not the package authority.

Run the structural audit before overwriting the source. If untouched pages are
pixel-identical but the package audit reports order, hidden, or shared-part
changes, do not authorize the churn with `--allow-shared` and do not dismiss it
as harmless.

When the candidate was authored from the same baseline, uses direct formatting
instead of placeholder/theme inheritance, and uses only dependencies already
present on each target slide, transplant the authorized shape tree back into
the untouched baseline:

```bash
python <skill-root>/scripts/transplant_pptx_slides.py \
  <baseline.pptx> <candidate.pptx> <rebased.pptx> \
  --pages 2,4,31,41 --component shape-tree
```

The transplant keeps the baseline presentation order, stable IDs, hidden
state, relationships, notes, layouts, masters, and themes. It remaps referenced
relationship IDs by type and payload hash and fails closed when the candidate
introduces an unmatched dependency, an ambiguous page identity, theme/layout
inheritance, or shape-ID-coupled timing/comments/controls. `cSld` and full-slide
replacement are not supported. Use explicit `--map source:candidate` when the
candidate's physical order differs.

If the redesign introduces an image, SVG, chart, SmartArt, or other dependency
not already present on the baseline target slide, stop using the transplant
route. Continue with a package-preserving editor or a separately scoped,
dependency-aware copy workflow; never broaden to full-slide replacement merely
to bypass the failure.

After transplanting, rerun the structural and property audits against the
baseline. The permitted logical package differences should be limited to the
authorized slide parts and property families. Render candidate and rebased
target pages with the same engine and require pixel equivalence; package safety
does not by itself prove that direct formatting renders identically.

## Final fidelity ladder

Complete these gates after the last edit:

1. Confirm the current source hash still matches the baseline hash.
2. Confirm the physical/visible-ordinal/displayed-marker/source page-address
   table.
3. Check every target slide against its content and topology contract.
4. Render the candidate target pages and fix copyfit at full size.
5. Rebase through slide-local transplant if the authoring tool churned the
   package.
6. Pass structure and property-scope audits.
7. Render baseline and final with the same engine.
8. Pass the rendered-page audit with only the authorized physical pages.
9. Inspect the aligned full-deck contact sheet and every changed/dense page
   full-size.
10. Verify visible numbering and the exact hidden pages.
11. Copy the validated artifact to the final path.
12. Verify the final file hash equals the validated candidate. A byte-identical
    copy carries the candidate's audit attestation; any differing hash or later
    save requires rerunning delivery-critical audits on the final path.
