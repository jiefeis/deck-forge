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
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Iterable, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _pptx_common import (  # noqa: E402
    FALSE_VALUES,
    NS,
    AuditError,
    _parse_xml,
    _rels_part,
    _resolve_target,
    _shown,
    q,
)

# The translation QA subsystem (language heuristics, text-box matching, the
# exceptions schema) lives in its own module: audit_pptx_backups,
# audit_pptx_properties, and transplant_pptx_slides import this file only for
# AuditError and build_manifest, and never reach any of it. _excerpt and
# _slide_mapping_evidence are shared with that subsystem and are defined there
# so the import stays one-directional.
from _pptx_translation import (  # noqa: E402
    TRANSLATION_EXCEPTIONS_HELP,
    _excerpt,
    _load_translation_exceptions,
    _slide_mapping_evidence,
    _translation_warnings,
)

XML_SPACE ="{http://www.w3.org/XML/1998/namespace}space"
SHARED_PREFIXES = (
    "ppt/slideMasters/",
    "ppt/slideLayouts/",
    "ppt/theme/",
)
GRAPH_STOP_PREFIXES = SHARED_PREFIXES + (
    "ppt/notesMasters/",
    "ppt/handoutMasters/",
)


def _root_for(
    zf: zipfile.ZipFile,
    part: str,
    roots: dict[str, ET.Element] | None,
) -> ET.Element:
    """Parse ``part``, reusing ``roots`` when the caller supplied a cache.

    build_manifest reads several parts (layouts, shared rels, the slide itself)
    more than once per package; the trees are only ever read, never mutated.
    """

    if roots is None:
        return _parse_xml(zf.read(part), part)
    root = roots.get(part)
    if root is None:
        root = _parse_xml(zf.read(part), part)
        roots[part] = root
    return root


def _relationships(
    zf: zipfile.ZipFile,
    source_part: str,
    names: set[str],
    roots: dict[str, ET.Element] | None = None,
) -> list[dict[str, str]]:
    rels_part = _rels_part(source_part)
    if rels_part not in names:
        return []
    root = _root_for(zf, rels_part, roots)
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


def _canonical_tree_for_fingerprint(element: ET.Element, strip_drawing_text: bool) -> object:
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

    children = [
        _canonical_tree_for_fingerprint(child, strip_drawing_text) for child in element
    ]
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


def _root_fingerprint(root: ET.Element, *, strip_drawing_text: bool = False) -> str:
    return _fingerprint_payload(
        _canonical_tree_for_fingerprint(root, strip_drawing_text)
    )


def _part_fingerprint(
    zf: zipfile.ZipFile,
    part: str,
    fingerprints: dict[str, str] | None = None,
    roots: dict[str, ET.Element] | None = None,
) -> str:
    if fingerprints is not None and part in fingerprints:
        return fingerprints[part]
    if part.endswith((".xml", ".rels")):
        value = _root_fingerprint(_root_for(zf, part, roots))
    else:
        value = hashlib.sha256(zf.read(part)).hexdigest()
    if fingerprints is not None:
        fingerprints[part] = value
    return value


def _as_slide_id(value: str) -> int | str:
    try:
        return int(value)
    except ValueError:
        return value


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
    roots: dict[str, ET.Element] | None = None,
) -> tuple[dict[str, str], ET.Element | None, tuple[str, str] | None]:
    layout_part = ""
    for rel in _relationships(zf, slide_part, names, roots):
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
    root = _root_for(zf, layout_part, roots)
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
    roots: dict[str, ET.Element] | None = None,
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
        for rel in _relationships(zf, part, names, roots):
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


def _shared_parts(
    zf: zipfile.ZipFile,
    names: set[str],
    fingerprints: dict[str, str] | None = None,
    roots: dict[str, ET.Element] | None = None,
) -> dict[str, str]:
    return {
        part: _part_fingerprint(zf, part, fingerprints, roots)
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
            # Per-package caches, valid only while the archive is open. Layouts,
            # masters, themes, and shared media are otherwise re-read and
            # re-hashed once per referencing slide.
            roots: dict[str, ET.Element] = {}
            fingerprints: dict[str, str] = {}
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

            presentation = _root_for(zf, "ppt/presentation.xml", roots)
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
                for rel in _relationships(zf, "ppt/presentation.xml", names, roots)
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
            visible_ordinal = 0
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
                    hidden = not _shown(slide_node.get("show"))
                    if not hidden:
                        visible_ordinal += 1
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
                            "physical_page": page,
                            "visible_ordinal": None if hidden else visible_ordinal,
                            "slide_id": stable_id,
                            "relationship_id": relationship_id,
                            "part": "",
                            "hidden": hidden,
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
                    hidden = not _shown(slide_node.get("show"))
                    if not hidden:
                        visible_ordinal += 1
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
                            "physical_page": page,
                            "visible_ordinal": None if hidden else visible_ordinal,
                            "slide_id": stable_id,
                            "relationship_id": relationship_id,
                            "part": slide_part,
                            "hidden": hidden,
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
                slide_root = _root_for(zf, slide_part, roots)
                layout, layout_root, layout_issue = _layout_info(
                    zf, slide_part, names, roots
                )
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
                    part: _part_fingerprint(zf, part, fingerprints, roots)
                    for part in _local_part_closure(zf, slide_part, names, roots)
                }
                # Slide-local trees are not reachable from any other slide, so
                # drop them here: peak memory tracks one slide, not the deck.
                for part in local_parts:
                    roots.pop(part, None)
                hidden = not (
                    _shown(slide_node.get("show")) and _shown(slide_root.get("show"))
                )
                if not hidden:
                    visible_ordinal += 1
                slides.append(
                    {
                        "page": page,
                        "physical_page": page,
                        "visible_ordinal": None if hidden else visible_ordinal,
                        "slide_id": stable_id,
                        "relationship_id": relationship_id,
                        "part": slide_part,
                        "hidden": hidden,
                        "layout": layout,
                        "title": title,
                        "title_source": title_source,
                        "text_box_count": len(boxes),
                        "text_boxes": boxes,
                        "structure_fingerprint": _root_fingerprint(
                            slide_root,
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
            shared_parts = _shared_parts(zf, names, fingerprints, roots)
    except zipfile.BadZipFile as exc:
        raise AuditError(f"not a valid PPTX ZIP package: {pptx}") from exc

    return {
        "schema_version": 1,
        "kind": "pptx-structure-manifest",
        "path": str(pptx),
        "package_fingerprint": package_fingerprint,
        "slide_size": slide_size,
        "slide_count": len(slides),
        "visible_slide_count": sum(not slide["hidden"] for slide in slides),
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
        (
            f"Slides: {manifest['slide_count']} physical / "
            f"{manifest['visible_slide_count']} visible"
        ),
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
                    f"Physical {slide['physical_page']}: "
                    f"visible={slide['visible_ordinal'] or '-'} "
                    f"id={slide['slide_id']} "
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
