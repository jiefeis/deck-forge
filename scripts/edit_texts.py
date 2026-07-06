#!/usr/bin/env python3
"""
edit_texts.py - Edit all the words in a deck through one plain-text file.

The text-editing capability fused in from rollingai-decks' `data-text-id`
extract / apply workflow. Because the final PDF is a screenshot, you cannot edit
the PDF directly - you edit the deck's text here and re-export:

  1. extract  - pull every editable string into a friendly `<deck>.texts.md`
                file, and stamp each string with a stable `data-text-id` in the
                HTML (auto-injected, so this works on ANY deck-forge /
                frontend-slides deck with no prep).
  2. (you edit `<deck>.texts.md` - change words; leave the marker comments alone.)
  3. apply    - write the edited text back into the HTML by id.
  4. re-run   `export_pdf.py` to get the updated PDF.

Safety: both commands write a one-shot `<file>.bak` backup before modifying the
HTML in place (disable with --no-backup). The marker comment is namespaced
(`deck-forge:id=`) to avoid colliding with comments in the user's own content;
note the texts file is still parsed by matching those markers, so don't paste a
literal `deck-forge:id=` marker into body text (a known v0 boundary).

Usage:
    python edit_texts.py extract <deck.html> [texts.md] [--no-backup]
    python edit_texts.py apply   <deck.html> <texts.md> [out.html] [--no-backup]

Requires: pip install lxml
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

try:
    from lxml import html as LH
except ImportError:
    sys.exit("edit_texts: lxml required. Run: pip install lxml")

MARKER = "deck-forge:id="
_MARKER_RE = re.compile(r"<!--\s*deck-forge:id=(\S+)\s*-->")

INLINE = {"span", "em", "strong", "b", "i", "u", "a", "br", "sub", "sup",
          "mark", "small", "code", "abbr", "wbr", "s", "del", "ins", "q"}
BLOCK_TEXT = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote",
              "figcaption", "caption", "td", "th", "dt", "dd", "div", "label"}


def _backup(path: Path) -> Path:
    bak = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, bak)
    return bak


def _inner_html(el) -> str:
    parts = [el.text or ""]
    for ch in el:
        if ch.tag is LH.etree.Comment:
            continue
        parts.append(LH.tostring(ch, encoding="unicode"))
    return "".join(parts).strip()


def _set_inner_html(el, new_html: str) -> None:
    for ch in list(el):
        el.remove(ch)
    frag = LH.fragment_fromstring(new_html, create_parent="__wrap__")
    el.text = frag.text
    for ch in frag:
        el.append(ch)


def _is_leaf(el) -> bool:
    if not isinstance(el.tag, str) or el.tag not in BLOCK_TEXT:
        return False
    for ch in el:
        if not isinstance(ch.tag, str):
            continue
        if ch.tag not in INLINE:
            return False
    return bool("".join(el.itertext()).strip())


def _slides(doc):
    return doc.xpath(
        "//*[contains(concat(' ', normalize-space(@class), ' '), ' slide ')]")


def extract(html_path: Path, texts_path: Path, backup: bool = True) -> None:
    doc = LH.document_fromstring(html_path.read_text(encoding="utf-8"))
    lines = [f"# Editable text - {html_path.stem}",
             "# Change the text under each marker comment. Leave the marker comment",
             "# lines (the HTML comments above each block) unchanged - they map the",
             "# text back to the deck. Inline tags (line breaks, em, span) are part of",
             "# the text - keep or adjust them.",
             ""]
    total = 0
    for si, slide in enumerate(_slides(doc), start=1):
        label = (slide.get("class") or "slide").replace("slide", "").strip() or f"slide {si}"
        lines.append(f"## Slide {si} - {label}")
        ti = 0
        for el in slide.iter():
            if el is slide or not _is_leaf(el):
                continue
            ti += 1
            tid = el.get("data-text-id")
            if not tid:
                tid = f"s{si:02d}t{ti:02d}"
                el.set("data-text-id", tid)
            lines.append(f"<!-- {MARKER}{tid} -->")
            lines.append(_inner_html(el))
            lines.append("")
            total += 1
        lines.append("")

    if backup:
        print(f"  Backup: {_backup(html_path)}")
    html_path.write_text(
        LH.tostring(doc, encoding="unicode", doctype="<!DOCTYPE html>"),
        encoding="utf-8")
    texts_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Extracted {total} editable strings -> {texts_path}")
    print(f"  Stamped data-text-id into {html_path} (re-saved).")


def _parse_texts(text: str) -> dict[str, str]:
    chunks = _MARKER_RE.split(text)
    out: dict[str, str] = {}
    for i in range(1, len(chunks), 2):
        tid = chunks[i]
        body = chunks[i + 1]
        body = "\n".join(l for l in body.splitlines()
                         if not l.lstrip().startswith("## ")).strip()
        out[tid] = body
    return out


def apply(html_path: Path, texts_path: Path, out_path: Path,
          backup: bool = True) -> None:
    doc = LH.document_fromstring(html_path.read_text(encoding="utf-8"))
    edits = _parse_texts(texts_path.read_text(encoding="utf-8"))
    by_id = {el.get("data-text-id"): el for el in doc.xpath("//*[@data-text-id]")}
    changed = missing = 0
    for tid, new_html in edits.items():
        el = by_id.get(tid)
        if el is None:
            print(f"  WARN: id '{tid}' not found in HTML (skipped)")
            missing += 1
            continue
        if _inner_html(el) != new_html:
            _set_inner_html(el, new_html)
            changed += 1
    if backup and out_path == html_path:
        print(f"  Backup: {_backup(html_path)}")
    out_path.write_text(
        LH.tostring(doc, encoding="unicode", doctype="<!DOCTYPE html>"),
        encoding="utf-8")
    print(f"  Applied {changed} change(s)"
          f"{f', {missing} id(s) missing' if missing else ''} -> {out_path}")
    print("  Now re-run: export_pdf.py <deck.html>")


def main() -> None:
    argv = [a for a in sys.argv[1:] if a != "--no-backup"]
    backup = "--no-backup" not in sys.argv
    if len(argv) < 2 or argv[0] not in ("extract", "apply"):
        sys.exit(__doc__)
    cmd = argv[0]
    html_path = Path(argv[1]).resolve()
    if not html_path.is_file():
        sys.exit(f"edit_texts: file not found: {html_path}")

    if cmd == "extract":
        texts_path = (Path(argv[2]).resolve() if len(argv) > 2
                      else html_path.with_suffix(".texts.md"))
        extract(html_path, texts_path, backup=backup)
    else:
        if len(argv) < 3:
            sys.exit("edit_texts: apply needs a texts.md path")
        texts_path = Path(argv[2]).resolve()
        out_path = (Path(argv[3]).resolve() if len(argv) > 3 else html_path)
        apply(html_path, texts_path, out_path, backup=backup)


if __name__ == "__main__":
    main()
