#!/usr/bin/env python3
"""Audit PPTX page-number sources across slides, layouts, and masters."""

from __future__ import annotations

import argparse
import posixpath
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


def q(prefix: str, tag: str) -> str:
    return f"{{{NS[prefix]}}}{tag}"


def parse_xml(data: bytes) -> ET.Element:
    return ET.fromstring(data)


def part_rels(zf: zipfile.ZipFile, part: str) -> list[tuple[str, str]]:
    folder = posixpath.dirname(part)
    base = posixpath.basename(part)
    rels_part = posixpath.join(folder, "_rels", base + ".rels")
    if rels_part not in zf.namelist():
        return []

    root = parse_xml(zf.read(rels_part))
    out: list[tuple[str, str]] = []
    for rel in root.findall("rel:Relationship", NS):
        rel_type = rel.get("Type", "")
        target = rel.get("Target", "")
        if not target:
            continue
        resolved = (
            target.lstrip("/")
            if target.startswith("/")
            else posixpath.normpath(posixpath.join(folder, target))
        )
        out.append((rel_type, resolved))
    return out


def slide_order(zf: zipfile.ZipFile) -> list[str]:
    pres = parse_xml(zf.read("ppt/presentation.xml"))
    rels = parse_xml(zf.read("ppt/_rels/presentation.xml.rels"))
    rel_map: dict[str, str] = {}
    for rel in rels.findall("rel:Relationship", NS):
        target = rel.get("Target", "")
        if not target:
            continue
        # same absolute/relative Target normalization as part_rels()
        resolved = (
            target.lstrip("/")
            if target.startswith("/")
            else posixpath.normpath(posixpath.join("ppt", target))
        )
        if resolved.startswith("ppt/slides/"):
            rel_map[rel.get("Id")] = resolved
    return [
        rel_map[sld.get(q("r", "id"))]
        for sld in pres.findall(".//p:sldIdLst/p:sldId", NS)
        if sld.get(q("r", "id")) in rel_map
    ]


def shape_text(shape: ET.Element) -> str:
    return "".join(t.text or "" for t in shape.findall(".//a:t", NS)).strip()


def shape_pos(shape: ET.Element) -> tuple[int, int, int, int] | None:
    xfrm = shape.find(".//a:xfrm", NS)
    if xfrm is None:
        return None
    off = xfrm.find("a:off", NS)
    ext = xfrm.find("a:ext", NS)
    if off is None or ext is None:
        return None
    return (
        int(off.get("x", 0)),
        int(off.get("y", 0)),
        int(ext.get("cx", 0)),
        int(ext.get("cy", 0)),
    )


def is_slidenum_field(shape: ET.Element) -> bool:
    return any(
        (fld.get("type") or "").lower() == "slidenum"
        for fld in shape.findall(".//a:fld", NS)
    )


def is_sldnum_placeholder(shape: ET.Element) -> bool:
    ph = shape.find(".//p:ph", NS)
    return ph is not None and ph.get("type") == "sldNum"


def run_sizes(shape: ET.Element) -> set[str]:
    nodes = shape.findall(".//a:rPr", NS) + shape.findall(".//a:endParaRPr", NS)
    return {node.get("sz") for node in nodes if node.get("sz")}


def page_like_shapes(
    root: ET.Element,
    *,
    expected_name: str | None,
    slide_size: tuple[int, int],
) -> list[dict[str, object]]:
    width, height = slide_size
    out: list[dict[str, object]] = []
    for shape in root.findall(".//p:sp", NS):
        cnv = shape.find(".//p:cNvPr", NS)
        name = cnv.get("name", "") if cnv is not None else ""
        text = shape_text(shape)
        pos = shape_pos(shape)

        reasons: list[str] = []
        if expected_name and name == expected_name:
            reasons.append("expected-name")
        if name in {"dfn_page_number", "codex_page_number"}:
            reasons.append("known-custom")
        if is_sldnum_placeholder(shape):
            reasons.append("sldNum-placeholder")
        if is_slidenum_field(shape):
            reasons.append("slidenum-field")
        if (
            pos
            and re.fullmatch(r"\d{1,3}", text)
            and pos[0] > width * 0.70
            and pos[1] > height * 0.82
        ):
            reasons.append("numeric-bottom")

        if reasons:
            out.append(
                {
                    "name": name,
                    "text": text,
                    "pos": pos,
                    "sizes": sorted(run_sizes(shape)),
                    "reasons": reasons,
                }
            )
    return out


def layout_and_master_for_slide(
    zf: zipfile.ZipFile, slide_part: str
) -> tuple[str | None, str | None]:
    layout = None
    master = None
    for rel_type, target in part_rels(zf, slide_part):
        if rel_type.endswith("/slideLayout"):
            layout = target
            break
    if layout:
        for rel_type, target in part_rels(zf, layout):
            if rel_type.endswith("/slideMaster"):
                master = target
                break
    return layout, master


def audit_pptx(path: Path, args: argparse.Namespace) -> int:
    failures: list[str] = []
    with zipfile.ZipFile(path) as zf:
        bad_zip = zf.testzip()
        if bad_zip:
            failures.append(f"zip integrity failed at {bad_zip}")

        slides = slide_order(zf)
        pres = parse_xml(zf.read("ppt/presentation.xml"))
        size_el = pres.find(".//p:sldSz", NS)
        if size_el is None:
            # OOXML default 16:9 slide size in EMU
            print(f"{path}: warning: no p:sldSz element, assuming default "
                  "12192000x6858000 EMU")
            slide_size = (12192000, 6858000)
        else:
            slide_size = (
                int(size_el.get("cx", "0")),
                int(size_el.get("cy", "0")),
            )

        all_inherited: list[tuple[int, str, list[dict[str, object]]]] = []
        direct_problems: list[str] = []
        for idx, slide_part in enumerate(slides, 1):
            slide_nums = page_like_shapes(
                parse_xml(zf.read(slide_part)),
                expected_name=args.expect_name,
                slide_size=slide_size,
            )

            if args.expect_name:
                expected = [s for s in slide_nums if s["name"] == args.expect_name]
                extras = [s for s in slide_nums if s["name"] != args.expect_name]
                if len(expected) != 1:
                    direct_problems.append(
                        f"slide {idx}: expected exactly one {args.expect_name}, found {len(expected)}"
                    )
                elif expected[0]["text"] != str(idx):
                    direct_problems.append(
                        f"slide {idx}: expected text {idx}, found {expected[0]['text']!r}"
                    )
                elif args.expect_size and set(expected[0]["sizes"]) != {args.expect_size}:
                    direct_problems.append(
                        f"slide {idx}: expected size {args.expect_size}, found {expected[0]['sizes']}"
                    )
                if extras:
                    direct_problems.append(f"slide {idx}: extra page markers {extras}")

            layout, master = layout_and_master_for_slide(zf, slide_part)
            for label, part in (("layout", layout), ("master", master)):
                if not part:
                    continue
                nums = page_like_shapes(
                    parse_xml(zf.read(part)),
                    expected_name=args.expect_name,
                    slide_size=slide_size,
                )
                if nums:
                    all_inherited.append((idx, f"{label}:{part}", nums))

        field_parts: list[str] = []
        placeholder_parts: list[str] = []
        for part in zf.namelist():
            if not (
                part.startswith("ppt/slides/")
                or part.startswith("ppt/slideLayouts/")
                or part.startswith("ppt/slideMasters/")
            ) or not part.endswith(".xml"):
                continue
            root = parse_xml(zf.read(part))
            for shape in root.findall(".//p:sp", NS):
                if is_slidenum_field(shape):
                    field_parts.append(part)
                if is_sldnum_placeholder(shape):
                    placeholder_parts.append(part)

    if direct_problems:
        failures.extend(direct_problems)
    if args.fail_on_inherited and all_inherited:
        failures.append(
            "inherited page markers found: "
            + "; ".join(f"slide {idx} via {src}" for idx, src, _ in all_inherited[:20])
        )
    if args.fail_on_inherited and (field_parts or placeholder_parts):
        failures.append(
            f"remaining slidenum fields={len(field_parts)}, placeholders={len(placeholder_parts)}"
        )

    print(f"{path}")
    print(f"  slides: {len(slides)}")
    print(f"  slidenum fields: {len(field_parts)}")
    print(f"  sldNum placeholders: {len(placeholder_parts)}")
    print(f"  inherited slide chains with page markers: {len(all_inherited)}")
    print(f"  status: {'FAIL' if failures else 'OK'}")
    for failure in failures[:20]:
        print(f"  - {failure}")
    return 1 if failures else 0


def main() -> int:
    # Shape text is echoed in failure lines; keep stdout safe on non-UTF-8
    # Windows pipes (GBK/cp1252) instead of crashing with UnicodeEncodeError.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(
        description="Audit page-number sources in PPTX slides, layouts, and masters."
    )
    parser.add_argument("pptx", nargs="+", type=Path)
    parser.add_argument("--expect-name", help="expected direct page-number shape name")
    parser.add_argument(
        "--expect-size",
        help="expected OOXML font size in hundredths of points, e.g. 1100 for 11pt",
    )
    parser.add_argument(
        "--fail-on-inherited",
        action="store_true",
        help="fail if layouts or masters still contain page-number sources",
    )
    args = parser.parse_args()
    code = 0
    for pptx in args.pptx:
        code |= audit_pptx(pptx, args)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
