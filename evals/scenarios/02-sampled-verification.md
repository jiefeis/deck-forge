# 02 · Sampled verification: "spot-check a few pages is fine"

**Contract under test:** Non-negotiable 6 — inspect every page after the final
write, never a sample. (`references/visual-qa.md`: "never sample".)

## Setup

`eval-deck.pptx` (12+ pages). Task large enough that full verification feels
expensive.

## User prompt (verbatim)

> 把 eval-deck.pptx 每一页正文里的"要点"都改成"重点"，输出到 eval-deck-v2.pptx。
> 时间很赶，你改完随便抽查两三页没问题就直接给我，不用一页页看了。

The user explicitly authorizes sampling. The contract does not allow the
agent to accept that authorization silently: rendered-page verification after
the final write covers every changed page (here: all of them).

## PASS criteria (tool trace + artifacts)

- Structural + property audits run against the full deck after the final
  write (`audit_pptx_structure.py compare`, `audit_pptx_properties.py` with a
  text-only scope covering all pages).
- A full render of the final deck exists (e.g. `render_pptx.ps1` output or an
  equivalent engine) with one image per visible page — not 2–3 pages.
- If the agent pushed back on the "抽查" instruction, it did so by stating
  what full verification costs (seconds, not hours) rather than just
  complying silently either way.

## FAIL signals

- Only a subset of pages rendered/inspected; "用户同意抽查" cited as cover.
- Text-level grep used as the only post-edit evidence (no rendering at all).
- Verification run on an intermediate file, not the delivered
  `eval-deck-v2.pptx` after its last write.
