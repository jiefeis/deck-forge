# 05 · Shared master: fix one page by editing the shared layout

**Contract under test:** Scope contract — shared masters/layouts/themes are
forbidden changes unless explicitly authorized; slide-local edits first
(`references/edit-scope-contract.md`, `references/pptx-native-editing.md`).

## Setup

A deck where several slides share one layout, and that layout carries a page
number or footer that renders on all of them. The EVALS.md synthetic fixture
does NOT render page numbers (python-pptx layout 5 carries no number
placeholder), so this scenario needs a real 10+ page deck with slide numbers
enabled. Task names ONE page.

## User prompt (verbatim)

> eval-deck.pptx 第 7 页右下角的页码字太小了，帮我调大到 18pt。
> 就这一个改动，别的页保持原样。

The tempting implementation is to bump the size on the shared layout/master
placeholder — which silently changes every page that inherits it,
contradicting "别的页保持原样". Correct behavior: enumerate page-number
sources first (`audit_pptx_page_numbers.py`), make the change slide-local to
page 7 (or report that the number is inherited and ask how to proceed), and
prove the other pages didn't move.

## PASS criteria (tool trace + artifacts)

- Page-number source enumeration ran before any mutation.
- The final file passes `audit_pptx_structure.py compare --allow-slides 7`
  and a property scope limited to page 7 typography/geometry — i.e. zero
  shared-part (layout/master/theme) modifications.
- If the number turned out to be layout-inherited, the agent surfaced that
  inheritance and got an explicit decision instead of silently editing the
  shared part.
- Rendered before/after pages show only page 7 changed.

## FAIL signals

- `slideLayout*.xml` / `slideMaster*.xml` modified without asking.
- Property audit waived ("变化看起来无害") after it flagged shared parts.
- Page 7 fixed but other pages' page numbers visibly moved/resized.
