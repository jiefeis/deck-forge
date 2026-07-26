# 07 · Hidden-page coordinate shift

**Contract under test:** Physical, visible, displayed, stable-ID, and mother
page identities must be mapped explicitly; hidden pages remain protected.

## Setup

- `current.pptx`: 52 physical pages, with physical pages 15 and 52 hidden.
  Visible ordinals are 1–50, while displayed markers are 101–150.
- `mother.md`: 50 visible/source pages with exact titles.
- Physical page 31 matches mother page 30 by title/content; physical 41 matches
  mother 40. Their visible ordinals are 30/40 and displayed markers are
  130/140.

## User prompt (verbatim)

> 我刚加了两张隐藏页。你改第2、4、31、41页，我说的是加完隐藏页后的当前物理页码；对照母稿时忽略隐藏页。隐藏页本身不要动。

## PASS criteria

- A baseline manifest is produced before mutation and reports 52 physical / 50
  visible slides, with physical 15 and 52 hidden.
- The scope ledger records physical page, stable ID, hidden state, visible
  ordinal, displayed marker, title, and mother page as separate fields.
- Physical 31 maps to mother 30 and physical 41 maps to mother 40 by
  title/content anchors, not by `slideN.xml` filenames.
- Only physical pages 2, 4, 31, and 41 change.
- Hidden pages remain hidden and pixel-identical to baseline.
- Page-number audit still reports exactly 50 sequential displayed markers,
  101–150, without treating them as visible ordinals.

## FAIL signals

- Editing physical 30/40 because mother pages are 30/40.
- Treating physical 31 as mother 31 despite mismatched title/content.
- Deleting hidden pages to make both decks contain 50 physical pages.
- Excluding hidden pages from final structure or render verification.
- Treating displayed marker 130 as physical page or visible ordinal 130.
