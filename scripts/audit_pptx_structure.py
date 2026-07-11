#!/usr/bin/env python3
"""Read-only PPTX structure, edit-scope, and translation audit.

The script opens PPTX packages only in ZIP read mode. It never rewrites a
presentation. Use ``manifest`` to inventory one deck and ``compare`` to enforce
an allowed slide range while guarding shared masters, layouts, and themes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import posixpath
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Iterable, Sequence


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
SHARED_PREFIXES = (
    "ppt/slideMasters/",
    "ppt/slideLayouts/",
    "ppt/theme/",
)
GRAPH_STOP_PREFIXES = SHARED_PREFIXES + (
    "ppt/notesMasters/",
    "ppt/handoutMasters/",
)
FALSE_VALUES = {"0", "false", "off", "no"}
CJK_RE = re.compile(
    r"[\u2e80-\u2fff\u3040-\u30ff\u31f0-\u31ff\u3400-\u4dbf"
    r"\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]"
)
URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)\S+")
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
LATIN_WORD_RE = re.compile(r"[A-Za-z]+(?:['-][A-Za-z]+)*")
ENGLISH_FUNCTION_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "our",
    "should",
    "that",
    "the",
    "this",
    "to",
    "we",
    "will",
    "with",
    "you",
}
TRANSLATION_EXCEPTIONS_HELP = """
Translation exceptions JSON schema (version 1):
  {
    "version": 1,
    "allow_extra": [
      {"id": "p44-overlays", "target_page": 44, "name": "EN_overlay_*"}
    ],
    "allow_missing": [
      {"id": "p20-rebuilt", "source_page": 20, "key": "id:42"}
    ],
    "box_mappings": [
      {"id": "chart-label", "source_page": 20, "source_key": "id:42",
       "target_page": 44, "target_key": "id:109"}
    ]
  }

allow_extra requires target_page; allow_missing requires source_page. Rules use
case-sensitive fnmatch globs in shape, name, and/or key. "shape" matches either
the shape name or box key; name/key constrain their respective field. Explicit
box_mappings use exact keys and run before automatic shape-id/placeholder/bbox
matching. Wildcard rules with fewer than three literal letters/digits are
rejected as too broad. Invalid, ambiguous, unmatched, conflicting, and unused
rules are reported; --strict-translation makes those issues fail the audit.

Slide mapping safety:
With --map-slides auto, a true-order fallback between different stable slide
IDs is provisional and emits translation-order-fallback during translation
checks; --strict-translation fails on it. Use --map-slides order to explicitly
select true-order mapping when comparing independent deck versions.
"""


class AuditError(RuntimeError):
    """Raised for malformed or unsupported PPTX package input."""


def q(prefix: str, tag: str) -> str:
    return f"{{{NS[prefix]}}}{tag}"


def _parse_xml(data: bytes, part: str) -> ET.Element:
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise AuditError(f"invalid XML in {part}: {exc}") from exc


def _rels_part(part: str) -> str:
    folder = posixpath.dirname(part)
    base = posixpath.basename(part)
    return posixpath.join(folder, "_rels", base + ".rels")


def _resolve_target(source_part: str, target: str) -> str:
    target = target.split("#", 1)[0]
    if target.startswith("/"):
        return posixpath.normpath(target.lstrip("/"))
    return posixpath.normpath(posixpath.join(posixpath.dirname(source_part), target))


def _relationships(
    zf: zipfile.ZipFile,
    source_part: str,
    names: set[str],
) -> list[dict[str, str]]:
    rels_part = _rels_part(source_part)
    if rels_part not in names:
        return []
    root = _parse_xml(zf.read(rels_part), rels_part)
    result: list[dict[str, str]] = []
    for rel in root.findall("rel:Relationship", NS):
        target = rel.get("Target", "")
        mode = rel.get("TargetMode", "")
        result.append(
            {
                "id": rel.get("Id", ""),
                "type": rel.get("Type", ""),
                "target": target,
                "target_mode": mode,
                "resolved": ""
                if mode.lower() == "external" or not target
                else _resolve_target(source_part, target),
            }
        )
    return result


def _canonical_tree(element: ET.Element, strip_drawing_text: bool) -> object:
    attrs = []
    for key, value in sorted(element.attrib.items()):
        if strip_drawing_text and element.tag == q("a", "t") and key == XML_SPACE:
            continue
        attrs.append([key, value])

    if strip_drawing_text and element.tag == q("a", "t"):
        text = ""
    else:
        raw_text = element.text or ""
        text = "" if raw_text.isspace() else raw_text

    children = [_canonical_tree(child, strip_drawing_text) for child in element]
    if element.tag == q("rel", "Relationships"):
        children.sort(key=lambda item: json.dumps(item, ensure_ascii=True, separators=(",", ":")))
    return [element.tag, attrs, text, children]


def _fingerprint_payload(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _xml_fingerprint(data: bytes, part: str, *, strip_drawing_text: bool = False) -> str:
    root = _parse_xml(data, part)
    return _fingerprint_payload(_canonical_tree(root, strip_drawing_text))


def _part_fingerprint(zf: zipfile.ZipFile, part: str) -> str:
    data = zf.read(part)
    if part.endswith((".xml", ".rels")):
        return _xml_fingerprint(data, part)
    return hashlib.sha256(data).hexdigest()


def _as_slide_id(value: str) -> int | str:
    try:
        return int(value)
    except ValueError:
        return value


def _shown(value: str | None) -> bool:
    return value is None or value.strip().lower() not in FALSE_VALUES


def _paragraph_text(paragraph: ET.Element) -> str:
    chunks: list[str] = []
    for node in paragraph.iter():
        if node.tag == q("a", "t"):
            chunks.append(node.text or "")
        elif node.tag == q("a", "br"):
            chunks.append("\n")
        elif node.tag == q("a", "tab"):
            chunks.append("\t")
    return "".join(chunks)


def _text_body_text(text_body: ET.Element) -> str:
    return "\n".join(
        _paragraph_text(paragraph) for paragraph in text_body.findall("a:p", NS)
    )


def _shape_bbox(shape: ET.Element) -> dict[str, int] | None:
    transform = shape.find("p:spPr/a:xfrm", NS)
    if transform is None:
        return None
    offset = transform.find("a:off", NS)
    extent = transform.find("a:ext", NS)
    if offset is None or extent is None:
        return None
    try:
        return {
            "x": int(offset.get("x", "0")),
            "y": int(offset.get("y", "0")),
            "cx": int(extent.get("cx", "0")),
            "cy": int(extent.get("cy", "0")),
        }
    except ValueError:
        return None


def _placeholder_maps(layout_root: ET.Element | None) -> tuple[dict[str, str], dict[str, str]]:
    by_index: dict[str, str] = {}
    by_shape_id: dict[str, str] = {}
    if layout_root is None:
        return by_index, by_shape_id
    for shape in layout_root.findall(".//p:sp", NS):
        placeholder = shape.find("p:nvSpPr/p:nvPr/p:ph", NS)
        if placeholder is None:
            continue
        placeholder_type = placeholder.get("type", "body")
        index = placeholder.get("idx")
        if index is not None:
            by_index[index] = placeholder_type
        non_visual = shape.find("p:nvSpPr/p:cNvPr", NS)
        if non_visual is not None and non_visual.get("id"):
            by_shape_id[non_visual.get("id", "")] = placeholder_type
    return by_index, by_shape_id


def _text_boxes(
    slide_root: ET.Element,
    layout_root: ET.Element | None,
) -> list[dict[str, object]]:
    layout_by_index, layout_by_shape = _placeholder_maps(layout_root)
    result: list[dict[str, object]] = []
    used_keys: dict[str, int] = {}
    for shape_index, shape in enumerate(slide_root.findall(".//p:sp", NS), 1):
        text_body = shape.find("p:txBody", NS)
        if text_body is None:
            continue
        non_visual = shape.find("p:nvSpPr/p:cNvPr", NS)
        shape_id = non_visual.get("id", "") if non_visual is not None else ""
        shape_name = non_visual.get("name", "") if non_visual is not None else ""
        placeholder = shape.find("p:nvSpPr/p:nvPr/p:ph", NS)
        placeholder_type = ""
        placeholder_index = ""
        if placeholder is not None:
            placeholder_index = placeholder.get("idx", "")
            placeholder_type = placeholder.get("type", "")
            if not placeholder_type and placeholder_index:
                placeholder_type = layout_by_index.get(placeholder_index, "")
            if not placeholder_type and shape_id:
                placeholder_type = layout_by_shape.get(shape_id, "")

        base_key = f"id:{shape_id}" if shape_id else f"index:{shape_index}"
        used_keys[base_key] = used_keys.get(base_key, 0) + 1
        key = base_key
        if used_keys[base_key] > 1:
            key = f"{base_key}#{used_keys[base_key]}"

        is_title = placeholder_type in {"title", "ctrTitle"}
        if not is_title and shape_name.casefold().startswith("title"):
            is_title = True
        result.append(
            {
                "key": key,
                "shape_id": shape_id,
                "name": shape_name,
                "placeholder_type": placeholder_type,
                "placeholder_index": placeholder_index,
                "is_title": is_title,
                "bbox": _shape_bbox(shape),
                "text": _text_body_text(text_body),
            }
        )
    return result


def _layout_info(
    zf: zipfile.ZipFile,
    slide_part: str,
    names: set[str],
) -> tuple[dict[str, str], ET.Element | None, tuple[str, str] | None]:
    layout_part = ""
    for rel in _relationships(zf, slide_part, names):
        if rel["type"].endswith("/slideLayout"):
            layout_part = rel["resolved"]
            break
    if not layout_part:
        return (
            {"part": "", "name": "", "type": ""},
            None,
            (
                "missing-slide-layout-relationship",
                f"{slide_part} has no slideLayout relationship",
            ),
        )
    if layout_part not in names:
        return (
            {"part": layout_part, "name": "", "type": ""},
            None,
            (
                "missing-relationship-target",
                f"{slide_part} points to missing layout part {layout_part}",
            ),
        )
    root = _parse_xml(zf.read(layout_part), layout_part)
    common = root.find("p:cSld", NS)
    return (
        {
            "part": layout_part,
            "name": common.get("name", "") if common is not None else "",
            "type": root.get("type", ""),
        },
        root,
        None,
    )


def _is_guarded_shared(part: str) -> bool:
    return part.startswith(SHARED_PREFIXES)


def _is_graph_stop(part: str) -> bool:
    return part.startswith(GRAPH_STOP_PREFIXES)


def _local_part_closure(
    zf: zipfile.ZipFile,
    slide_part: str,
    names: set[str],
) -> list[str]:
    todo = [slide_part]
    visited: set[str] = set()
    local_parts: set[str] = set()
    while todo:
        part = todo.pop()
        if part in visited or part not in names:
            continue
        visited.add(part)
        local_parts.add(part)
        rels_part = _rels_part(part)
        if rels_part in names:
            local_parts.add(rels_part)
        for rel in _relationships(zf, part, names):
            target = rel["resolved"]
            if not target or _is_graph_stop(target):
                continue
            if target == "ppt/presentation.xml":
                continue
            if target.startswith("ppt/slides/") and target != slide_part:
                continue
            if target in names and target not in visited:
                todo.append(target)
    return sorted(local_parts)


def _title_from_boxes(boxes: list[dict[str, object]]) -> tuple[str, str]:
    for box in boxes:
        if box["is_title"] and str(box["text"]).strip():
            return str(box["text"]).strip(), "title-placeholder"
    for box in boxes:
        if str(box["text"]).strip():
            return str(box["text"]).strip(), "first-text-box"
    return "", "none"


def _shared_parts(zf: zipfile.ZipFile, names: set[str]) -> dict[str, str]:
    return {
        part: _part_fingerprint(zf, part)
        for part in sorted(names)
        if not part.endswith("/") and _is_guarded_shared(part)
    }


def build_manifest(path: str | Path) -> dict[str, object]:
    """Build a JSON-serializable, true-slide-order manifest for ``path``."""

    pptx = Path(path).expanduser().resolve()
    if not pptx.is_file():
        raise AuditError(f"PPTX not found: {pptx}")
    package_fingerprint = hashlib.sha256(pptx.read_bytes()).hexdigest()
    integrity_warnings: list[dict[str, object]] = []

    def add_integrity_warning(code: str, message: str, **details: object) -> None:
        item: dict[str, object] = {"code": code, "message": message, **details}
        if item not in integrity_warnings:
            integrity_warnings.append(item)

    try:
        with zipfile.ZipFile(pptx, "r") as zf:
            infos = zf.infolist()
            names_list = [info.filename for info in infos]
            names = set(names_list)
            for name, count in sorted(Counter(names_list).items()):
                if count > 1:
                    add_integrity_warning(
                        "duplicate-zip-entry",
                        f"ZIP part {name} occurs {count} times",
                        part=name,
                        count=count,
                    )
            bad_part = zf.testzip()
            if bad_part:
                raise AuditError(f"ZIP integrity failure at {bad_part}")
            required = {"ppt/presentation.xml", "ppt/_rels/presentation.xml.rels"}
            missing = sorted(required - names)
            if missing:
                raise AuditError("missing required PPTX parts: " + ", ".join(missing))

            presentation = _parse_xml(
                zf.read("ppt/presentation.xml"), "ppt/presentation.xml"
            )
            size_element = presentation.find("p:sldSz", NS)
            slide_size = {
                "cx": int(size_element.get("cx", "12192000"))
                if size_element is not None
                else 12192000,
                "cy": int(size_element.get("cy", "6858000"))
                if size_element is not None
                else 6858000,
            }
            presentation_rels = [
                rel
                for rel in _relationships(zf, "ppt/presentation.xml", names)
                if rel["type"].endswith("/slide")
            ]
            rel_id_counts = Counter(rel["id"] for rel in presentation_rels)
            rel_by_id: dict[str, dict[str, str]] = {}
            for rel in presentation_rels:
                if rel_id_counts[rel["id"]] > 1:
                    add_integrity_warning(
                        "duplicate-slide-relationship-id",
                        f"presentation slide relationship id {rel['id']!r} is duplicated",
                        relationship_id=rel["id"],
                        count=rel_id_counts[rel["id"]],
                    )
                rel_by_id.setdefault(rel["id"], rel)
            slide_nodes = presentation.findall("p:sldIdLst/p:sldId", NS)
            slides: list[dict[str, object]] = []
            seen_ids: set[int | str] = set()
            for page, slide_node in enumerate(slide_nodes, 1):
                stable_id = _as_slide_id(slide_node.get("id", ""))
                if stable_id in seen_ids:
                    add_integrity_warning(
                        "duplicate-stable-slide-id",
                        f"stable slide id {stable_id!r} occurs more than once",
                        slide_id=stable_id,
                        page=page,
                    )
                seen_ids.add(stable_id)
                relationship_id = slide_node.get(q("r", "id"), "")
                rel = rel_by_id.get(relationship_id)
                if rel is None or not rel["resolved"]:
                    add_integrity_warning(
                        "missing-slide-relationship",
                        (
                            f"slide {page} id {stable_id!r} has no resolvable "
                            f"relationship {relationship_id!r}"
                        ),
                        page=page,
                        slide_id=stable_id,
                        relationship_id=relationship_id,
                    )
                    empty_parts: dict[str, str] = {}
                    slides.append(
                        {
                            "page": page,
                            "slide_id": stable_id,
                            "relationship_id": relationship_id,
                            "part": "",
                            "hidden": not _shown(slide_node.get("show")),
                            "layout": {"part": "", "name": "", "type": ""},
                            "title": "",
                            "title_source": "none",
                            "text_box_count": 0,
                            "text_boxes": [],
                            "structure_fingerprint": "",
                            "text_fingerprint": _fingerprint_payload([]),
                            "local_fingerprint": _fingerprint_payload(empty_parts),
                            "local_parts": empty_parts,
                            "integrity_incomplete": True,
                        }
                    )
                    continue
                slide_part = rel["resolved"]
                if slide_part not in names:
                    add_integrity_warning(
                        "missing-relationship-target",
                        f"slide {page} id {stable_id!r} points to missing part {slide_part}",
                        page=page,
                        slide_id=stable_id,
                        relationship_id=relationship_id,
                        target=slide_part,
                    )
                    empty_parts = {}
                    slides.append(
                        {
                            "page": page,
                            "slide_id": stable_id,
                            "relationship_id": relationship_id,
                            "part": slide_part,
                            "hidden": not _shown(slide_node.get("show")),
                            "layout": {"part": "", "name": "", "type": ""},
                            "title": "",
                            "title_source": "none",
                            "text_box_count": 0,
                            "text_boxes": [],
                            "structure_fingerprint": "",
                            "text_fingerprint": _fingerprint_payload([]),
                            "local_fingerprint": _fingerprint_payload(empty_parts),
                            "local_parts": empty_parts,
                            "integrity_incomplete": True,
                        }
                    )
                    continue
                slide_data = zf.read(slide_part)
                slide_root = _parse_xml(slide_data, slide_part)
                layout, layout_root, layout_issue = _layout_info(zf, slide_part, names)
                if layout_issue:
                    code, message = layout_issue
                    add_integrity_warning(
                        code,
                        message,
                        page=page,
                        slide_id=stable_id,
                        slide_part=slide_part,
                    )
                boxes = _text_boxes(slide_root, layout_root)
                title, title_source = _title_from_boxes(boxes)
                local_parts = {
                    part: _part_fingerprint(zf, part)
                    for part in _local_part_closure(zf, slide_part, names)
                }
                hidden = not (
                    _shown(slide_node.get("show")) and _shown(slide_root.get("show"))
                )
                slides.append(
                    {
                        "page": page,
                        "slide_id": stable_id,
                        "relationship_id": relationship_id,
                        "part": slide_part,
                        "hidden": hidden,
                        "layout": layout,
                        "title": title,
                        "title_source": title_source,
                        "text_box_count": len(boxes),
                        "text_boxes": boxes,
                        "structure_fingerprint": _xml_fingerprint(
                            slide_data,
                            slide_part,
                            strip_drawing_text=True,
                        ),
                        "text_fingerprint": _fingerprint_payload(
                            [box["text"] for box in boxes]
                        ),
                        "local_fingerprint": _fingerprint_payload(local_parts),
                        "local_parts": local_parts,
                        "integrity_incomplete": False,
                    }
                )
            shared_parts = _shared_parts(zf, names)
    except zipfile.BadZipFile as exc:
        raise AuditError(f"not a valid PPTX ZIP package: {pptx}") from exc

    return {
        "schema_version": 1,
        "kind": "pptx-structure-manifest",
        "path": str(pptx),
        "package_fingerprint": package_fingerprint,
        "slide_size": slide_size,
        "slide_count": len(slides),
        "slide_order": [slide["slide_id"] for slide in slides],
        "slides": slides,
        "shared_parts": shared_parts,
        "integrity_ok": not integrity_warnings,
        "integrity_warnings": integrity_warnings,
        "warnings": [item["message"] for item in integrity_warnings],
    }


def parse_slide_ranges(spec: str) -> set[int]:
    """Parse a one-based range such as ``1-3,5,8``."""

    result: set[int] = set()
    if not spec.strip():
        return result
    for token in spec.split(","):
        token = token.strip()
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", token)
        if not match:
            raise AuditError(f"invalid --allow-slides token: {token!r}")
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if start < 1 or end < start:
            raise AuditError(f"invalid --allow-slides range: {token!r}")
        if end - start > 100000:
            raise AuditError(f"--allow-slides range is too large: {token!r}")
        result.update(range(start, end + 1))
    return result


def _coerce_allowed_slides(value: Iterable[int] | str | None) -> set[int]:
    if value is None:
        return set()
    if isinstance(value, str):
        return parse_slide_ranges(value)
    result = {int(page) for page in value}
    if any(page < 1 for page in result):
        raise AuditError("allowed slide numbers must be positive")
    return result


def _slide_pairs(
    source_slides: list[dict[str, object]],
    target_slides: list[dict[str, object]],
    mapping: str,
) -> tuple[
    list[tuple[dict[str, object], dict[str, object], str]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    if mapping not in {"auto", "id", "order"}:
        raise AuditError(f"unknown slide mapping mode: {mapping}")

    source_counts: dict[object, int] = {}
    target_counts: dict[object, int] = {}
    for slide in source_slides:
        source_counts[slide["slide_id"]] = source_counts.get(slide["slide_id"], 0) + 1
    for slide in target_slides:
        target_counts[slide["slide_id"]] = target_counts.get(slide["slide_id"], 0) + 1

    pairs: list[tuple[dict[str, object], dict[str, object], str]] = []
    used_source: set[int] = set()
    used_target: set[int] = set()
    if mapping in {"auto", "id"}:
        target_by_id = {
            slide["slide_id"]: (index, slide)
            for index, slide in enumerate(target_slides)
            if target_counts[slide["slide_id"]] == 1
        }
        for source_index, source_slide in enumerate(source_slides):
            stable_id = source_slide["slide_id"]
            if source_counts[stable_id] != 1 or stable_id not in target_by_id:
                continue
            target_index, target_slide = target_by_id[stable_id]
            pairs.append((source_slide, target_slide, "slide-id"))
            used_source.add(source_index)
            used_target.add(target_index)

    if mapping in {"auto", "order"}:
        remaining_source = [
            (index, slide)
            for index, slide in enumerate(source_slides)
            if index not in used_source
        ]
        remaining_target = [
            (index, slide)
            for index, slide in enumerate(target_slides)
            if index not in used_target
        ]
        for (source_index, source_slide), (target_index, target_slide) in zip(
            remaining_source, remaining_target
        ):
            pairs.append((source_slide, target_slide, "true-order"))
            used_source.add(source_index)
            used_target.add(target_index)

    pairs.sort(key=lambda item: int(item[0]["page"]))
    unmatched_source = [
        slide for index, slide in enumerate(source_slides) if index not in used_source
    ]
    unmatched_target = [
        slide for index, slide in enumerate(target_slides) if index not in used_target
    ]
    return pairs, unmatched_source, unmatched_target


def _slide_mapping_evidence(
    source_slide: dict[str, object],
    target_slide: dict[str, object],
    method: str,
    policy: str,
) -> dict[str, object]:
    stable_id_match = source_slide["slide_id"] == target_slide["slide_id"]
    provisional = policy == "auto" and method == "true-order" and not stable_id_match
    if method == "slide-id":
        basis = "matching-stable-slide-id"
    elif policy == "order":
        basis = "user-selected-true-order"
    else:
        basis = "automatic-true-order-fallback"
    return {
        "method": method,
        "policy": policy,
        "basis": basis,
        "source_slide_id": source_slide["slide_id"],
        "target_slide_id": target_slide["slide_id"],
        "stable_slide_id_match": stable_id_match,
        "provisional": provisional,
    }


def _part_changes(source: dict[str, str], target: dict[str, str]) -> dict[str, list[str]]:
    source_names = set(source)
    target_names = set(target)
    return {
        "added": sorted(target_names - source_names),
        "removed": sorted(source_names - target_names),
        "modified": sorted(
            name
            for name in source_names & target_names
            if source[name] != target[name]
        ),
    }


def _has_part_changes(changes: dict[str, list[str]]) -> bool:
    return any(changes.values())


def _question_title(title: str) -> bool:
    value = title.rstrip()
    closers = "\"')]}\u2019\u201d\u3009\u300b\u300d\u300f\uff09\uff3d\uff5d"
    while value and value[-1] in closers:
        value = value[:-1].rstrip()
    return value.endswith(("?", "\uFF1F"))


def _excerpt(text: str, limit: int = 80) -> str:
    value = " ".join(text.split())
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _obvious_english_prose(text: str) -> str | None:
    for paragraph in re.split(r"[\r\n]+", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        cleaned = URL_RE.sub(" ", EMAIL_RE.sub(" ", paragraph))
        words = LATIN_WORD_RE.findall(cleaned)
        latin_characters = sum(sum(character.isalpha() for character in word) for word in words)
        if len(words) < 7 or latin_characters < 32:
            continue
        lowercase_words = [word for word in words if any(char.islower() for char in word)]
        if len(lowercase_words) < 5:
            continue
        function_word_count = sum(
            word.casefold() in ENGLISH_FUNCTION_WORDS for word in words
        )
        sentence_punctuation = bool(re.search(r"[.!?](?:[\"')\]]*\s*)$", cleaned))
        if function_word_count < 2 and not (sentence_punctuation and len(words) >= 9):
            continue
        cjk_characters = len(CJK_RE.findall(cleaned))
        if cjk_characters and latin_characters < cjk_characters * 4:
            continue
        return paragraph
    return None


def _placeholder_signature(box: dict[str, object]) -> tuple[str, str] | None:
    placeholder_type = str(box.get("placeholder_type", ""))
    placeholder_index = str(box.get("placeholder_index", ""))
    if not placeholder_type and not placeholder_index:
        return None
    return placeholder_type, placeholder_index


def _normalized_bbox(
    box: dict[str, object], slide_size: dict[str, int]
) -> tuple[float, float, float, float] | None:
    bbox = box.get("bbox")
    if not isinstance(bbox, dict):
        return None
    width = int(slide_size.get("cx", 0))
    height = int(slide_size.get("cy", 0))
    if width <= 0 or height <= 0:
        return None
    try:
        box_width = int(bbox["cx"])
        box_height = int(bbox["cy"])
        if box_width <= 0 or box_height <= 0:
            return None
        return (
            (int(bbox["x"]) + box_width / 2) / width,
            (int(bbox["y"]) + box_height / 2) / height,
            box_width / width,
            box_height / height,
        )
    except (KeyError, TypeError, ValueError):
        return None


def _geometry_cost(
    source_box: dict[str, object],
    target_box: dict[str, object],
    source_size: dict[str, int],
    target_size: dict[str, int],
) -> tuple[float, float] | None:
    source_geometry = _normalized_bbox(source_box, source_size)
    target_geometry = _normalized_bbox(target_box, target_size)
    if source_geometry is None or target_geometry is None:
        return None
    source_x, source_y, source_width, source_height = source_geometry
    target_x, target_y, target_width, target_height = target_geometry
    center_distance = math.hypot(source_x - target_x, source_y - target_y)
    width_ratio = min(source_width, target_width) / max(source_width, target_width)
    height_ratio = min(source_height, target_height) / max(source_height, target_height)
    if center_distance > 0.04 or width_ratio < 0.55 or height_ratio < 0.50:
        return None
    size_delta = (1 - width_ratio) + (1 - height_ratio)
    return center_distance + size_delta * 0.02, center_distance


def _map_text_boxes(
    source_boxes: list[dict[str, object]],
    target_boxes: list[dict[str, object]],
    source_size: dict[str, int],
    target_size: dict[str, int],
) -> tuple[
    list[tuple[dict[str, object], dict[str, object], dict[str, object]]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    matches: list[
        tuple[dict[str, object], dict[str, object], dict[str, object]]
    ] = []
    used_source: set[str] = set()
    used_target: set[str] = set()

    def add_match(
        source_box: dict[str, object],
        target_box: dict[str, object],
        method: str,
        **details: object,
    ) -> None:
        source_key = str(source_box["key"])
        target_key = str(target_box["key"])
        used_source.add(source_key)
        used_target.add(target_key)
        record: dict[str, object] = {
            "source_text_box": source_key,
            "target_text_box": target_key,
            "source_shape_id": source_box.get("shape_id", ""),
            "target_shape_id": target_box.get("shape_id", ""),
            "mapping": method,
            **details,
        }
        matches.append((source_box, target_box, record))

    source_by_id: dict[str, list[dict[str, object]]] = {}
    target_by_id: dict[str, list[dict[str, object]]] = {}
    for box in source_boxes:
        if box.get("shape_id"):
            source_by_id.setdefault(str(box["shape_id"]), []).append(box)
    for box in target_boxes:
        if box.get("shape_id"):
            target_by_id.setdefault(str(box["shape_id"]), []).append(box)
    for shape_id in sorted(set(source_by_id) & set(target_by_id)):
        if len(source_by_id[shape_id]) == len(target_by_id[shape_id]) == 1:
            add_match(source_by_id[shape_id][0], target_by_id[shape_id][0], "shape-id")

    remaining_source = [box for box in source_boxes if str(box["key"]) not in used_source]
    remaining_target = [box for box in target_boxes if str(box["key"]) not in used_target]
    source_by_placeholder: dict[tuple[str, str], list[dict[str, object]]] = {}
    target_by_placeholder: dict[tuple[str, str], list[dict[str, object]]] = {}
    for box in remaining_source:
        signature = _placeholder_signature(box)
        if signature:
            source_by_placeholder.setdefault(signature, []).append(box)
    for box in remaining_target:
        signature = _placeholder_signature(box)
        if signature:
            target_by_placeholder.setdefault(signature, []).append(box)
    for signature in sorted(set(source_by_placeholder) & set(target_by_placeholder)):
        if (
            len(source_by_placeholder[signature]) == 1
            and len(target_by_placeholder[signature]) == 1
        ):
            add_match(
                source_by_placeholder[signature][0],
                target_by_placeholder[signature][0],
                "placeholder",
                placeholder_type=signature[0],
                placeholder_index=signature[1],
            )

    remaining_source = [box for box in source_boxes if str(box["key"]) not in used_source]
    remaining_target = [box for box in target_boxes if str(box["key"]) not in used_target]
    candidates: dict[tuple[str, str], tuple[float, float]] = {}
    for source_box in remaining_source:
        for target_box in remaining_target:
            cost = _geometry_cost(source_box, target_box, source_size, target_size)
            if cost is not None:
                candidates[(str(source_box["key"]), str(target_box["key"]))] = cost

    source_rankings: dict[str, list[tuple[float, str, float]]] = {}
    target_rankings: dict[str, list[tuple[float, str, float]]] = {}
    for (source_key, target_key), (cost, distance) in candidates.items():
        source_rankings.setdefault(source_key, []).append((cost, target_key, distance))
        target_rankings.setdefault(target_key, []).append((cost, source_key, distance))
    for ranking in list(source_rankings.values()) + list(target_rankings.values()):
        ranking.sort()

    source_lookup = {str(box["key"]): box for box in remaining_source}
    target_lookup = {str(box["key"]): box for box in remaining_target}

    def unambiguous(ranking: list[tuple[float, str, float]]) -> bool:
        return len(ranking) == 1 or ranking[1][0] - ranking[0][0] >= 0.005

    for source_key in sorted(source_rankings):
        source_ranking = source_rankings[source_key]
        if not unambiguous(source_ranking):
            continue
        cost, target_key, center_distance = source_ranking[0]
        target_ranking = target_rankings[target_key]
        if not unambiguous(target_ranking) or target_ranking[0][1] != source_key:
            continue
        if source_key in used_source or target_key in used_target:
            continue
        add_match(
            source_lookup[source_key],
            target_lookup[target_key],
            "geometry",
            geometry_cost=round(cost, 6),
            center_distance=round(center_distance, 6),
        )

    source_order = {str(box["key"]): index for index, box in enumerate(source_boxes)}
    matches.sort(key=lambda item: source_order[str(item[0]["key"])])
    unmatched_source = [box for box in source_boxes if str(box["key"]) not in used_source]
    unmatched_target = [box for box in target_boxes if str(box["key"]) not in used_target]
    return matches, unmatched_source, unmatched_target


def _exception_issue(
    code: str,
    message: str,
    *,
    rule_id: str | None = None,
    rule_type: str | None = None,
    **details: object,
) -> dict[str, object]:
    issue: dict[str, object] = {
        "code": code,
        "severity": "warning",
        "message": message,
        **details,
    }
    if rule_id is not None:
        issue["rule_id"] = rule_id
    if rule_type is not None:
        issue["rule_type"] = rule_type
    return issue


def _valid_exception_page(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _glob_rule_too_broad(patterns: dict[str, str]) -> bool:
    combined = " ".join(patterns.values())
    if not any(character in combined for character in "*?["):
        return False
    without_classes = re.sub(r"\[[^\]]*\]", "", combined)
    literal_alphanumeric = re.sub(r"[^A-Za-z0-9]", "", without_classes)
    return len(literal_alphanumeric) < 3


def _load_translation_exceptions(
    value: str | Path | dict[str, object] | None,
) -> dict[str, object]:
    config: dict[str, object] = {
        "source": None,
        "allow_extra": [],
        "allow_missing": [],
        "box_mappings": [],
        "issues": [],
    }
    if value is None:
        return config

    if isinstance(value, dict):
        raw = value
        config["source"] = "inline"
    else:
        path = Path(value).expanduser().resolve()
        config["source"] = str(path)
        try:
            raw_value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AuditError(f"invalid translation exceptions JSON in {path}: {exc}") from exc
        if not isinstance(raw_value, dict):
            config["issues"].append(
                _exception_issue(
                    "translation-exception-schema",
                    "translation exceptions root must be a JSON object",
                )
            )
            return config
        raw = raw_value

    allowed_top_level = {"version", "allow_extra", "allow_missing", "box_mappings"}
    unknown_top_level = sorted(set(raw) - allowed_top_level)
    if unknown_top_level:
        config["issues"].append(
            _exception_issue(
                "translation-exception-schema",
                "unknown translation exceptions keys: " + ", ".join(unknown_top_level),
            )
        )
    if "version" in raw and raw["version"] != 1:
        config["issues"].append(
            _exception_issue(
                "translation-exception-schema",
                "translation exceptions version must be 1",
            )
        )

    seen_ids: set[str] = set()

    def normalize_allow_rules(rule_type: str, page_field: str) -> None:
        raw_rules = raw.get(rule_type, [])
        if not isinstance(raw_rules, list):
            config["issues"].append(
                _exception_issue(
                    "translation-exception-schema",
                    f"{rule_type} must be an array",
                    rule_type=rule_type,
                )
            )
            return
        destination: list[dict[str, object]] = config[rule_type]
        allowed_fields = {"id", page_field, "shape", "name", "key"}
        for index, raw_rule in enumerate(raw_rules):
            token = f"{rule_type}[{index}]"
            if not isinstance(raw_rule, dict):
                config["issues"].append(
                    _exception_issue(
                        "translation-exception-schema",
                        f"{token} must be an object",
                        rule_id=token,
                        rule_type=rule_type,
                    )
                )
                continue
            rule_id = str(raw_rule.get("id") or token)
            problems: list[str] = []
            unknown_fields = sorted(set(raw_rule) - allowed_fields)
            if unknown_fields:
                problems.append("unknown fields: " + ", ".join(unknown_fields))
            page = raw_rule.get(page_field)
            if not _valid_exception_page(page):
                problems.append(f"{page_field} must be a positive integer")
            patterns: dict[str, str] = {}
            for field in ("shape", "name", "key"):
                if field not in raw_rule:
                    continue
                pattern = raw_rule[field]
                if not isinstance(pattern, str) or not pattern:
                    problems.append(f"{field} must be a non-empty fnmatch glob")
                else:
                    patterns[field] = pattern
            if not patterns:
                problems.append("one of shape, name, or key is required")
            if rule_id in seen_ids:
                problems.append(f"duplicate rule id {rule_id!r}")
            if problems:
                config["issues"].append(
                    _exception_issue(
                        "translation-exception-schema",
                        f"{token}: " + "; ".join(problems),
                        rule_id=rule_id,
                        rule_type=rule_type,
                    )
                )
                continue
            seen_ids.add(rule_id)
            if _glob_rule_too_broad(patterns):
                config["issues"].append(
                    _exception_issue(
                        "translation-exception-too-broad",
                        (
                            f"{rule_id}: wildcard rule needs at least three literal "
                            "letters or digits"
                        ),
                        rule_id=rule_id,
                        rule_type=rule_type,
                        page=page,
                        patterns=patterns,
                    )
                )
                continue
            destination.append(
                {
                    "_token": token,
                    "id": rule_id,
                    page_field: page,
                    "patterns": patterns,
                }
            )

    normalize_allow_rules("allow_extra", "target_page")
    normalize_allow_rules("allow_missing", "source_page")

    raw_mappings = raw.get("box_mappings", [])
    if not isinstance(raw_mappings, list):
        config["issues"].append(
            _exception_issue(
                "translation-exception-schema",
                "box_mappings must be an array",
                rule_type="box_mappings",
            )
        )
    else:
        allowed_mapping_fields = {
            "id",
            "source_page",
            "source_key",
            "target_page",
            "target_key",
        }
        destination_mappings: list[dict[str, object]] = config["box_mappings"]
        for index, raw_rule in enumerate(raw_mappings):
            token = f"box_mappings[{index}]"
            if not isinstance(raw_rule, dict):
                config["issues"].append(
                    _exception_issue(
                        "translation-exception-schema",
                        f"{token} must be an object",
                        rule_id=token,
                        rule_type="box_mappings",
                    )
                )
                continue
            rule_id = str(raw_rule.get("id") or token)
            problems = []
            unknown_fields = sorted(set(raw_rule) - allowed_mapping_fields)
            if unknown_fields:
                problems.append("unknown fields: " + ", ".join(unknown_fields))
            for field in ("source_page", "target_page"):
                if not _valid_exception_page(raw_rule.get(field)):
                    problems.append(f"{field} must be a positive integer")
            for field in ("source_key", "target_key"):
                key = raw_rule.get(field)
                if not isinstance(key, str) or not key:
                    problems.append(f"{field} must be a non-empty exact box key")
                elif any(character in key for character in "*?["):
                    problems.append(f"{field} must be exact, not a glob")
            if rule_id in seen_ids:
                problems.append(f"duplicate rule id {rule_id!r}")
            if problems:
                config["issues"].append(
                    _exception_issue(
                        "translation-exception-schema",
                        f"{token}: " + "; ".join(problems),
                        rule_id=rule_id,
                        rule_type="box_mappings",
                    )
                )
                continue
            seen_ids.add(rule_id)
            destination_mappings.append(
                {
                    "_token": token,
                    "id": rule_id,
                    "source_page": raw_rule["source_page"],
                    "source_key": raw_rule["source_key"],
                    "target_page": raw_rule["target_page"],
                    "target_key": raw_rule["target_key"],
                }
            )
    return config


def _allow_rule_matches_box(
    rule: dict[str, object],
    box: dict[str, object],
) -> bool:
    patterns: dict[str, str] = rule["patterns"]
    name = str(box.get("name", ""))
    key = str(box.get("key", ""))
    if "shape" in patterns and not (
        fnmatchcase(name, patterns["shape"]) or fnmatchcase(key, patterns["shape"])
    ):
        return False
    if "name" in patterns and not fnmatchcase(name, patterns["name"]):
        return False
    if "key" in patterns and not fnmatchcase(key, patterns["key"]):
        return False
    return True


def _translation_warnings(
    pairs: list[tuple[dict[str, object], dict[str, object], str]],
    unmatched_source: list[dict[str, object]],
    unmatched_target: list[dict[str, object]],
    target_slides: list[dict[str, object]],
    source_size: dict[str, int],
    target_size: dict[str, int],
    mapping_policy: str,
    target_language: str | None,
    exceptions: dict[str, object],
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    warnings: list[dict[str, object]] = []
    box_mappings: list[dict[str, object]] = []
    exceptions_applied: list[dict[str, object]] = []
    exception_issues: list[dict[str, object]] = list(exceptions["issues"])
    used_rule_tokens: set[str] = set()
    matched_rule_tokens: set[str] = set()

    pair_lookup = {
        (int(source_slide["page"]), int(target_slide["page"])): (
            source_slide,
            target_slide,
            slide_mapping,
        )
        for source_slide, target_slide, slide_mapping in pairs
    }
    explicit_by_pair: dict[
        tuple[int, int],
        list[tuple[dict[str, object], dict[str, object], dict[str, object]]],
    ] = {}
    explicitly_used_source: set[tuple[int, str]] = set()
    explicitly_used_target: set[tuple[int, str]] = set()
    for rule in exceptions["box_mappings"]:
        source_page = int(rule["source_page"])
        target_page = int(rule["target_page"])
        pair_key = (source_page, target_page)
        rule_id = str(rule["id"])
        token = str(rule["_token"])
        pair = pair_lookup.get(pair_key)
        if pair is None:
            exception_issues.append(
                _exception_issue(
                    "translation-exception-mapping-no-match",
                    (
                        f"{rule_id}: source page {source_page} is not mapped to "
                        f"target page {target_page}"
                    ),
                    rule_id=rule_id,
                    rule_type="box_mappings",
                    source_page=source_page,
                    target_page=target_page,
                )
            )
            continue
        source_slide, target_slide, _ = pair
        source_boxes = {
            str(box["key"]): box for box in source_slide["text_boxes"]
        }
        target_boxes = {
            str(box["key"]): box for box in target_slide["text_boxes"]
        }
        source_key = str(rule["source_key"])
        target_key = str(rule["target_key"])
        source_box = source_boxes.get(source_key)
        target_box = target_boxes.get(target_key)
        if source_box is None or target_box is None:
            missing_endpoints = []
            if source_box is None:
                missing_endpoints.append(f"source {source_page}/{source_key}")
            if target_box is None:
                missing_endpoints.append(f"target {target_page}/{target_key}")
            exception_issues.append(
                _exception_issue(
                    "translation-exception-mapping-no-match",
                    f"{rule_id}: box mapping endpoint not found: " + ", ".join(missing_endpoints),
                    rule_id=rule_id,
                    rule_type="box_mappings",
                    source_page=source_page,
                    target_page=target_page,
                    source_key=source_key,
                    target_key=target_key,
                )
            )
            continue
        source_endpoint = (source_page, source_key)
        target_endpoint = (target_page, target_key)
        if (
            source_endpoint in explicitly_used_source
            or target_endpoint in explicitly_used_target
        ):
            exception_issues.append(
                _exception_issue(
                    "translation-exception-mapping-conflict",
                    f"{rule_id}: source or target box is already explicitly mapped",
                    rule_id=rule_id,
                    rule_type="box_mappings",
                    source_page=source_page,
                    target_page=target_page,
                    source_key=source_key,
                    target_key=target_key,
                )
            )
            continue
        explicitly_used_source.add(source_endpoint)
        explicitly_used_target.add(target_endpoint)
        used_rule_tokens.add(token)
        mapping_record = {
            "source_text_box": source_key,
            "target_text_box": target_key,
            "source_shape_id": source_box.get("shape_id", ""),
            "target_shape_id": target_box.get("shape_id", ""),
            "mapping": "exception-explicit",
            "exception_rule_id": rule_id,
        }
        explicit_by_pair.setdefault(pair_key, []).append(
            (source_box, target_box, mapping_record)
        )
        exceptions_applied.append(
            {
                "kind": "box_mapping",
                "rule_id": rule_id,
                "source_page": source_page,
                "source_key": source_key,
                "target_page": target_page,
                "target_key": target_key,
            }
        )

    for source_slide in unmatched_source:
        warnings.append(
            {
                "code": "translation-slide-missing",
                "severity": "warning",
                "source_page": source_slide["page"],
                "slide_id": source_slide["slide_id"],
                "message": f"source slide {source_slide['page']} has no target mapping",
            }
        )
    for target_slide in unmatched_target:
        warnings.append(
            {
                "code": "translation-slide-extra",
                "severity": "warning",
                "target_page": target_slide["page"],
                "slide_id": target_slide["slide_id"],
                "message": f"target slide {target_slide['page']} has no source mapping",
            }
        )

    for source_slide, target_slide, slide_mapping in pairs:
        evidence = _slide_mapping_evidence(
            source_slide,
            target_slide,
            slide_mapping,
            mapping_policy,
        )
        if evidence["provisional"]:
            warnings.append(
                {
                    "code": "translation-order-fallback",
                    "severity": "warning",
                    "source_page": source_slide["page"],
                    "target_page": target_slide["page"],
                    "source_slide_id": source_slide["slide_id"],
                    "target_slide_id": target_slide["slide_id"],
                    "mapping": slide_mapping,
                    "evidence": evidence,
                    "message": (
                        f"auto mapping provisionally paired source page "
                        f"{source_slide['page']} (id {source_slide['slide_id']}) with "
                        f"target page {target_slide['page']} (id {target_slide['slide_id']}) "
                        "by true order"
                    ),
                }
            )

    for source_slide, target_slide, slide_mapping in pairs:
        source_page = int(source_slide["page"])
        target_page = int(target_slide["page"])
        explicit_matches = explicit_by_pair.get((source_page, target_page), [])
        explicit_source_keys = {str(item[0]["key"]) for item in explicit_matches}
        explicit_target_keys = {str(item[1]["key"]) for item in explicit_matches}
        automatic_matches, missing_boxes, extra_boxes = _map_text_boxes(
            [
                box
                for box in source_slide["text_boxes"]
                if str(box["key"]) not in explicit_source_keys
            ],
            [
                box
                for box in target_slide["text_boxes"]
                if str(box["key"]) not in explicit_target_keys
            ],
            source_size,
            target_size,
        )
        for _, _, record in explicit_matches + automatic_matches:
            box_mappings.append(
                {
                    "source_page": source_page,
                    "target_page": target_page,
                    "slide_id": source_slide["slide_id"],
                    "slide_mapping": slide_mapping,
                    **record,
                }
            )
        for box in missing_boxes:
            key = str(box["key"])
            matching_rules = [
                rule
                for rule in exceptions["allow_missing"]
                if int(rule["source_page"]) == source_page
                and _allow_rule_matches_box(rule, box)
            ]
            matched_rule_tokens.update(str(rule["_token"]) for rule in matching_rules)
            if len(matching_rules) == 1:
                rule = matching_rules[0]
                used_rule_tokens.add(str(rule["_token"]))
                exceptions_applied.append(
                    {
                        "kind": "allow_missing",
                        "rule_id": rule["id"],
                        "source_page": source_page,
                        "target_page": target_page,
                        "shape_key": key,
                        "shape_name": box.get("name", ""),
                        "patterns": rule["patterns"],
                    }
                )
                continue
            if len(matching_rules) > 1:
                exception_issues.append(
                    _exception_issue(
                        "translation-exception-ambiguous",
                        (
                            f"source {source_page}/{key} matches multiple allow_missing "
                            "rules"
                        ),
                        rule_type="allow_missing",
                        source_page=source_page,
                        target_page=target_page,
                        text_box=key,
                        rule_ids=[rule["id"] for rule in matching_rules],
                    )
                )
            warnings.append(
                {
                    "code": "translation-text-box-missing",
                    "severity": "warning",
                    "source_page": source_slide["page"],
                    "target_page": target_slide["page"],
                    "slide_id": source_slide["slide_id"],
                    "slide_mapping": slide_mapping,
                    "mapping": "unmatched-after-shape-id-placeholder-geometry",
                    "text_box": key,
                    "shape_key": key,
                    "shape_name": box.get("name", ""),
                    "message": (
                        f"target slide {target_slide['page']} is missing text box "
                        f"{key} ({box['name']!r})"
                    ),
                }
            )
        for box in extra_boxes:
            key = str(box["key"])
            matching_rules = [
                rule
                for rule in exceptions["allow_extra"]
                if int(rule["target_page"]) == target_page
                and _allow_rule_matches_box(rule, box)
            ]
            matched_rule_tokens.update(str(rule["_token"]) for rule in matching_rules)
            if len(matching_rules) == 1:
                rule = matching_rules[0]
                used_rule_tokens.add(str(rule["_token"]))
                exceptions_applied.append(
                    {
                        "kind": "allow_extra",
                        "rule_id": rule["id"],
                        "source_page": source_page,
                        "target_page": target_page,
                        "shape_key": key,
                        "shape_name": box.get("name", ""),
                        "patterns": rule["patterns"],
                    }
                )
                continue
            if len(matching_rules) > 1:
                exception_issues.append(
                    _exception_issue(
                        "translation-exception-ambiguous",
                        (
                            f"target {target_page}/{key} matches multiple allow_extra rules"
                        ),
                        rule_type="allow_extra",
                        source_page=source_page,
                        target_page=target_page,
                        text_box=key,
                        rule_ids=[rule["id"] for rule in matching_rules],
                    )
                )
            warnings.append(
                {
                    "code": "translation-text-box-extra",
                    "severity": "warning",
                    "source_page": source_slide["page"],
                    "target_page": target_slide["page"],
                    "slide_id": source_slide["slide_id"],
                    "slide_mapping": slide_mapping,
                    "mapping": "unmatched-after-shape-id-placeholder-geometry",
                    "text_box": key,
                    "shape_key": key,
                    "shape_name": box.get("name", ""),
                    "message": (
                        f"target slide {target_slide['page']} has extra text box "
                        f"{key} ({box['name']!r})"
                    ),
                }
            )
        source_question = _question_title(str(source_slide["title"]))
        target_question = _question_title(str(target_slide["title"]))
        if source_question != target_question:
            warnings.append(
                {
                    "code": "translation-title-question-mismatch",
                    "severity": "warning",
                    "source_page": source_slide["page"],
                    "target_page": target_slide["page"],
                    "slide_id": source_slide["slide_id"],
                    "mapping": slide_mapping,
                    "mapping_scope": "slide",
                    "message": (
                        f"title question-mark logic differs on source slide "
                        f"{source_slide['page']} and target slide {target_slide['page']}"
                    ),
                }
            )

    if target_language == "en":
        for target_slide in target_slides:
            for box in target_slide["text_boxes"]:
                text = str(box["text"])
                if not CJK_RE.search(text):
                    continue
                warnings.append(
                    {
                        "code": "translation-cjk-in-english",
                        "severity": "warning",
                        "target_page": target_slide["page"],
                        "slide_id": target_slide["slide_id"],
                        "text_box": box["key"],
                        "mapping": "target-language-scan",
                        "target_language": target_language,
                        "excerpt": _excerpt(text),
                        "message": (
                            f"target English slide {target_slide['page']} retains CJK text "
                            f"in {box['key']}: {_excerpt(text)!r}"
                        ),
                    }
                )
    elif target_language == "zh":
        for target_slide in target_slides:
            for box in target_slide["text_boxes"]:
                prose = _obvious_english_prose(str(box["text"]))
                if prose is None:
                    continue
                warnings.append(
                    {
                        "code": "translation-english-prose-in-chinese",
                        "severity": "warning",
                        "target_page": target_slide["page"],
                        "slide_id": target_slide["slide_id"],
                        "text_box": box["key"],
                        "mapping": "target-language-scan",
                        "target_language": target_language,
                        "excerpt": _excerpt(prose),
                        "message": (
                            f"target Chinese slide {target_slide['page']} retains obvious "
                            f"English prose in {box['key']}: {_excerpt(prose)!r}"
                        ),
                    }
                )
    for rule_type in ("allow_missing", "allow_extra"):
        for rule in exceptions[rule_type]:
            token = str(rule["_token"])
            if token in used_rule_tokens or token in matched_rule_tokens:
                continue
            page_field = "source_page" if rule_type == "allow_missing" else "target_page"
            exception_issues.append(
                _exception_issue(
                    "translation-exception-unused",
                    f"{rule['id']}: rule matched no pending {rule_type} box",
                    rule_id=str(rule["id"]),
                    rule_type=rule_type,
                    page=rule[page_field],
                    patterns=rule["patterns"],
                )
            )
    return warnings, box_mappings, exceptions_applied, exception_issues


def compare_pptx(
    source: str | Path,
    target: str | Path,
    *,
    allow_slides: Iterable[int] | str | None = None,
    allow_shared: bool = False,
    translation_check: bool = False,
    strict_translation: bool = False,
    target_language: str | None = None,
    translation_exceptions: str | Path | dict[str, object] | None = None,
    mapping: str = "auto",
) -> dict[str, object]:
    """Compare two PPTX packages and return an authorization-aware report."""

    if target_language not in {None, "en", "zh"}:
        raise AuditError("target_language must be 'en', 'zh', or None")
    exception_config = _load_translation_exceptions(translation_exceptions)
    source_manifest = build_manifest(source)
    target_manifest = build_manifest(target)
    allowed = _coerce_allowed_slides(allow_slides)
    source_slides = source_manifest["slides"]
    target_slides = target_manifest["slides"]
    pairs, unmatched_source, unmatched_target = _slide_pairs(
        source_slides, target_slides, mapping
    )

    differences: list[dict[str, object]] = []
    violations: list[dict[str, object]] = []

    def add_difference(
        code: str,
        message: str,
        *,
        authorized: bool,
        scope: str,
        details: dict[str, object] | None = None,
    ) -> None:
        item: dict[str, object] = {
            "code": code,
            "scope": scope,
            "authorized": authorized,
            "message": message,
        }
        if details:
            item.update(details)
        differences.append(item)
        if not authorized:
            violations.append(item.copy())

    for side, manifest in (("source", source_manifest), ("target", target_manifest)):
        for warning in manifest["integrity_warnings"]:
            add_difference(
                "package-integrity-warning",
                f"{side} package: {warning['message']}",
                authorized=False,
                scope="package-integrity",
                details={
                    "side": side,
                    "integrity_code": warning["code"],
                    "integrity_warning": warning,
                },
            )

    if source_manifest["slide_count"] != target_manifest["slide_count"]:
        affected = sorted(
            {int(slide["page"]) for slide in unmatched_source + unmatched_target}
        )
        add_difference(
            "slide-count-changed",
            (
                f"slide count changed from {source_manifest['slide_count']} "
                f"to {target_manifest['slide_count']}"
            ),
            authorized=bool(affected) and set(affected) <= allowed,
            scope="presentation",
            details={"affected_pages": affected},
        )

    source_ids = [slide["slide_id"] for slide in source_slides]
    target_ids = [slide["slide_id"] for slide in target_slides]
    common_ids = set(source_ids) & set(target_ids)
    source_common = [slide_id for slide_id in source_ids if slide_id in common_ids]
    target_common = [slide_id for slide_id in target_ids if slide_id in common_ids]
    if source_common != target_common:
        source_page_by_id = {slide["slide_id"]: int(slide["page"]) for slide in source_slides}
        target_page_by_id = {slide["slide_id"]: int(slide["page"]) for slide in target_slides}
        affected = sorted(
            {
                page
                for slide_id in common_ids
                for page in (source_page_by_id[slide_id], target_page_by_id[slide_id])
                if source_page_by_id[slide_id] != target_page_by_id[slide_id]
            }
        )
        add_difference(
            "slide-order-changed",
            "stable slide-id order changed",
            authorized=bool(affected) and set(affected) <= allowed,
            scope="presentation",
            details={
                "affected_pages": affected,
                "source_order": source_ids,
                "target_order": target_ids,
            },
        )

    for slide in unmatched_source:
        page = int(slide["page"])
        add_difference(
            "slide-removed",
            f"source slide {page} (id {slide['slide_id']}) has no target slide",
            authorized=page in allowed,
            scope="slide",
            details={"source_page": page, "slide_id": slide["slide_id"]},
        )
    for slide in unmatched_target:
        page = int(slide["page"])
        add_difference(
            "slide-added",
            f"target slide {page} (id {slide['slide_id']}) has no source slide",
            authorized=page in allowed,
            scope="slide",
            details={"target_page": page, "slide_id": slide["slide_id"]},
        )

    slide_mappings: list[dict[str, object]] = []
    for source_slide, target_slide, map_method in pairs:
        source_page = int(source_slide["page"])
        target_page = int(target_slide["page"])
        slide_id = source_slide["slide_id"]
        authorized = source_page in allowed
        mapping_evidence = _slide_mapping_evidence(
            source_slide,
            target_slide,
            map_method,
            mapping,
        )
        slide_mappings.append(
            {
                "source_page": source_page,
                "target_page": target_page,
                "slide_id": slide_id,
                "target_slide_id": target_slide["slide_id"],
                "mapping": map_method,
                "evidence": mapping_evidence,
            }
        )
        common_details = {
            "source_page": source_page,
            "target_page": target_page,
            "slide_id": slide_id,
            "mapping": map_method,
            "mapping_evidence": mapping_evidence,
        }
        if source_slide["slide_id"] != target_slide["slide_id"]:
            add_difference(
                "slide-id-changed",
                (
                    f"source slide {source_page} id {source_slide['slide_id']} maps by "
                    f"order to target id {target_slide['slide_id']}"
                ),
                authorized=authorized,
                scope="slide",
                details={
                    **common_details,
                    "target_slide_id": target_slide["slide_id"],
                },
            )
        if source_slide["hidden"] != target_slide["hidden"]:
            add_difference(
                "slide-hidden-changed",
                (
                    f"slide {source_page} hidden state changed from "
                    f"{source_slide['hidden']} to {target_slide['hidden']}"
                ),
                authorized=authorized,
                scope="slide",
                details=common_details,
            )
        if source_slide["layout"]["part"] != target_slide["layout"]["part"]:
            add_difference(
                "slide-layout-changed",
                (
                    f"slide {source_page} layout changed from "
                    f"{source_slide['layout']['part']!r} to "
                    f"{target_slide['layout']['part']!r}"
                ),
                authorized=authorized,
                scope="slide",
                details=common_details,
            )
        if source_slide["text_box_count"] != target_slide["text_box_count"]:
            add_difference(
                "slide-text-box-count-changed",
                (
                    f"slide {source_page} text-box count changed from "
                    f"{source_slide['text_box_count']} to {target_slide['text_box_count']}"
                ),
                authorized=authorized,
                scope="slide",
                details=common_details,
            )
        if source_slide["structure_fingerprint"] != target_slide["structure_fingerprint"]:
            add_difference(
                "slide-structure-changed",
                f"slide {source_page} structure fingerprint changed",
                authorized=authorized,
                scope="slide",
                details=common_details,
            )
        if source_slide["text_fingerprint"] != target_slide["text_fingerprint"]:
            add_difference(
                "slide-text-changed",
                f"slide {source_page} text fingerprint changed",
                authorized=authorized,
                scope="slide",
                details=common_details,
            )
        local_changes = _part_changes(
            source_slide["local_parts"], target_slide["local_parts"]
        )
        if _has_part_changes(local_changes):
            add_difference(
                "slide-local-parts-changed",
                f"slide {source_page} has changed slide-local OOXML parts",
                authorized=authorized,
                scope="slide-local",
                details={**common_details, "part_changes": local_changes},
            )

    shared_changes = _part_changes(
        source_manifest["shared_parts"], target_manifest["shared_parts"]
    )
    for change_kind in ("added", "removed", "modified"):
        for part in shared_changes[change_kind]:
            add_difference(
                "shared-part-changed",
                f"shared {part} was {change_kind}",
                authorized=allow_shared,
                scope="shared",
                details={"part": part, "change": change_kind},
            )

    run_translation = (
        translation_check
        or strict_translation
        or target_language is not None
        or exception_config["source"] is not None
    )
    if run_translation:
        (
            translation_warnings,
            translation_box_mappings,
            translation_exceptions_applied,
            translation_exception_issues,
        ) = _translation_warnings(
            pairs,
            unmatched_source,
            unmatched_target,
            target_slides,
            source_manifest["slide_size"],
            target_manifest["slide_size"],
            mapping,
            target_language,
            exception_config,
        )
    else:
        translation_warnings = []
        translation_box_mappings = []
        translation_exceptions_applied = []
        translation_exception_issues = []
    translation_findings = translation_warnings + translation_exception_issues
    if not run_translation:
        translation_status = "not-run"
    elif translation_findings and strict_translation:
        translation_status = "fail"
        for finding in translation_findings:
            strict_item = finding.copy()
            strict_item["strict_failure"] = True
            violations.append(strict_item)
    elif translation_findings:
        translation_status = "warning"
    else:
        translation_status = "pass"

    ok = not violations
    return {
        "schema_version": 1,
        "kind": "pptx-structure-comparison",
        "source": {
            "path": source_manifest["path"],
            "slide_count": source_manifest["slide_count"],
            "package_fingerprint": source_manifest["package_fingerprint"],
            "integrity_ok": source_manifest["integrity_ok"],
            "integrity_warnings": source_manifest["integrity_warnings"],
        },
        "target": {
            "path": target_manifest["path"],
            "slide_count": target_manifest["slide_count"],
            "package_fingerprint": target_manifest["package_fingerprint"],
            "integrity_ok": target_manifest["integrity_ok"],
            "integrity_warnings": target_manifest["integrity_warnings"],
        },
        "policy": {
            "allow_slides": sorted(allowed),
            "allow_shared": allow_shared,
            "mapping": mapping,
            "translation_check": run_translation,
            "strict_translation": strict_translation,
            "target_language": target_language,
            "translation_exceptions": exception_config["source"],
            "translation_exception_rule_counts": {
                "allow_extra": len(exception_config["allow_extra"]),
                "allow_missing": len(exception_config["allow_missing"]),
                "box_mappings": len(exception_config["box_mappings"]),
            },
        },
        "slide_mappings": slide_mappings,
        "translation_box_mappings": translation_box_mappings,
        "translation_exceptions_applied": translation_exceptions_applied,
        "translation_exception_issues": translation_exception_issues,
        "differences": differences,
        "translation_warnings": translation_warnings,
        "translation_status": translation_status,
        "violations": violations,
        "summary": {
            "difference_count": len(differences),
            "unauthorized_change_count": sum(
                1 for item in differences if not item["authorized"]
            ),
            "translation_warning_count": len(translation_warnings),
            "translation_box_mapping_count": len(translation_box_mappings),
            "translation_exception_applied_count": len(
                translation_exceptions_applied
            ),
            "translation_exception_issue_count": len(translation_exception_issues),
            "violation_count": len(violations),
        },
        "ok": ok,
        "exit_code": 0 if ok else 1,
    }


def manifest_to_text(manifest: dict[str, object]) -> str:
    lines = [
        "PPTX STRUCTURE MANIFEST",
        f"Path: {manifest['path']}",
        f"Package SHA-256: {manifest['package_fingerprint']}",
        f"Slides: {manifest['slide_count']}",
        f"Integrity: {'PASS' if manifest['integrity_ok'] else 'WARNING'}",
    ]
    for slide in manifest["slides"]:
        layout = slide["layout"]
        layout_label = layout["name"] or layout["type"] or layout["part"] or "(none)"
        title = json.dumps(slide["title"], ensure_ascii=False)
        lines.extend(
            [
                "",
                (
                    f"Slide {slide['page']}: id={slide['slide_id']} "
                    f"hidden={'yes' if slide['hidden'] else 'no'} part={slide['part']}"
                ),
                f"  Layout: {layout_label} [{layout['part'] or 'none'}]",
                f"  Title: {title}",
                f"  Text boxes: {slide['text_box_count']}",
                f"  Structure SHA-256: {slide['structure_fingerprint']}",
                f"  Text SHA-256: {slide['text_fingerprint']}",
                f"  Slide-local parts: {len(slide['local_parts'])}",
            ]
        )
        for box in slide["text_boxes"]:
            bbox = box["bbox"]
            bbox_text = (
                f"x={bbox['x']},y={bbox['y']},cx={bbox['cx']},cy={bbox['cy']}"
                if bbox
                else "unknown"
            )
            lines.append(
                f"    Text box {box['key']} bbox=({bbox_text}) "
                f"placeholder={box['placeholder_type'] or '-'}: {_excerpt(str(box['text']))!r}"
            )
    lines.extend(["", f"Protected shared parts: {len(manifest['shared_parts'])}"])
    for part, fingerprint in manifest["shared_parts"].items():
        lines.append(f"  {part}: {fingerprint}")
    for warning in manifest["integrity_warnings"]:
        lines.append(f"INTEGRITY WARNING [{warning['code']}]: {warning['message']}")
    return "\n".join(lines) + "\n"


def comparison_to_text(report: dict[str, object]) -> str:
    lines = [
        "PPTX STRUCTURE COMPARISON",
        f"Source: {report['source']['path']} ({report['source']['slide_count']} slides)",
        f"Target: {report['target']['path']} ({report['target']['slide_count']} slides)",
        (
            "Policy: slides="
            + (",".join(str(page) for page in report["policy"]["allow_slides"]) or "none")
            + f" shared={'allowed' if report['policy']['allow_shared'] else 'blocked'}"
            + f" target-language={report['policy']['target_language'] or 'unspecified'}"
            + (
                f" exceptions={report['policy']['translation_exceptions']}"
                if report["policy"]["translation_exceptions"]
                else " exceptions=none"
            )
        ),
        "",
        "Changes:",
    ]
    if not report["differences"]:
        lines.append("  (none)")
    for item in report["differences"]:
        status = "ALLOWED" if item["authorized"] else "FAIL"
        lines.append(f"  [{status}] {item['code']}: {item['message']}")
    if report["policy"]["translation_check"]:
        lines.extend(["", f"Translation audit: {report['translation_status'].upper()}"])
        mapping_counts = Counter(
            item["mapping"] for item in report["translation_box_mappings"]
        )
        mapping_summary = ", ".join(
            f"{method}={count}" for method, count in sorted(mapping_counts.items())
        )
        lines.append(f"  Text-box mappings: {mapping_summary or 'none'}")
        lines.append(
            f"  Exceptions applied: {len(report['translation_exceptions_applied'])}"
        )
        for item in report["translation_exceptions_applied"]:
            lines.append(
                f"  [APPLIED] {item['rule_id']} ({item['kind']}): "
                f"source={item.get('source_page', '-')} target={item.get('target_page', '-')} "
                f"box={item.get('shape_key', item.get('source_key', '-'))}"
            )
        if not report["translation_warnings"] and not report["translation_exception_issues"]:
            lines.append("  (no warnings or exception issues)")
        for item in report["translation_warnings"]:
            lines.append(f"  [WARN] {item['code']}: {item['message']}")
        for item in report["translation_exception_issues"]:
            lines.append(f"  [EXCEPTION ISSUE] {item['code']}: {item['message']}")
    lines.extend(
        [
            "",
            f"Result: {'PASS' if report['ok'] else 'FAIL'}",
            f"Violations: {report['summary']['violation_count']}",
        ]
    )
    return "\n".join(lines) + "\n"


def _json_text(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _write_output(
    content: str,
    output: Path | None,
    protected_inputs: Sequence[Path],
) -> None:
    if output is None or str(output) == "-":
        sys.stdout.write(content)
        return
    destination = output.expanduser().resolve()
    if destination.suffix.casefold() == ".pptx":
        raise AuditError("refusing to write audit output to a .pptx path")
    protected = {path.expanduser().resolve() for path in protected_inputs}
    if destination in protected:
        raise AuditError("refusing to overwrite an input PPTX")
    destination.write_text(content, encoding="utf-8", newline="\n")


def _add_output_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )
    parser.add_argument(
        "--json",
        action="store_const",
        const="json",
        dest="format",
        help="shortcut for --format json",
    )
    parser.add_argument("-o", "--output", type=Path, help="write report to this file")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only PPTX manifest, edit-scope, and translation audit."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    manifest_parser = commands.add_parser("manifest", help="inventory one PPTX")
    manifest_parser.add_argument("pptx", type=Path)
    manifest_parser.add_argument(
        "--allow-warnings",
        action="store_true",
        help="emit integrity warnings but return zero (diagnostic use only)",
    )
    _add_output_options(manifest_parser)

    compare_parser = commands.add_parser(
        "compare",
        help="compare source and target PPTX",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=TRANSLATION_EXCEPTIONS_HELP,
    )
    compare_parser.add_argument("source", type=Path)
    compare_parser.add_argument("target", type=Path)
    compare_parser.add_argument(
        "--allow-slides",
        action="append",
        default=[],
        metavar="RANGE",
        help="authorize one-based true pages, e.g. 2-4,7 (repeatable)",
    )
    compare_parser.add_argument(
        "--allow-shared",
        action="store_true",
        help="authorize changes under slideMasters, slideLayouts, and theme",
    )
    compare_parser.add_argument(
        "--translation-check",
        "--check-translation",
        action="store_true",
        help="check text-box completeness and title question-mark consistency",
    )
    compare_parser.add_argument(
        "--strict-translation",
        action="store_true",
        help="make translation warnings fail the audit (implies translation check)",
    )
    compare_parser.add_argument(
        "--target-language",
        choices=("en", "zh"),
        help=(
            "enable target-language residue checks: en flags CJK; zh flags only "
            "obvious English prose"
        ),
    )
    compare_parser.add_argument(
        "--translation-exceptions",
        type=Path,
        metavar="JSON",
        help="read page-scoped translation exceptions from a JSON file",
    )
    compare_parser.add_argument(
        "--map-slides",
        choices=("auto", "id", "order"),
        default="auto",
        help=(
            "slide mapping strategy; auto uses stable id then provisional true-order "
            "fallback, while order explicitly selects true-order mapping"
        ),
    )
    _add_output_options(compare_parser)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "manifest":
            manifest = build_manifest(args.pptx)
            content = _json_text(manifest) if args.format == "json" else manifest_to_text(manifest)
            _write_output(content, args.output, [args.pptx])
            return 0 if manifest["integrity_ok"] or args.allow_warnings else 1

        allowed: set[int] = set()
        for spec in args.allow_slides:
            allowed.update(parse_slide_ranges(spec))
        report = compare_pptx(
            args.source,
            args.target,
            allow_slides=allowed,
            allow_shared=args.allow_shared,
            translation_check=args.translation_check,
            strict_translation=args.strict_translation,
            target_language=args.target_language,
            translation_exceptions=args.translation_exceptions,
            mapping=args.map_slides,
        )
        content = _json_text(report) if args.format == "json" else comparison_to_text(report)
        protected_inputs = [args.source, args.target]
        if args.translation_exceptions is not None:
            protected_inputs.append(args.translation_exceptions)
        _write_output(content, args.output, protected_inputs)
        return int(report["exit_code"])
    except (AuditError, OSError) as exc:
        print(f"audit_pptx_structure: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
