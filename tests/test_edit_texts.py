#!/usr/bin/env python3
"""
Regression tests for scripts/edit_texts.py.

Focus: the lxml round-trip must NOT corrupt the deck. These guard the concerns
that a full re-serialize could change inline <script>/<style> content, alter
URLs, drop slides, or touch text the user didn't edit.

Run standalone (no pytest needed):   python tests/test_edit_texts.py
Or under pytest if installed:         python -m pytest tests/
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True  # keep the skill dir clean (no scripts/__pycache__)

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("edit_texts", ROOT / "scripts" / "edit_texts.py")
ET = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ET)

# A deck that exercises the tricky bits: an inline <script> with `<` and `&&`,
# a <style> with a `>` child selector, a font URL with `&`, accent <span>/<em>,
# a mixed number+unit leaf, a visible .deck-controls bar, and CJK text.
SAMPLE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=A:wght@400&family=B&display=swap" rel="stylesheet">
<style>.a > .b{color:red}.slide.active{display:flex}</style>
</head><body>
<div class="deck-viewport"><main class="deck-stage" id="deckStage">
  <section class="slide cover active">
    <h1>让增长<br><em>有迹可循</em></h1>
    <p class="sub">原始副标题</p>
    <div class="big">63<span class="unit">%</span></div>
  </section>
  <section class="slide">
    <h2>第二页</h2>
    <ul><li>要点一</li><li>要点二</li></ul>
    <div class="foot"><span>LUMEN</span><span class="pageno">02</span></div>
  </section>
</main></div>
<div class="deck-controls"><button>prev</button><button>next</button></div>
<script>
class P{constructor(){this.n=document.querySelectorAll('.slide').length;}
go(i){for(let k=0;k<this.n;k++){if(k<i&&i>0){}}}}
window.presentation=new P();
</script>
</body></html>
"""

FAILS: list[str] = []


def check(cond, msg):
    if cond:
        print(f"  PASS  {msg}")
    else:
        print(f"  FAIL  {msg}")
        FAILS.append(msg)


def write(tmp: Path, name: str, text: str) -> Path:
    p = tmp / name
    p.write_text(text, encoding="utf-8")
    return p


def run():
    tmp = Path(tempfile.mkdtemp(prefix="deckforge-test-"))
    html = write(tmp, "deck.html", SAMPLE)
    texts = tmp / "deck.texts.md"

    # --- extract -----------------------------------------------------------
    ET.extract(html, texts)
    txt = texts.read_text(encoding="utf-8")
    html_after_extract = html.read_text(encoding="utf-8")

    check("有迹可循" in txt, "extract: captures CJK + inline-tag leaf")
    check(txt.count("<!-- deck-forge:id=s01") >= 3, "extract: per-slide ids assigned (slide 1)")
    check('data-text-id="s01t01"' in html_after_extract, "extract: stamps ids into HTML")
    check((tmp / "deck.html.bak").exists(), "extract: writes a .bak backup by default")
    # guard the phantom-id regression: the header/comments must not parse as ids,
    # and every parsed id must really exist in the stamped HTML.
    parsed = ET._parse_texts(txt)
    check("..." not in parsed and all("deck-forge" not in k for k in parsed),
          "extract: header text not mis-parsed as a phantom id")
    check(all(f'data-text-id="{k}"' in html_after_extract for k in parsed),
          "extract: every parsed id exists in the HTML")
    # extract must not duplicate accent spans as their own ids
    check("有迹可循" in [b.strip() for b in []] or txt.count("有迹可循") == 1,
          "extract: inline accent not captured as a separate id")

    # lxml re-serialize must preserve script/style/url integrity
    check("window.presentation=new P()" in html_after_extract,
          "round-trip: inline <script> body preserved")
    check("k<i" in html_after_extract, "round-trip: '<' inside <script> not corrupted")
    check(".a > .b{color:red}" in html_after_extract,
          "round-trip: '>' selector inside <style> preserved")
    check("fonts.googleapis.com/css2?family=A" in html_after_extract,
          "round-trip: font URL host/path preserved")
    check(html_after_extract.count('class="slide') == 2,
          "round-trip: no slides dropped/added")

    # --- apply edits -------------------------------------------------------
    # change cover title (keep inline tags), subtitle, and the number-in-mixed-leaf
    new = txt
    new = new.replace("让增长<br><em>有迹可循</em>", "把钱<br><em>花在刀刃上</em>")
    new = new.replace("原始副标题", "改过的副标题")
    new = new.replace('63<span class="unit">%</span>', '72<span class="unit">%</span>')
    texts.write_text(new, encoding="utf-8")

    out = tmp / "deck.out.html"
    ET.apply(html, texts, out)
    res = out.read_text(encoding="utf-8")

    check("花在刀刃上" in res and "<em>花在刀刃上</em>" in res,
          "apply: edited title written back WITH inline <em> preserved")
    check("有迹可循" not in res, "apply: old title text fully replaced")
    check("改过的副标题" in res, "apply: subtitle changed")
    check('72<span class="unit">%</span>' in res,
          "apply: mixed number+unit leaf changed, unit span kept")
    # untouched text must remain
    check("第二页" in res and "要点一" in res, "apply: untouched slides unchanged")
    # script/style still intact after apply too
    check("window.presentation=new P()" in res, "apply: <script> still intact")
    check(".slide.active{display:flex}" in res, "apply: <style> still intact")

    # --- idempotency: applying the same texts again changes nothing --------
    out2 = tmp / "deck.out2.html"
    ET.apply(out, texts, out2)
    check(out.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8"),
          "apply: idempotent (re-apply is a no-op)")

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)   # don't leave test artifacts in %TEMP%

    print()
    if FAILS:
        print(f"RESULT: {len(FAILS)} FAILED")
        sys.exit(1)
    print("RESULT: all passed")


# pytest entry point
def test_round_trip():
    run()


if __name__ == "__main__":
    run()
