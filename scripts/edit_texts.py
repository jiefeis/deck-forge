#!/usr/bin/env python3
"""Round-trip editable HTML deck copy through one Markdown file.

``extract`` assigns stable ``data-text-id`` values to editable text leaves and
writes their inner HTML to a Markdown companion. ``apply`` reads that companion
and updates matching leaves. In-place writes create ``.bak`` files unless
``--no-backup`` is used.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import Sequence

try:
    from lxml import etree
    from lxml import html as lhtml
except ImportError:
    sys.exit("edit_texts: lxml required. Run: pip install lxml")


MARKER = "deck-forge:id="
MARKER_RE = re.compile(r"<!--\s*deck-forge:id=(\S+)\s*-->")
SLIDE_SECTION_RE = re.compile(r"^## Slide \d+ - .+$")
INLINE_TAGS = frozenset(
    {
        "a", "abbr", "b", "br", "code", "del", "em", "i", "ins", "mark",
        "q", "s", "small", "span", "strong", "sub", "sup", "u", "wbr",
    }
)
TEXT_CONTAINER_TAGS = frozenset(
    {
        "blockquote", "caption", "dd", "div", "dt", "figcaption", "h1", "h2",
        "h3", "h4", "h5", "h6", "label", "li", "p", "td", "th",
    }
)


def _make_backup(path: Path) -> Path:
    destination = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, destination)
    return destination


def _parse_document(path: Path):
    return lhtml.document_fromstring(path.read_text(encoding="utf-8"))


def _write_document(document, path: Path) -> None:
    rendered = lhtml.tostring(
        document,
        encoding="unicode",
        doctype="<!DOCTYPE html>",
    )
    path.write_text(rendered, encoding="utf-8")


def _inner_html(element) -> str:
    fragments: list[str] = [element.text or ""]
    for child in element:
        if isinstance(child, etree._Comment):
            fragments.append(child.tail or "")
        else:
            fragments.append(lhtml.tostring(child, encoding="unicode"))
    return "".join(fragments).strip()


def _replace_inner_html(element, value: str) -> None:
    for child in list(element):
        element.remove(child)
    wrapper = lhtml.fragment_fromstring(value, create_parent="deckforge-fragment")
    element.text = wrapper.text
    for child in list(wrapper):
        wrapper.remove(child)
        element.append(child)


def _is_editable_leaf(element) -> bool:
    if not isinstance(element.tag, str) or element.tag.casefold() not in TEXT_CONTAINER_TAGS:
        return False
    if not "".join(element.itertext()).strip():
        return False
    return all(
        not isinstance(child.tag, str) or child.tag.casefold() in INLINE_TAGS
        for child in element
    )


def _slide_nodes(document) -> list[object]:
    return document.xpath(
        "//*[contains(concat(' ', normalize-space(@class), ' '), ' slide ')]"
    )


def _next_text_id(slide_number: int, ordinal: int, used: set[str]) -> tuple[str, int]:
    candidate_ordinal = ordinal
    while True:
        candidate = f"s{slide_number:02d}t{candidate_ordinal:02d}"
        if candidate not in used:
            return candidate, candidate_ordinal
        candidate_ordinal += 1


def extract(html_path: Path, texts_path: Path, backup: bool = True) -> None:
    document = _parse_document(html_path)
    used_ids = set(document.xpath("//*[@data-text-id]/@data-text-id"))
    output = [
        f"# Editable text - {html_path.stem}",
        "# Edit content below each marker. Keep marker comments unchanged.",
        "# Inline HTML such as <em>, <span>, and <br> is preserved.",
        "",
    ]
    count = 0

    for slide_number, slide in enumerate(_slide_nodes(document), 1):
        classes = [part for part in (slide.get("class") or "").split() if part != "slide"]
        label = " ".join(classes) or f"slide {slide_number}"
        output.append(f"## Slide {slide_number} - {label}")
        ordinal = 0
        for element in slide.iter():
            if element is slide or not _is_editable_leaf(element):
                continue
            ordinal += 1
            text_id = element.get("data-text-id")
            if not text_id:
                text_id, ordinal = _next_text_id(slide_number, ordinal, used_ids)
                element.set("data-text-id", text_id)
            used_ids.add(text_id)
            output.extend(
                [
                    f"<!-- {MARKER}{text_id} -->",
                    _inner_html(element),
                    "",
                ]
            )
            count += 1
        output.append("")

    if backup:
        print(f"  Backup: {_make_backup(html_path)}")
    _write_document(document, html_path)
    texts_path.write_text("\n".join(output), encoding="utf-8")
    print(f"  Extracted {count} editable strings -> {texts_path}")
    print(f"  Stamped data-text-id into {html_path} (re-saved).")


def _clean_text_block(block: str) -> str:
    lines = [line for line in block.splitlines() if not SLIDE_SECTION_RE.match(line)]
    return "\n".join(lines).strip()


def _parse_texts(text: str) -> dict[str, str]:
    matches = list(MARKER_RE.finditer(text))
    result: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        text_id = match.group(1)
        if text_id in result:
            print(f"  WARN: duplicate marker '{text_id}' in texts file (last one wins)")
        result[text_id] = _clean_text_block(text[match.end():end])
    return result


def _elements_by_text_id(document) -> dict[str, object]:
    result: dict[str, object] = {}
    for element in document.xpath("//*[@data-text-id]"):
        text_id = element.get("data-text-id")
        if text_id in result:
            print(f"  WARN: duplicate data-text-id '{text_id}' in HTML (last one wins)")
        result[text_id] = element
    return result


def apply(
    html_path: Path,
    texts_path: Path,
    out_path: Path,
    backup: bool = True,
) -> None:
    document = _parse_document(html_path)
    requested = _parse_texts(texts_path.read_text(encoding="utf-8"))
    elements = _elements_by_text_id(document)
    changed = 0
    missing: list[str] = []

    for text_id, replacement in requested.items():
        element = elements.get(text_id)
        if element is None:
            print(f"  WARN: id '{text_id}' not found in HTML (skipped)")
            missing.append(text_id)
            continue
        if _inner_html(element) != replacement:
            _replace_inner_html(element, replacement)
            changed += 1

    if backup and out_path == html_path:
        print(f"  Backup: {_make_backup(html_path)}")
    _write_document(document, out_path)
    suffix = f", {len(missing)} id(s) missing" if missing else ""
    print(f"  Applied {changed} change(s){suffix} -> {out_path}")
    print("  Now re-run: export_pdf.py <deck.html>")
    if missing:
        print(f"  WARNING: {len(missing)} edit(s) NOT applied (ids not found)")
        raise SystemExit(2)


def _existing_file(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"file not found: {path}")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    extract_parser = commands.add_parser("extract", help="write editable copy to Markdown")
    extract_parser.add_argument("html", type=_existing_file)
    extract_parser.add_argument("texts", nargs="?", type=Path)
    extract_parser.add_argument("--no-backup", action="store_true")

    apply_parser = commands.add_parser("apply", help="apply Markdown copy to HTML")
    apply_parser.add_argument("html", type=_existing_file)
    apply_parser.add_argument("texts", type=_existing_file)
    apply_parser.add_argument("output", nargs="?", type=Path)
    apply_parser.add_argument("--no-backup", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "extract":
        texts_path = (
            args.texts.expanduser().resolve()
            if args.texts is not None
            else args.html.with_suffix(".texts.md")
        )
        extract(args.html, texts_path, backup=not args.no_backup)
    else:
        output = (
            args.output.expanduser().resolve()
            if args.output is not None
            else args.html
        )
        apply(args.html, args.texts, output, backup=not args.no_backup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
