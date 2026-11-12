---
name: deck-forge
description: >-
  Build HTML/PDF slide decks, author and minimally edit native PowerPoint presentations,
  translate or polish slide copy, and compare and visually verify deck versions.
  Use for slide or PPT requests including 做成幻灯片、改 PPT、套用原母版、翻译 PPT 和逐页核查.
---

# Deck Forge

## Choose one track

Read the matching guide. Start with the user's deliverable and how its recipient will edit or present it.

| Request | First guide |
| --- | --- |
| Build a new fixed-stage web presentation or PDF from notes, screenshots, or supplied material. Revise selected HTML slides or export an existing HTML deck. | [HTML build](tracks/html-build.md) |
| Deliver editable PowerPoint. Change a few words, restyle named elements, or author new pages on the source PPTX's own layouts, masters and theme. Choose this route when recipients will frequently edit paragraphs, tables or chart data. | [Native PowerPoint](tracks/pptx-native.md) |
| Translate or polish copy within an existing layout. Check a translation, compare versions, or report visual issues read-only. | [Translation and QA](tracks/translate-and-qa.md) |

An existing PPTX can be authoritative or just source material. If its role and the delivery format are ambiguous, ask whether to preserve it as editable PowerPoint or repurpose its content for HTML/PDF. A real PowerPoint master belongs to the native route. The bundled bold-template pack contains HTML design recipes.

## Establish the source and scope

- Record the exact input, output, format and authorized change. A read-only comparison writes its report and renders to scratch. Keep previews, baselines and QA evidence outside a one-file delivery.
- When materials disagree, record which governs each dimension. Typically the current deck owns package state and live edits, the mother draft owns required claims and teaching sequence, the case file supplies evidence, and the template supplies design. The user's latest instructions govern purpose and scope.
- Treat assistant summaries, review verdicts, proposed rewrites and tracked comments as proposals until the user adopts them. Reassess the affected outline and evidence when the user corrects an interpretation. Keep approved decisions and blanks.
- Keep numbers, claims, units, quotations and attribution traceable. Use a labelled editable field for an answer the audience will fill in. Ask for missing facts that are required for delivery or mark the affected page provisional.
- For an existing deck, `python scripts/forge.py preflight SOURCE --out QA_DIR` checks the environment and records the file's SHA-256 and page count. Work on a copy. Before replacing a live file, check its hash again. If it changed, retain the candidate, rebaseline from the current file and remap the edits. Verify the delivered hash matches the audited candidate. Leave an app with unsaved edits open.

## Run and deliver

Commands in the tracks start at the installed folder containing this file. From another working directory, call the scripts by their absolute paths and quote paths containing spaces. Write new presentations and evidence to the user's project.

Preflight writes `report.json` and the environment log to a new directory. It counts physical PPTX slides, rendered HTML slides or PDF pages (PDF requires `pypdfium2`). The SHA-256 covers the named input file.

Verify the saved artifact after its final write. Trace claims back to their source spans, including subject, unit, period and whether a number is achieved, estimated or proposed. Inspect every rendered page and the specific interactions or native objects the user needs. Report the delivery path, page count, practical editing limits and any checks that could not run.
