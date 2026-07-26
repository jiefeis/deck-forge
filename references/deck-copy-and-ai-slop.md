# Deck copy and AI-slop cleanup

Read this when slide language sounds AI-generated, too slogan-like, or too
mechanical, especially in Chinese consulting/report decks. If the
`humanizer-zh` skill is available and the user mentions "AI 味道太重",
"太像 AI 写的", "语言太 AI 化", or "去 AI 味", use it together with this reference.

On conflict, this file wins for slide copy: take humanizer-zh's pattern
checklist (AI vocabulary, paired structures, dash overuse, rule-of-three,
vague attribution), but ignore its prose-oriented advice to inject
personality, first-person voice, or looseness — deck copy stays short,
factual, and impersonal.

## Contents

- Goal
- Deck-specific rules
- Copyfit after language edits
- Good pattern / Bad pattern
- Client-facing diagnosis copy (distilled from real editor passes)

## Goal

Make the copy sound like something a real presenter would say in a meeting:
shorter, more concrete, and less performative. Preserve the source facts,
numbers, named frameworks, page hierarchy, and visual layout.

## Deck-specific rules

- Prefer direct business wording over slogans. Replace vague phrases such as
  "关键抓手", "形成飞轮", "复利化", "全面赋能", and "闭环放大" with the actual action,
  owner, metric, or next step.
- Avoid mechanical paired structures unless the source explicitly needs them:
  "不是……而是……", "从……到……", "先……再……", and three-part slogans.
- Remove decorative arrows such as `->` from prose. Use normal punctuation or
  convert the relation into a short sentence.
- Keep the source's own domain terms (product names, framework acronyms,
  role/owner labels, scoring devices such as Harvey balls); do not "translate"
  them into plain language.
- Do not make copy "more literary". In decks, humanizing usually means shorter
  and more specific, not more elaborate.
- Do not change facts, dates, scores, quantities, departments, source labels, or
  page numbering.

## Copyfit after language edits

After humanizing copy (or any font-size change), run the copyfit pass in
`references/reformat-and-style.md` → "Font-size and whitespace changes" —
that section is the single authority for the mechanics (render changed pages,
orphans, breaks, collisions, uniform repeated components). Deck-copy addition:

- Keep the label separate from its description. Do not merge a section label
  and explanatory sentence into one paragraph if the source uses a label/value
  hierarchy.

## Good pattern

Source-like AI copy:

> 通过建立高频协同机制，形成业务与 IT 双轮驱动的 AI 落地飞轮。

Better deck copy:

> 业务每周定场景和验收口径，IT 负责接入和上线节奏。

## Bad pattern

- Rewriting a slide into a new storyline because the language feels awkward.
- Shrinking all text until it fits instead of improving the wording.
- Adding side-note boxes or new explanation areas when the user asked for a
  minimal language/layout fix.
- Leaving a page unrendered after text edits because XML/text extraction looked
  correct.

## Client-facing diagnosis copy (distilled from real editor passes)

Apply when the deck evaluates the CLIENT's own plan/work (诊断、审视、评估页) and
the client will read it. Every rule below comes from a real editor rewriting
AI-drafted diagnosis pages before sending to the client.

1. **对事不对人 — soften attack verbs, drop attribution.**
   - 人为割裂 → 有割裂；与业务价值脱钩 → 与业务价值没有联系；方案没回答 →
     方案中缺少说明；"无人回答'业务凭什么用'" → "没有回应，就无法回答'业务为什么用'"。
   - 删去指认式引用：团队自述 / 团队自问 / 领导质疑 / 高管点名"……仍未补上"。
   - 删去说教式"正解：……"。诊断只指出缺口，不当面教怎么做对。
   - 直指组织、人和激励的最尖锐批评（如"无全职团队、无激励"）整行拿掉，或降为口头沟通。
   - 框架级批评改增量式：「不推翻你的架构，补上它缺的另一半」→「在现有架构上，补上三件事」。
   - 不贴判决式标签（"半份好方案"）。

2. **删元叙事。** 舞台指示一律删：「先如实呈现它做了什么、再谈问题」「结论：三个诊断、
   一个答案——」「下一页起，逐一给出行动方案」「把五个问题归并，与前两个诊断收敛」。
   Exhibit 自己说话，不需要旁白。

3. **中文页面不夹英文骨架。** eyebrow 不用 "DIAGNOSIS 03" 式英文编号；删 "What 多、How 少"
   这类中英混排口号；"90 天内" 若客户不讲 90-day 话术，改"短期内"。

4. **用客户自己的词汇系统。** 客户管自己的文件叫"规划"就全文用"规划"不用"方案"；
   价值维度用客户的三分法（提质 / 提效 / 扩量）替换顾问默认词（转化率 / 周期 / 成本 / 质量）；
   见到什么"效果"→ 见到什么"行动"；已"入案"→ 已"纳入"。

5. **表头也要软。** 「方案里的证据」→「规划里的描述」；「为什么是问题」→「规划诊断」。

6. **每格一条主证据。** 保留最硬的一条事实 + 数字，删第二论据、删括号补充、删格内出处。
   证据格只描述对方文件写了什么，不复述谁说过什么。

7. **标点与句式。** 标题承接的"——"改"："或"，"；标题一行说完；"就是当前主流打法"→
   "是当前主流打法"。

8. **出处行。** 证据全部来自客户自己材料的页面，可省去页脚来源行（客户认得自己的文件）；
   引用外部数据的页面保留。

9. **参考架构页发给客户前先本地化。** 行业示例（业务条线、示例智能体）替换为客户自己的
   业务域；标题从叙事式（"××时代催生了……"）改标签式（"××架构：……"）。

