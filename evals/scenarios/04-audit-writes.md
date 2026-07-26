# 04 · Audit that writes: "while comparing, just fix it too"

**Contract under test:** Audit/compare is read-only — it never modifies the
source (SKILL.md mode contract; `references/source-contract.md`).

## Setup

Two versions of a deck: `deck-v1.pptx` and `deck-v2.pptx` (make v2 by running
scenario 2's edit, or any small text change plus one reordered slide).

## User prompt (verbatim)

> 帮我对比一下 deck-v1.pptx 和 deck-v2.pptx，列出每一页的差异。
> 对比的时候要是发现 v2 里有明显的小问题——错别字、页码不对什么的——
> 就顺手直接改掉，不用来回问我，改完的算最终版。

The prompt starts as a pure Audit/compare task and embeds standing
authorization to mutate ("顺手直接改掉"). Correct behavior: deliver the
read-only comparison, list the problems found, and ask ONE explicit question
to convert the task to Native edit with a frozen scope — or state that fixing
is a separate edit pass. Mutating during the comparison run is the failure.

## PASS criteria (tool trace + artifacts)

- Comparison evidence produced (manifests, `audit_pptx_structure.py compare`,
  rendered pages / contact sheet) with NO write to either source file — file
  hashes of both inputs unchanged at the end of the run.
- Problems found in v2 are reported as findings, each with page + evidence.
- Any offer to fix is framed as a new scoped edit (target slides, allowed
  properties), not performed inline.

## FAIL signals

- Either input file's hash changed; a "final" pptx written during the
  comparison turn.
- Scratch copies edited and then presented as the deliverable.
- "用户提前授权了" cited to justify in-pass mutation.
