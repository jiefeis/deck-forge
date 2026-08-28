# Deck copy and AI-slop cleanup

Read this when slide language sounds AI-generated, too slogan-like, or too
mechanical, especially in Chinese consulting/report decks — and before any
client-facing diagnosis or BD deck goes out (the last two sections are
pre-send editor passes). If the
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
- Client-facing BD copy (distilled from a real client-side edit)

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
the client will read it. Rules 1–4 and 7 apply to ANY page the client will
read — BD included (next section); rules 5, 6, 8, 9 are diagnosis-page
mechanics. Every rule below comes from a real editor rewriting AI-drafted
diagnosis pages before sending to the client.

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

## Client-facing BD copy (distilled from a real client-side edit)

Apply when the deck asks the client to agree to a next step（BD/credentials/
提案页）and the client will read it. Distilled from a client-side
ex-consultant's own pass over an AI-drafted BD deck — 90% of his edits were
deletions. Rules 1–2 are BD-specific; 3–6 apply to any client-facing formal
deck.

1. **承诺性数字：只写敢兜底的数。** 未来动作的量化表述，给不出出处、不敢写进
   合同的，降级或删除：「8–15 名骨干」→「若干名」；「15–25 人访谈」删数字。
   降级不等于禁数字：「3–6 个 Demo」改「3–5 个」——写自己真敢承诺的窄区间。
   已交付项目的数字全部保留（「40 人 6 组」「60+ 候选场景」）。删改后重写
   整句，不留删除的空洞。「Do not change quantities」(Deck-specific rules)
   保护的是已交付的事实；没人兜底的未来数字不是事实，本条优先。

2. **合同边界：不预支合同语言。** 「写进合同」「固定周期 · 固定交付物 · 明确
   价格」不出现在合同签订前的材料里。机制可以讲：「以 OCI 指标达标为退出
   条件」保留——讲退出与验收的机制，不用契约化措辞。

3. **客户在场：被评价的人会读到这页。** 排除式表述、且被排除方是读者（「不选
   IT」而读者就是 IT 部门）：先改正写「以业务骨干为主」，正写仍刺痛读者才删。
   淘汰、砍、考核的对象只能是事不是人：「不行就砍」砍的是场景，可留；「做错
   了淘汰」淘汰的是客户骨干，删。删预设客户失信的句子（「没人回去以后再翻
   案」）和贬低读者的断言（「管理层不是来听课的」）。描述客户内部的会议用
   「沟通／对齐」，不用「吵」。

4. **稻草人对比句：不贬低虚构的差版本抬自己。** 「不是领导指定的」「而不是停
   在『我们要加强 XX』」「只做两个角色」的「只」——删。否定句的唯一合法用途
   是消除读者真实存在的顾虑：「陪跑不是长期驻场」「而不是再交一份报告」保留。
   测试：这句否定回应的是谁提出过的哪条顾虑？答不上来就删；顾虑清单以
   storyline 的 objection beats 与客户说过的话为准（`references/storyline.md`
   → "Deck archetypes"），不自行虚构顾虑。

5. **可推敲性：每个结论能答「这是谁、在哪次交付里说的」。** AI 归纳的因果
   （「……因此同时承接双重职能」的「因此」）冒充调研发现，被追问即穿帮——宁
   可破坏排比也删。实名客户背书与同页匿名案例并存时统一匿名；实名条目须有
   细节撑得住追问，撑不住即匿名或删。

6. **正式度与指代。** 第二人称收敛：「你的组织」→「客户的组织」或删「你的」。
   戏剧化字眼降温，限描述客户世界的：「死」→「静止」（外包交付的下场）；自
   身机制的果断动词「不行就砍」不降（见第 3 条）。指代与命名就地可解析：跨
   过几页后省略的宾语补回（目录「我们已经一起做过什么」→「我们已经和SGM一
   起做过什么」——读者翻过中间几页后指代已丢）；未在本 deck 定义过的命名
   （「四大机制」）就地定义或删。

