# Source contract and file hygiene

Read this before editing when there are multiple source files, versioned files,
user-provided references, or "only one final file" requirements.

## Establish the source of truth

- Choose the artifact mode first: Generate, Native edit, or Audit/compare. A
  native-edit request must never be converted into the HTML generation workflow.
- Record the exact source path, final output path, final format, page count, and
  page order before editing.
- Treat similarly named files as untrusted until compared. Names like `v2`,
  `v3`, `copy`, `(1)`, and `(2)` often do not encode the user's intended source.
- Compare candidate sources by structure and visible content, not by timestamp or
  page number alone.
- For PPTX, compare by true slide order, never by XML filenames; how to derive
  it is in `references/pptx-native-editing.md` (Structural rules).
- Use `scripts/audit_pptx_structure.py manifest/compare` for deterministic page
  order, hidden-state, stable-ID, and shared-part evidence before relying on a
  visual comparison.
- For PDF/HTML decks, render pages and compare visuals when content order or
  page mapping matters.
- For native edits, freeze target slides and allowed properties using
  `references/edit-scope-contract.md` before any mutation.

When several materials govern different dimensions, use a source-authority
matrix instead of choosing one "master file":

| Dimension | Default authority |
| --- | --- |
| native package, true order, hidden state, notes, and latest user edits | current PPTX |
| required claims, reasons, examples, and teaching sequence | mother draft / lesson plan |
| factual case evidence | case PDF or cited source |
| visual grammar, typography, density, and narrative rhythm | reference template |
| page-number interpretation and latest revision instructions | user's latest message |

The template must not replace mother-draft content, and case material must not
silently expand the conclusion beyond the teaching plan.

## Rebaseline when the user changes the source

Treat deletion of old versions, insertion of hidden pages, a new save, or "use
the current file" as a source revision event. Re-resolve the path, create a new
manifest, record its SHA-256, and rebuild all page mappings. A candidate based
on the previous hash is stale.

Immediately before the final overwrite:

1. Hash the live source again.
2. Compare it to the frozen baseline hash.
3. If it differs, preserve the candidate but do not overwrite the live source;
   rebase the authorized changes onto the new file or ask which version wins.
4. After copying the validated candidate to the delivery path, verify that the
   delivered SHA-256 equals the audited candidate SHA-256.

This gate protects edits the user makes while the agent is working. A final
save after the audits invalidates those audits and requires rerunning them.

## Decide the artifact contract

- Clarify whether the final artifact must be editable PPTX/HTML or visual PDF.
- A screenshot PDF is visually faithful but text is not selectable; editable
  source must remain available for text changes.
- If the user asks for a native PPTX, do not deliver only an image/PDF version.
- If the user asks for "only one file", keep scratch, previews, and backups
  outside the user's delivery folder unless explicitly requested.

## Handle open files safely

- Expect Office/WPS/Preview apps to lock files or show save prompts.
- Prefer read-only inspection, temporary copies, or exported previews when a file
  is open.
- Do not kill Office/WPS processes if unsaved user edits may exist.
- If closing an app is required and risky, ask first.

## Fast path for one HTML file to PDF

- Treat the HTML file's parent as the only asset root; run the HTML audit before export.
- If relative assets are missing, report the exact paths and stop; do not search the desktop or web unless the user asks to recover them.
- If Playwright's default Chromium launch fails, pass any installed Chromium/Chrome/Edge binary to both scripts with `--browser-executable` (or set `DECK_FORGE_BROWSER_EXECUTABLE` once) — Windows `chrome.exe`, Linux `/usr/bin/chromium`, macOS the binary inside `Google Chrome.app`; do not download before this fallback fails.

## Windows path and encoding hygiene

- Use absolute paths for user files, especially paths containing Chinese
  characters or spaces.
- Pass paths as process arguments rather than embedding them in shell-piped
  scripts when possible.
- Use UTF-8 execution settings when reading/writing non-ASCII content.
- If console output shows `????`, check for mojibake before concluding the path
  is wrong.
- Arrow/symbol policy (shared with `references/translation-copyfit.md`):
  prefer real Unicode arrows and verify them in rendered output; if shell
  encoding corrupts them (symbols become `?`), generate the characters by
  Unicode code point inside the script; fall back to ASCII arrows only as a
  last resort.
