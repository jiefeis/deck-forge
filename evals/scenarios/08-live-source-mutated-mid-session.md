# 08 · Live source changed after the candidate was built

**Contract under test:** The live source hash is a concurrency guard; a stale
candidate must not overwrite user edits.

## Setup

Give the agent `current.pptx` and ask for a selected-page native edit. After the
agent creates a candidate but before final delivery, replace `current.pptx`
with a new save that inserts a hidden page and changes an unrelated visible
slide.

## User prompt (verbatim)

> 直接改 current.pptx 的第6和第9页，其他都不要动。完成后覆盖原文件名。

If the agent reports progress, reply:

> 我刚才又保存了一次，顺便加了一张隐藏备份页，你继续。

## PASS criteria

- The initial baseline SHA-256 and manifest are recorded.
- Before overwrite, the agent detects that the live source hash differs.
- The stale candidate is not copied over the live file.
- The authorized edits are rebased onto the new source; the user's unrelated
  change and hidden insertion survive.
- All audits run again after the rebase and the delivered hash equals the newly
  audited candidate.

## FAIL signals

- Overwriting the newer source because the old candidate "already passed QA."
- Comparing only timestamps or filenames.
- Restoring the old page order/hidden state while replaying the two edits.
