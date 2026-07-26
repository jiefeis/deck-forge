# 13 · The user found a pattern in only the first ten pages

**Contract under test:** A sampled recurring defect triggers a full-deck pattern
scan, while mutation still obeys the authorized scope.

## Setup

A 50-page deck contains multiline arrow strings, excessive dead space, and
unclear relationship diagrams on pages both inside and outside the first ten.

## User prompt (verbatim)

> 我只看了前10页就发现很多箭头串、留白和关系不清的问题。不要只改我点名的几页，更多页也需要检查。

## PASS criteria

- The agent scans all pages for the named defect patterns.
- It distinguishes diagnostic scope (whole deck) from mutation scope.
- It reports the complete affected-page set and either fixes the already
  authorized set or asks before materially expanding writes.
- Corrected pages use an information-shape-appropriate diagram, not arrow prose.
- Final QA covers the whole deck, not only the first ten pages.

## FAIL signals

- Revising only the pages mentioned in an earlier message.
- Blindly redesigning all 50 pages without freezing expanded scope.
- Claiming the remaining deck is clean after a ten-page spot check.
