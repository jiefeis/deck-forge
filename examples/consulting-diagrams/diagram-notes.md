# Consulting diagram atlas

Three internal, illustrative 1920 × 1080 diagrams. `index.html` is the editable artifact: all drawing objects are inline SVG, all labels remain native HTML/SVG text with stable `data-text-id`. No rasterized diagram, generated image, remote asset, client data, or deployed-system claim is used. HTML uses the bundled licensed Noto Sans SC sample subsets described below; PDF is optional and produces static image pages.

## 1. Responsibility swimlane

Claim: make detection, treatment and review ownership explicit.

| Actor | Actions |
| --- | --- |
| 现场 | 现场观测；现场处置 |
| 系统 | 系统识别；自动处置条件判断；系统记录 |
| 工程师 | 工程师复核 |

The six directed handoffs are: observation → recognition (现场数据); recognition → decision (判定); satisfied condition → field treatment (条件满足); unmet conditions (including low confidence) → engineer review (条件不满足（含低置信度）); confirmed review → field treatment (复核确认); treatment → system record (处置结果). The review branch has an owner and an explicit exit. Normal and reviewed instructions enter distinct ports on field treatment, and the result leaves its lower boundary for the system-record node. All connectors end on intended node boundaries.

Lane containment encodes responsibility. Green solid arrows encode work/data flow; ochre solid arrows encode the engineer-review route. Labels preserve meaning without color. Horizontal distance and lane dimensions do not encode time. The page visibly identifies its mechanism as illustrative and leaves automation conditions/thresholds undefined pending field work.

## 2. Proportional delivery-time chain

Claim: waiting is the largest part of the supplied illustrative delivery time.

| Stage | Minutes | Cumulative interval | Drawn x | Drawn width |
| --- | ---: | --- | ---: | ---: |
| 接单 | 10 | 0–10 | 88 | 218 |
| 排队 | 45 | 10–55 | 306 | 981 |
| 加工 | 15 | 55–70 | 1287 | 327 |
| 检验 | 5 | 70–75 | 1614 | 109 |
| 交付 | 5 | 75–80 | 1723 | 109 |

Encoding: a continuous 0–80 minute domain with `x = 88 + cumulative_minutes × 21.8`; widths equal `minutes × 21.8`. All bars share the same vertical range. Thin separators mark stage boundaries without changing the segment dimensions. The completed track ends at x = 1832 and totals 1744 pixels. This is a proportional time track, not equal-sized topic cards.

Checks: 10 + 45 + 15 + 5 + 5 = 80 minutes; waiting = 45 / 80 = 56.25%; other four stages = 35 minutes. The page labels the values “示例数据，非客户结果”, states that there is no measured period, and does not invent any post-improvement result. The chart identifies a time concentration; it does not prove a throughput bottleneck.

## 3. Loss categories and an untested hypothesis

The root “交付损失” is classified into “等待损失”, “质量损失”, and “切换损失”. Their supporting materials are “排队时间戳”, “返工记录”, and “换型记录”. Plain hierarchy lines have no arrowheads and denote classification/support, not causation or measured contribution. The branches are a categorization framework and are explicitly not added together.

The separate “排程频繁变更” object connects to “等待损失” through one ochre dashed arrow, labeled “可能增加等待” and “待检验假设”. It asserts a proposed direction to test, not proven or quantified causality. The evidence boundary asks for logs to be aligned before this relationship is established. Its route uses the left corridor and enters the waiting node from the side, separate from the hierarchy connection above.

## Visual acceptance

The primary exhibits are respectively responsibility transfer, exact proportional time, and category/hypothesis distinction. Every drawn relation maps to one of the stated semantics. No connector passes through an unrelated node. Native labels, distinct line styles, explanatory legends and visible evidence boundaries preserve the meaning without relying on color alone. Revalidate the actual HTML and interactions after each change; an earlier PDF render does not cover visible navigation.

One focused repair cycle moved the normal-route condition label clear of the review route and added visible internal time-stage separators. No required edge or content was removed. The source has no personal paths or generated login artifacts and is suitable for inclusion as a public-safe internal example.

## HTML delivery

The example loads licensed Noto Sans SC 400/700 sample subsets from the sibling
consulting-visuals/assets/fonts folder. Keep that folder when copying the HTML,
or embed the fonts for a single-file delivery. Source/license notes are in that
folder; refresh subsets after introducing new glyphs. Viewer controls occupy a
reserved band outside the scaled stage. Keyboard input respects native controls
and editing focus.
