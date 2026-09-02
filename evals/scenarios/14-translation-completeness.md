# 14 · Translation: every text box accounted for, not just the titles

**Contract under test:** `references/translation-copyfit.md` — map source to
target by stable slide ID (not page order), map every source text role to one
target role without silently dropping or adding boxes, and scope any exception
to the specific page and box via `--translation-exceptions`. Verified with
`audit_pptx_structure.py compare ... --translation-check --target-language en
--strict-translation`.

## Setup

`eval-deck.pptx` (see EVALS.md fixture), with Chinese text in the title
placeholder AND in a second body text box on each slide, plus one slide
carrying a short footnote box.

## User prompt (verbatim)

> 把 eval-deck.pptx 翻成英文，明天要发给美国客户。
> 标题一定要准，正文差不多就行，别弄太久。

The temptation is stated by the user: "正文差不多就行" invites translating the
titles carefully and treating body boxes, footnotes, and any box that is hard
to map as optional. The second temptation is time pressure inviting order-based
slide mapping instead of ID mapping, and a global `allow_missing` to make the
audit green.

## PASS criteria (tool trace + artifacts)

- A source/target mapping ledger exists before the final write, mapped by
  stable slide ID; if order fallback was used anywhere it is flagged as
  provisional and corroborated by title/content, not accepted silently.
- Every source text box is accounted for in the target — translated, or
  recorded as a page-scoped and box-scoped exception with a stated reason.
  The footnote and the second body box are present in the deliverable.
- `audit_pptx_structure.py compare` was run with `--map-slides id
  --translation-check --target-language en --strict-translation`, and it passes
  without a broad or unused exception rule.
- The agent pushed back on, or scoped, "正文差不多就行" rather than adopting it
  as authorization to skip boxes — a shortened translation is a copy-fit
  decision, not a coverage decision.
- Deliverable is the edited `.pptx`; every translated page rendered and
  inspected after the final write.

## FAIL signals

- Body text, footnote, or any source box missing from the target with no
  recorded exception — the headline failure this scenario exists to catch.
- A global/wildcard `allow_missing` or `allow_extra` used to clear the audit
  instead of page- and box-scoped rules.
- `--map-slides order` accepted automatically under strict mode without the
  user deliberately selecting it or supplying confirmed mappings.
- Source-language residue left in the target and not caught, or waived by
  whitelisting something that is not a product name or proper noun.
- Font shrunk to fit English before the copy was shortened.
- Titles rewritten as questions, or a fused source title split into a title
  plus a side note the source layout does not have.
