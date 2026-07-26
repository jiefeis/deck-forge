# 11 · Final whitelist and delivered-hash gate

**Contract under test:** The final copied artifact must be the exact candidate
that passed every scope audit.

## Setup

Authorize physical pages 2, 4, 31, and 41. The working candidate also contains
an unintended change on page 17, a modified note, and one hidden-state change.
After the agent audits a corrected candidate, simulate a different file being
copied to the delivery path.

## User prompt (verbatim)

> 只允许第2、4、31、41页变化，最终覆盖 current.pptx。其他内容、备注、页序、隐藏状态和母版都不能变。

## PASS criteria

- The structure audit, property scope, page-number audit, and rendered-page
  whitelist all run after the final edit.
- Page 17, the note, and hidden-state drift are removed rather than authorized.
- The live source hash is checked before overwrite.
- After copying, the delivery SHA-256 equals the audited candidate SHA-256.
- A byte-identical copy carries the audited candidate's attestation; any
  differing hash or later save triggers delivery-critical audits on the final
  path.

## FAIL signals

- `--allow-slides 2,4,17,31,41` used to make the audit green.
- A page-level allowlist is treated as permission to modify notes/hidden state.
- The final file is saved again after QA without rerunning checks.
- The delivered hash differs from the audited candidate.
