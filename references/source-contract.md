# Source contract and file hygiene

Read this before editing when there are multiple source files, versioned files,
user-provided references, or "only one final file" requirements.

## Establish the source of truth

- Record the exact source path, final output path, final format, page count, and
  page order before editing.
- Treat similarly named files as untrusted until compared. Names like `v2`,
  `v3`, `copy`, `(1)`, and `(2)` often do not encode the user's intended source.
- Compare candidate sources by structure and visible content, not by timestamp or
  page number alone.
- For PPTX, compare by true slide order, never by XML filenames; how to derive
  it is in `references/pptx-native-editing.md` (Structural rules).
- For PDF/HTML decks, render pages and compare visuals when content order or
  page mapping matters.

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
