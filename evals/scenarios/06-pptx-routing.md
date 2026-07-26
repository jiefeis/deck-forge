# 06 · PPTX routing: repurpose vs native edit, stated ambiguously

**Contract under test:** Phase 0 routing — a source `.pptx` being repurposed
into a NEW deck may go through `extract_pptx.py --visible-only`; a
source-preserving request must never be extracted/rebuilt (SKILL.md Phase 0;
`references/workflow.md` "PPTX input").

## Setup

`eval-deck.pptx` with at least one hidden slide (see EVALS.md fixture).

## User prompt (verbatim)

> 我下周要给新客户讲方案，基于 eval-deck.pptx 帮我弄一版。
> 风格可以大改，好看最重要，但是里面的内容和数据都要在。
> 最后给我能直接讲的东西。

Genuinely ambiguous: "基于……弄一版 + 风格大改" leans Generate (repurpose);
"内容和数据都要在 + 能直接讲" is compatible with both a new PDF deck and a
restyled native PPTX. Correct behavior: resolve the route EXPLICITLY before
touching the file — one question offering the two real options with their
artifact consequences (new HTML→PDF deck, loses PPTX editability; native
restyle, keeps the package). Silently picking either route is the failure
mode being probed, with a secondary probe on hidden-slide handling.

## PASS criteria (tool trace + artifacts)

- The agent asked (or the user's wording answered) which artifact mode
  applies BEFORE running `extract_pptx.py` or editing the package —
  and named the deliverable difference (PDF vs editable PPTX), not just
  "重做 or 修改".
- If Generate was chosen: extraction used `--visible-only`, the agent
  confirmed hidden pages were excluded, and the deliverable is HTML + PDF in
  the user's directory.
- If Native restyle was chosen: no extraction; scope contract frozen first;
  hidden slide still hidden in the deliverable; structure/property audits run.

## FAIL signals

- `extract_pptx.py` run before the mode was resolved.
- Generate route chosen but hidden-slide content appears in the new deck.
- Native route chosen but the deck was rebuilt page-by-page as images/HTML.
- The routing question asked without artifact consequences ("要重做还是
  修改？" alone), leaving the user to guess what each means.
