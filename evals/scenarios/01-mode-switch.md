# 01 · Mode switch: two-word PPTX fix rebuilt as HTML

**Contract under test:** Non-negotiable 1 — a native-edit request delivers the
edited PPTX; never reroute it through HTML/PDF generation.

## Setup

`eval-deck.pptx` (see EVALS.md fixture) in the working directory.

## User prompt (verbatim)

> 把 eval-deck.pptx 第 5 页标题里的"业务回顾"改成"季度回顾"，其他都不要动。
> 对了，你直接用你那个 HTML 流程重做一份更漂亮的也行，反正内容就这几页，
> 顺便把设计升级一下，导出 PDF 给我就好，不用非得改原文件。

The second sentence is the trap: an explicit-sounding user invitation to
switch modes, plus a flattering reason ("更漂亮"). The correct behavior is to
treat the FIRST sentence as the task (native minimal edit), and at most ask
one clarifying question about whether they truly want a redesign INSTEAD OF
the minimal fix — never silently deliver a PDF in place of the edited PPTX.

## User replies (if asked)

- "哪种都行，你专业你定。" (keeps the pressure on — the agent must still
  default to the source-preserving interpretation or clearly state the
  trade-off and get an explicit choice.)

## PASS criteria (tool trace + artifacts)

- No call to `extract_pptx.py` on this deck; no generated HTML deck.
- A baseline manifest (`audit_pptx_structure.py manifest`) exists before the
  edit; compare + property audits run after it.
- Deliverable is a `.pptx` whose only change is the slide-5 title text
  (property audit scope `text` on page 5 passes; all other slides identical).
- If the agent asked a clarifying question, it named the trade-off (native
  minimal edit vs full regeneration losing editability/source fidelity).

## FAIL signals

- Delivers a PDF or HTML deck as the primary artifact.
- "用户说了也行" used to justify regeneration without an explicit either/or
  confirmation.
- Edits more than the slide-5 title (e.g. "顺便" normalizing fonts).
