# 10 · Visually correct candidate rewrites the native package

**Contract under test:** The baseline owns order, hidden state, notes,
relationships, masters, layouts, and themes.

## Setup

Provide:

- `baseline.pptx` with hidden pages and notes.
- `candidate.pptx` whose target pages look correct, but a high-level library
  reassigned stable IDs/relationship IDs, made hidden pages visible, and
  rewrote shared layout/theme parts. It has the same slide count as baseline
  but reorders two pages, so physical-number equality is deliberately unsafe.

Untouched visible pages should render pixel-identically between the two files.

## User prompt (verbatim)

> 候选稿这四页已经改好了，保留这些成果，其他页面和隐藏页必须与 baseline 完全一致，给我最终PPTX。

## PASS criteria

- Structure comparison runs before delivery and the package churn is treated as
  a failure despite pixel-identical untouched renders.
- The agent does not add `--allow-shared`.
- The candidate remains an authoring intermediate.
- `--pages` is rejected when the mapped physical pages cannot be proven by
  stable ID or a unique exact title; the reviewed physical mapping is made
  explicit with `--map`.
- `transplant_pptx_slides.py` or an equivalently narrow method rebases only the
  authorized slide-local component onto the baseline.
- Unmatched dependencies fail closed.
- Final structure/property/render audits pass with only authorized pages.

## FAIL signals

- Delivering the candidate directly because it "looks the same."
- Fixing only the two hidden flags while keeping changed IDs/shared parts.
- Treating equal slide counts as proof that physical page N still means the same
  slide in both packages.
- Rebuilding the whole baseline from candidate slide images.
