# 12 · Mother draft, case evidence, template, and current PPTX disagree

**Contract under test:** Each source governs a different dimension; no single
reference may silently replace the others.

## Setup

Provide:

- current native PPTX with the latest package/order/hidden state
- mother draft with required page claims, reasons, and sequence
- case PDF with factual evidence
- visual template with a distinct font, density, layout, and narrative rhythm

Make the template's sample text conflict with the mother draft.

## User prompt (verbatim)

> 按母稿内容重做当前PPT，案例事实看PDF，风格和叙述方式参考模板。不要改变当前文件里的隐藏页和备注。

## PASS criteria

- The agent records a source-authority matrix.
- Current PPTX owns package structure and latest edits.
- Mother draft owns required content and teaching sequence.
- Case PDF supplies evidence only.
- Template supplies composition, typography, density, and narrative rhythm—not
  its sample claims.
- Every mother-draft content block is traced to the final slides.

## FAIL signals

- Copying the template's example narrative into the course.
- Matching only template colors/fonts while ignoring its composition rhythm.
- Letting the case PDF invent a conclusion absent from the mother draft.
- Rebuilding the native PPTX as a visual-only deck.
