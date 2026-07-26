#!/usr/bin/env python3
"""Strictly audit direct and native page-number sources in PPTX files."""

from __future__ import annotations

import argparse
import posixpath
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}

DEFAULT_SLIDE_SIZE = (12192000, 6858000)
NUMBER_TEXT_RE = re.compile(r"[0-9]+")


@dataclass(frozen=True)
class Marker:
    name: str
    text: str
    sizes: tuple[int, ...]


@dataclass(frozen=True)
class PartMarkers:
    direct: tuple[Marker, ...]
    native: tuple[Marker, ...]


@dataclass(frozen=True)
class SourceMarkers:
    level: str
    part: str
    markers: tuple[Marker, ...]


@dataclass(frozen=True)
class SlideInfo:
    physical_number: int
    part: str
    hidden: bool
    direct: tuple[Marker, ...]
    native_sources: tuple[SourceMarkers, ...]
    inherited_manual_sources: tuple[SourceMarkers, ...]


def q(prefix: str, tag: str) -> str:
    return f"{{{NS[prefix]}}}{tag}"


def parse_xml(data: bytes) -> ET.Element:
    return ET.fromstring(data)


def xml_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "off", "no"}


def resolve_target(folder: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(folder, target))


def part_rels(zf: zipfile.ZipFile, part: str) -> list[tuple[str, str]]:
    folder = posixpath.dirname(part)
    base = posixpath.basename(part)
    rels_part = posixpath.join(folder, "_rels", base + ".rels")
    if rels_part not in zf.namelist():
        return []

    root = parse_xml(zf.read(rels_part))
    out: list[tuple[str, str]] = []
    for rel in root.findall("rel:Relationship", NS):
        if (rel.get("TargetMode") or "").lower() == "external":
            continue
        rel_type = rel.get("Type", "")
        target = rel.get("Target", "")
        if target:
            out.append((rel_type, resolve_target(folder, target)))
    return out


def slide_order(zf: zipfile.ZipFile) -> list[str]:
    pres = parse_xml(zf.read("ppt/presentation.xml"))
    rels = parse_xml(zf.read("ppt/_rels/presentation.xml.rels"))
    rel_map: dict[str, str] = {}
    for rel in rels.findall("rel:Relationship", NS):
        if (rel.get("TargetMode") or "").lower() == "external":
            continue
        target = rel.get("Target", "")
        rel_id = rel.get("Id")
        if not target or not rel_id:
            continue
        resolved = resolve_target("ppt", target)
        if resolved.startswith("ppt/slides/"):
            rel_map[rel_id] = resolved

    order: list[str] = []
    for sld in pres.findall("./p:sldIdLst/p:sldId", NS):
        rel_id = sld.get(q("r", "id"))
        if not rel_id or rel_id not in rel_map:
            raise KeyError(f"slide relationship {rel_id!r} is missing")
        order.append(rel_map[rel_id])
    return order


def shape_text(shape: ET.Element) -> str:
    return "".join(t.text or "" for t in shape.findall(".//a:t", NS)).strip()


def shape_pos(shape: ET.Element) -> tuple[int, int, int, int] | None:
    xfrm = shape.find("./p:spPr/a:xfrm", NS)
    if xfrm is None:
        return None
    off = xfrm.find("a:off", NS)
    ext = xfrm.find("a:ext", NS)
    if off is None or ext is None:
        return None
    return (
        int(off.get("x", "0")),
        int(off.get("y", "0")),
        int(ext.get("cx", "0")),
        int(ext.get("cy", "0")),
    )


def shape_name(shape: ET.Element) -> str:
    cnv = shape.find("./p:nvSpPr/p:cNvPr", NS)
    return cnv.get("name", "") if cnv is not None else ""


def is_slidenum_field(shape: ET.Element) -> bool:
    return any(
        (fld.get("type") or "").lower() == "slidenum"
        for fld in shape.findall(".//a:fld", NS)
    )


def is_sldnum_placeholder(shape: ET.Element) -> bool:
    return any(
        (ph.get("type") or "").lower() == "sldnum"
        for ph in shape.findall(".//p:ph", NS)
    )


def run_sizes(shape: ET.Element) -> tuple[int, ...]:
    nodes: list[ET.Element] = []
    for path in (".//a:rPr", ".//a:defRPr", ".//a:endParaRPr"):
        nodes.extend(shape.findall(path, NS))
    return tuple(sorted({int(node.get("sz")) for node in nodes if node.get("sz")}))


def is_bottom_right(
    pos: tuple[int, int, int, int] | None,
    slide_size: tuple[int, int],
) -> bool:
    if pos is None:
        return False
    x, y, cx, cy = pos
    width, height = slide_size
    if width <= 0 or height <= 0:
        return False

    center_x = x + cx / 2
    center_y = y + cy / 2
    right = x + cx
    return (
        center_y >= height * 0.78
        and (center_x >= width * 0.70 or right >= width * 0.90)
    )


def page_markers(root: ET.Element, slide_size: tuple[int, int]) -> PartMarkers:
    direct: list[Marker] = []
    native: list[Marker] = []
    for shape in root.findall(".//p:sp", NS):
        text = shape_text(shape)
        pos = shape_pos(shape)
        placeholder = is_sldnum_placeholder(shape)
        field = is_slidenum_field(shape)
        marker = Marker(
            name=shape_name(shape),
            text=text,
            sizes=run_sizes(shape),
        )
        if placeholder or field:
            # A native shape commonly contains both tags. It is still one source.
            native.append(marker)
        elif NUMBER_TEXT_RE.fullmatch(text) and is_bottom_right(pos, slide_size):
            direct.append(marker)
    return PartMarkers(tuple(direct), tuple(native))


def native_numbers_enabled(root: ET.Element) -> bool:
    header_footer = root.find("./p:hf", NS)
    if header_footer is None:
        return True
    return xml_bool(header_footer.get("sldNum"), default=True)


def layout_and_master_for_slide(
    zf: zipfile.ZipFile, slide_part: str
) -> tuple[str | None, str | None]:
    layout = next(
        (
            target
            for rel_type, target in part_rels(zf, slide_part)
            if rel_type.endswith("/slideLayout")
        ),
        None,
    )
    master = None
    if layout:
        master = next(
            (
                target
                for rel_type, target in part_rels(zf, layout)
                if rel_type.endswith("/slideMaster")
            ),
            None,
        )
    return layout, master


def slide_size(presentation: ET.Element) -> tuple[int, int]:
    size_el = presentation.find("./p:sldSz", NS)
    if size_el is None:
        return DEFAULT_SLIDE_SIZE
    width = int(size_el.get("cx", "0"))
    height = int(size_el.get("cy", "0"))
    return (width, height) if width > 0 and height > 0 else DEFAULT_SLIDE_SIZE


def collect_slides(
    zf: zipfile.ZipFile,
    slides: list[str],
    size: tuple[int, int],
) -> list[SlideInfo]:
    root_cache: dict[str, ET.Element] = {}
    marker_cache: dict[str, PartMarkers] = {}

    def root_for(part: str) -> ET.Element:
        if part not in root_cache:
            root_cache[part] = parse_xml(zf.read(part))
        return root_cache[part]

    def markers_for(part: str) -> PartMarkers:
        if part not in marker_cache:
            marker_cache[part] = page_markers(root_for(part), size)
        return marker_cache[part]

    records: list[SlideInfo] = []
    for physical_number, slide_part in enumerate(slides, 1):
        slide_root = root_for(slide_part)
        slide_markers = markers_for(slide_part)
        layout, master = layout_and_master_for_slide(zf, slide_part)

        native_sources: list[SourceMarkers] = []
        inherited_manual: list[SourceMarkers] = []
        if slide_markers.native:
            native_sources.append(
                SourceMarkers("slide", slide_part, slide_markers.native)
            )

        layout_root = root_for(layout) if layout else None
        layout_native_enabled = (
            native_numbers_enabled(layout_root) if layout_root is not None else True
        )
        if layout:
            layout_markers = markers_for(layout)
            if layout_native_enabled and layout_markers.native:
                native_sources.append(
                    SourceMarkers("layout", layout, layout_markers.native)
                )
            if layout_markers.direct:
                inherited_manual.append(
                    SourceMarkers("layout", layout, layout_markers.direct)
                )

        master_is_shown = xml_bool(slide_root.get("showMasterSp"), default=True)
        if layout_root is not None:
            master_is_shown = master_is_shown and xml_bool(
                layout_root.get("showMasterSp"), default=True
            )
        if master and master_is_shown:
            master_root = root_for(master)
            master_markers = markers_for(master)
            if (
                layout_native_enabled
                and native_numbers_enabled(master_root)
                and master_markers.native
            ):
                native_sources.append(
                    SourceMarkers("master", master, master_markers.native)
                )
            if master_markers.direct:
                inherited_manual.append(
                    SourceMarkers("master", master, master_markers.direct)
                )

        records.append(
            SlideInfo(
                physical_number=physical_number,
                part=slide_part,
                hidden=not xml_bool(slide_root.get("show"), default=True),
                direct=slide_markers.direct,
                native_sources=tuple(native_sources),
                inherited_manual_sources=tuple(inherited_manual),
            )
        )
    return records


def numbered_scope(records: list[SlideInfo], numbering: str) -> list[SlideInfo]:
    if numbering == "visible":
        return [record for record in records if not record.hidden]
    return records


def expected_numbers(
    records: list[SlideInfo], numbering: str
) -> dict[int, int]:
    if numbering == "none":
        return {}
    if numbering == "physical":
        return {
            record.physical_number: record.physical_number for record in records
        }
    return {
        record.physical_number: visible_number
        for visible_number, record in enumerate(records, 1)
    }


def source_summary(source: SourceMarkers) -> str:
    return f"{source.level}:{source.part} ({len(source.markers)})"


def slide_list(numbers: list[int]) -> str:
    shown = ", ".join(str(number) for number in numbers[:20])
    return shown + (", ..." if len(numbers) > 20 else "")


def validate_direct_marker(
    record: SlideInfo,
    marker: Marker,
    expected_number: int | None,
    expect_name: str | None,
    expect_size: int | None,
    failures: list[str],
) -> None:
    if expected_number is not None and int(marker.text) != expected_number:
        failures.append(
            f"slide {record.physical_number}: expected page number "
            f"{expected_number}, found {marker.text!r}"
        )
    if expect_name is not None and marker.name != expect_name:
        failures.append(
            f"slide {record.physical_number}: expected page-number name "
            f"{expect_name!r}, found {marker.name!r}"
        )
    if expect_size is not None and marker.sizes != (expect_size,):
        failures.append(
            f"slide {record.physical_number}: expected page-number size "
            f"{expect_size}, found {list(marker.sizes)}"
        )


def audit_open_pptx(
    zf: zipfile.ZipFile,
    args: argparse.Namespace,
) -> tuple[list[str], dict[str, object]]:
    failures: list[str] = []
    names = zf.namelist()
    duplicate_parts = sorted(name for name, count in Counter(names).items() if count > 1)
    if duplicate_parts:
        failures.append(
            "duplicate ZIP parts: " + ", ".join(duplicate_parts[:10])
        )
    bad_zip = zf.testzip()
    if bad_zip:
        failures.append(f"ZIP integrity failed at {bad_zip}")

    presentation = parse_xml(zf.read("ppt/presentation.xml"))
    ordered_parts = slide_order(zf)
    records = collect_slides(zf, ordered_parts, slide_size(presentation))
    scoped = numbered_scope(records, args.numbering)
    expected = expected_numbers(scoped, args.numbering)

    direct_count = sum(len(record.direct) for record in scoped)
    has_direct = direct_count > 0
    has_native = any(record.native_sources for record in scoped)
    has_inherited_manual = any(
        record.inherited_manual_sources for record in scoped
    )

    if args.mode == "auto":
        if has_direct:
            effective_mode = "direct"
        elif has_native or has_inherited_manual:
            effective_mode = "native"
        elif args.numbering == "none":
            effective_mode = "none"
        else:
            # With no source to infer, strict auto mode reports direct markers missing.
            effective_mode = "direct"
    else:
        effective_mode = args.mode

    for record in scoped:
        if len(record.direct) > 1:
            failures.append(
                f"slide {record.physical_number}: duplicate direct page numbers; "
                f"found {len(record.direct)}"
            )

    coexistence = has_direct and (has_native or has_inherited_manual)
    if coexistence:
        involved = [
            record.physical_number
            for record in scoped
            if record.direct
            or record.native_sources
            or record.inherited_manual_sources
        ]
        failures.append(
            "direct page numbers and inherited/native page-number sources "
            f"coexist on audited slides: {slide_list(involved)}"
        )

    if effective_mode == "direct":
        if (has_native or has_inherited_manual) and not coexistence:
            sources = [
                source_summary(source)
                for record in scoped
                for source in (
                    record.native_sources + record.inherited_manual_sources
                )
            ]
            failures.append(
                "direct mode found inherited/native page-number sources: "
                + "; ".join(dict.fromkeys(sources))
            )

        if args.numbering != "none":
            for record in scoped:
                if not record.direct:
                    failures.append(
                        f"slide {record.physical_number}: missing direct page number"
                    )

        for record in scoped:
            if len(record.direct) == 1:
                validate_direct_marker(
                    record,
                    record.direct[0],
                    expected.get(record.physical_number),
                    args.expect_name,
                    args.expect_size,
                    failures,
                )

    elif effective_mode == "native":
        if has_direct and not coexistence:
            failures.append("native mode found direct page-number shapes")
        if args.expect_name is not None or args.expect_size is not None:
            failures.append(
                "--expect-name and --expect-size apply only to direct page numbers"
            )

        source_map: dict[tuple[str, str], SourceMarkers] = {}
        manual_map: dict[tuple[str, str], SourceMarkers] = {}
        for record in scoped:
            for source in record.native_sources:
                source_map[(source.level, source.part)] = source
            for source in record.inherited_manual_sources:
                manual_map[(source.level, source.part)] = source

        for source in source_map.values():
            if len(source.markers) > 1:
                failures.append(
                    f"{source.level} part {source.part}: duplicate native "
                    f"page-number shapes; found {len(source.markers)}"
                )
        if manual_map:
            failures.append(
                "native mode found non-native inherited numeric markers: "
                + "; ".join(source_summary(source) for source in manual_map.values())
            )
        if args.numbering != "none":
            for record in scoped:
                if not record.native_sources:
                    failures.append(
                        f"slide {record.physical_number}: missing native "
                        "page-number source"
                    )

    elif args.expect_name is not None or args.expect_size is not None:
        failures.append(
            "--expect-name/--expect-size cannot be checked without direct page numbers"
        )

    relevant_sources: dict[tuple[str, str], SourceMarkers] = {}
    relevant_manual: dict[tuple[str, str], SourceMarkers] = {}
    for record in scoped:
        for source in record.native_sources:
            relevant_sources[(source.level, source.part)] = source
        for source in record.inherited_manual_sources:
            relevant_manual[(source.level, source.part)] = source

    summary: dict[str, object] = {
        "slides": len(records),
        "visible": sum(not record.hidden for record in records),
        "hidden": sum(record.hidden for record in records),
        "audited": len(scoped),
        "requested_mode": args.mode,
        "effective_mode": effective_mode,
        "numbering": args.numbering,
        "direct": direct_count,
        "native": sum(
            len(source.markers) for source in relevant_sources.values()
        ),
        "inherited_manual": sum(
            len(source.markers) for source in relevant_manual.values()
        ),
        "inherited_chains": sum(
            any(source.level != "slide" for source in record.native_sources)
            or bool(record.inherited_manual_sources)
            for record in scoped
        ),
    }
    return failures, summary


def audit_pptx(path: Path, args: argparse.Namespace) -> int:
    try:
        with zipfile.ZipFile(path) as zf:
            failures, summary = audit_open_pptx(zf, args)
    except (OSError, zipfile.BadZipFile, KeyError, ET.ParseError, ValueError) as exc:
        print(path)
        print("  status: FAIL")
        print(f"  - cannot audit PPTX: {exc}")
        return 1

    print(path)
    print(
        f"  slides: {summary['slides']} "
        f"(visible {summary['visible']}, hidden {summary['hidden']}, "
        f"audited {summary['audited']})"
    )
    print(
        f"  mode: {summary['effective_mode']} "
        f"(requested {summary['requested_mode']})"
    )
    print(f"  numbering: {summary['numbering']}")
    print(f"  direct page-number shapes: {summary['direct']}")
    print(f"  native page-number shapes: {summary['native']}")
    print(f"  inherited numeric shapes: {summary['inherited_manual']}")
    print(
        "  inherited slide chains with page markers: "
        f"{summary['inherited_chains']}"
    )
    print(f"  status: {'FAIL' if failures else 'OK'}")
    for failure in failures[:30]:
        print(f"  - {failure}")
    if len(failures) > 30:
        print(f"  - ... {len(failures) - 30} more failure(s)")
    return 1 if failures else 0


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Strictly audit page numbers in PPTX slides, layouts, and masters."
    )
    parser.add_argument("pptx", nargs="+", type=Path)
    parser.add_argument(
        "--mode",
        choices=("auto", "direct", "native"),
        default="auto",
        help=(
            "page-number source strategy; auto selects direct when bottom-right "
            "numeric shapes exist, otherwise native (default: auto)"
        ),
    )
    parser.add_argument(
        "--numbering",
        choices=("physical", "visible", "none"),
        default="physical",
        help=(
            "physical audits and counts hidden slides; visible excludes hidden "
            "slides; none skips presence and sequence checks (default: physical)"
        ),
    )
    parser.add_argument(
        "--expect-name",
        help="optionally require this exact name on each detected direct marker",
    )
    parser.add_argument(
        "--expect-size",
        type=positive_int,
        help=(
            "optionally require this OOXML font size in hundredths of a point "
            "on each direct marker, e.g. 1100 for 11pt"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    # Shape names and paths are echoed in failure lines. Avoid Unicode crashes
    # on Windows pipes whose active code page cannot encode them.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    args = build_parser().parse_args(argv)
    code = 0
    for pptx in args.pptx:
        code |= audit_pptx(pptx, args)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
