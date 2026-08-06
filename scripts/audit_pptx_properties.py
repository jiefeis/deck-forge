#!/usr/bin/env python3
"""Fail-closed, property-level scope audit for native PPTX edits.

The broader structure auditor can authorize a changed slide. This companion
answers the narrower question: which property families changed on that slide,
and were those exact families authorized? Inputs are opened read-only.
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
from typing import Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _pptx_common import AuditError, _parse_xml, _rels_part  # noqa: E402
from audit_pptx_structure import build_manifest  # noqa: E402


P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"p": P_NS, "a": A_NS, "r": R_NS, "rel": REL_NS}

CATEGORIES = {
    "text",
    "typography",
    "color",
    "background",
    "geometry",
    "shape-tree",
    "relationships",
    "media-data",
    "notes",
    "timing",
    "hidden",
    "order",
    "other",
}
SHAPE_TAGS = {
    f"{{{P_NS}}}sp",
    f"{{{P_NS}}}pic",
    f"{{{P_NS}}}graphicFrame",
    f"{{{P_NS}}}cxnSp",
    f"{{{P_NS}}}grpSp",
    f"{{{P_NS}}}contentPart",
}
COLOR_TAGS = {
    "solidFill", "gradFill", "pattFill", "noFill", "srgbClr", "scrgbClr",
    "schemeClr", "prstClr", "sysClr", "hslClr", "alpha", "alphaMod",
    "alphaOff", "tint", "shade", "lumMod", "lumOff", "satMod", "satOff",
    "hueMod", "hueOff", "red", "green", "blue", "gamma", "invGamma",
    "highlight", "fillRef", "lnRef", "effectRef",
}
TYPOGRAPHY_TAGS = {
    "rPr", "defRPr", "endParaRPr", "latin", "ea", "cs", "sym", "fontRef",
}
GEOMETRY_TAGS = {
    "xfrm", "off", "ext", "chOff", "chExt", "prstGeom", "custGeom",
    "avLst", "gdLst", "ahLst", "cxnLst", "rect", "pathLst", "path",
    "moveTo", "lnTo", "arcTo", "cubicBezTo", "quadBezTo", "close",
    "bodyPr", "spAutoFit", "normAutofit", "noAutofit", "srcRect",
}
TIMING_TAGS = {
    "timing", "transition", "tnLst", "bldLst", "par", "seq", "cTn",
    "childTnLst", "subTnLst", "anim", "animClr", "animEffect", "animMotion",
    "animRot", "animScale", "cmd", "set", "video", "audio",
}
GLOBAL_PROTECTED_PARTS = {"ppt/presProps.xml", "ppt/tableStyles.xml"}
GLOBAL_PROTECTED_PREFIXES = ("ppt/notesMasters/", "ppt/handoutMasters/")


def _local_name(value: str) -> str:
    return value.rsplit("}", 1)[-1]


def _namespace(value: str) -> str:
    return value[1:].split("}", 1)[0] if value.startswith("{") else ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_ranges(value: object) -> set[int]:
    if isinstance(value, list):
        if not value or any(not isinstance(item, int) or item < 1 for item in value):
            raise AuditError("scope pages must be a non-empty list of positive integers")
        return set(value)
    if not isinstance(value, str) or not value.strip():
        raise AuditError("scope pages must be a range string or integer list")
    pages: set[int] = set()
    for raw in value.split(","):
        token = raw.strip()
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", token)
        if not match:
            raise AuditError(f"invalid scope page range token: {token!r}")
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if start < 1 or end < start or end - start > 100000:
            raise AuditError(f"invalid scope page range: {token!r}")
        pages.update(range(start, end + 1))
    return pages


def _load_scope(
    path: Path | None,
    source_manifest: dict[str, object],
    target_manifest: dict[str, object],
) -> list[dict[str, object]]:
    if path is None:
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"cannot read scope JSON {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise AuditError("scope JSON must be an object with version: 1")
    if set(payload) != {"version", "rules"} or not isinstance(payload.get("rules"), list):
        raise AuditError("scope JSON keys must be exactly version and rules")

    source_slides = list(source_manifest["slides"])
    target_slides = list(target_manifest["slides"])
    source_by_page = {int(slide["page"]): slide for slide in source_slides}
    source_by_id = {str(slide["slide_id"]): slide for slide in source_slides}
    target_by_page = {int(slide["page"]): slide for slide in target_slides}
    target_by_id = {str(slide["slide_id"]): slide for slide in target_slides}
    rules: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    claims: dict[tuple[str, str], str] = {}

    for index, raw in enumerate(payload["rules"], 1):
        if not isinstance(raw, dict):
            raise AuditError(f"scope rule {index} must be an object")
        unknown = set(raw) - {
            "id", "pages", "slide_ids", "target_pages", "target_slide_ids",
            "properties",
        }
        if unknown:
            raise AuditError(f"scope rule {index} has unknown keys: {sorted(unknown)}")
        rule_id = raw.get("id")
        if not isinstance(rule_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", rule_id):
            raise AuditError(f"scope rule {index} needs a stable id")
        if rule_id in seen_ids:
            raise AuditError(f"duplicate scope rule id: {rule_id}")
        seen_ids.add(rule_id)

        selected_ids: set[str] = set()
        if "pages" in raw:
            for page in _parse_ranges(raw["pages"]):
                slide = source_by_page.get(page)
                if slide is None:
                    raise AuditError(f"scope rule {rule_id} selects missing source page {page}")
                selected_ids.add(str(slide["slide_id"]))
        if "slide_ids" in raw:
            values = raw["slide_ids"]
            if not isinstance(values, list) or not values:
                raise AuditError(f"scope rule {rule_id} slide_ids must be non-empty")
            for value in values:
                key = str(value)
                if key not in source_by_id:
                    raise AuditError(f"scope rule {rule_id} selects missing slide id {value!r}")
                selected_ids.add(key)
        if "target_pages" in raw:
            for page in _parse_ranges(raw["target_pages"]):
                slide = target_by_page.get(page)
                if slide is None:
                    raise AuditError(f"scope rule {rule_id} selects missing target page {page}")
                selected_ids.add(str(slide["slide_id"]))
        if "target_slide_ids" in raw:
            values = raw["target_slide_ids"]
            if not isinstance(values, list) or not values:
                raise AuditError(
                    f"scope rule {rule_id} target_slide_ids must be non-empty"
                )
            for value in values:
                key = str(value)
                if key not in target_by_id:
                    raise AuditError(
                        f"scope rule {rule_id} selects missing target slide id {value!r}"
                    )
                selected_ids.add(key)
        if not selected_ids:
            raise AuditError(
                f"scope rule {rule_id} must select source or target pages/slide_ids"
            )

        properties = raw.get("properties")
        if not isinstance(properties, list) or not properties:
            raise AuditError(f"scope rule {rule_id} properties must be non-empty")
        if any(not isinstance(item, str) for item in properties):
            raise AuditError(f"scope rule {rule_id} properties must be strings")
        prop_set = set(properties)
        invalid = prop_set - CATEGORIES
        if invalid:
            raise AuditError(f"scope rule {rule_id} has invalid properties: {sorted(invalid)}")
        for slide_id in selected_ids:
            for category in prop_set:
                claim = (slide_id, category)
                if claim in claims:
                    raise AuditError(
                        f"scope rules {claims[claim]} and {rule_id} overlap on "
                        f"slide {slide_id} property {category}"
                    )
                claims[claim] = rule_id
        rules.append(
            {
                "id": rule_id,
                "slide_ids": selected_ids,
                "properties": prop_set,
                "used": False,
            }
        )
    return rules


def _canonical_xml_for_property_diff(
    element: ET.Element, *, sort_children: bool = False
) -> object:
    children = [
        _canonical_xml_for_property_diff(child, sort_children=sort_children)
        for child in list(element)
    ]
    if sort_children:
        children.sort(key=lambda item: json.dumps(item, ensure_ascii=True, separators=(",", ":")))
    text = element.text or ""
    if text.isspace():
        text = ""
    return [element.tag, sorted(element.attrib.items()), text, children]


def _protected_global_parts(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    with zipfile.ZipFile(path, "r") as zf:
        names = set(zf.namelist())
        presentation_part = "ppt/presentation.xml"
        if presentation_part in names:
            root = _parse_xml(zf.read(presentation_part), presentation_part)
            for tag in (
                f"{{{P_NS}}}sldIdLst",
                f"{{{P_NS}}}sldSz",
            ):
                child = root.find(tag)
                if child is not None:
                    root.remove(child)
            payload = _canonical_xml_for_property_diff(root)
            result[presentation_part + "#non-slide"] = hashlib.sha256(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            ).hexdigest()

        presentation_rels = "ppt/_rels/presentation.xml.rels"
        if presentation_rels in names:
            root = _parse_xml(zf.read(presentation_rels), presentation_rels)
            for rel in list(root):
                if rel.get("Type", "").endswith("/slide"):
                    root.remove(rel)
            payload = _canonical_xml_for_property_diff(root, sort_children=True)
            result[presentation_rels + "#non-slide"] = hashlib.sha256(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            ).hexdigest()

        for part in sorted(names):
            if part in GLOBAL_PROTECTED_PARTS or part.startswith(GLOBAL_PROTECTED_PREFIXES):
                data = zf.read(part)
                if part.endswith((".xml", ".rels")):
                    payload = _canonical_xml_for_property_diff(
                        _parse_xml(data, part),
                        sort_children=part.endswith(".rels"),
                    )
                    data = json.dumps(
                        payload, ensure_ascii=False, separators=(",", ":")
                    ).encode("utf-8")
                result[part] = hashlib.sha256(data).hexdigest()
    return result


def _shape_id(shape: ET.Element) -> str:
    non_visual = shape.find(".//p:cNvPr", NS)
    return non_visual.get("id", "") if non_visual is not None else ""


def _shape_records(root: ET.Element) -> tuple[list[dict[str, object]], list[str]]:
    tree = root.find("p:cSld/p:spTree", NS)
    if tree is None:
        return [], []
    records: list[dict[str, object]] = []

    def visit(container: ET.Element, parent: str) -> None:
        ordinal = 0
        for child in list(container):
            if child.tag not in SHAPE_TAGS:
                continue
            ordinal += 1
            shape_id = _shape_id(child)
            fallback = f"path:{parent}/{ordinal}:{_local_name(child.tag)}"
            key = f"id:{shape_id}" if shape_id else fallback
            records.append(
                {
                    "key": key,
                    "shape_id": shape_id,
                    "tag": _local_name(child.tag),
                    "parent": parent,
                    "ordinal": ordinal,
                    "element": child,
                }
            )
            if child.tag == f"{{{P_NS}}}grpSp":
                visit(child, key)

    visit(tree, "root")
    counts = Counter(str(record["key"]) for record in records)
    duplicates = sorted(key for key, count in counts.items() if count > 1)
    return records, duplicates


def _classify(chain: tuple[str, ...], field: str) -> str:
    tags = set(chain)
    current = chain[-1] if chain else ""
    if "bg" in tags:
        return "background"
    if tags & TIMING_TAGS:
        return "timing"
    if "tbl" in tags:
        return "media-data"
    if current == "t" and field == "#text":
        return "text"
    if tags & COLOR_TAGS:
        return "color"
    if tags & TYPOGRAPHY_TAGS:
        return "typography"
    if tags & GEOMETRY_TAGS:
        return "geometry"
    if current == "cNvPr" and field in {"@id", "@name"}:
        return "shape-tree"
    if field.startswith("@r:"):
        return "relationships"
    return "other"


def _flatten(
    element: ET.Element,
    *,
    skip_nested_shapes: bool,
    skip_show: bool = False,
) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}

    def visit(node: ET.Element, path: str, chain: tuple[str, ...], is_root: bool) -> None:
        current = _local_name(node.tag)
        next_chain = (*chain, current)
        for raw_name, value in sorted(node.attrib.items()):
            local = _local_name(raw_name)
            if skip_show and is_root and local == "show":
                continue
            namespace = _namespace(raw_name)
            prefix = "r:" if namespace == R_NS else ""
            field = f"@{prefix}{local}"
            result[f"{path}/{field}"] = (value, _classify(next_chain, field))
        if node.text is not None and not node.text.isspace():
            result[f"{path}/#text"] = (node.text, _classify(next_chain, "#text"))
        counts: Counter[str] = Counter()
        for child in list(node):
            if skip_nested_shapes and child.tag in SHAPE_TAGS:
                continue
            name = _local_name(child.tag)
            counts[name] += 1
            visit(child, f"{path}/{name}[{counts[name]}]", next_chain, False)

    visit(element, _local_name(element.tag), (), True)
    return result


def _changed_categories(
    before: dict[str, tuple[str, str]],
    after: dict[str, tuple[str, str]],
) -> set[str]:
    categories: set[str] = set()
    for key in set(before) | set(after):
        if before.get(key) == after.get(key):
            continue
        if key in before:
            categories.add(before[key][1])
        if key in after:
            categories.add(after[key][1])
    return categories


def _slide_level(root: ET.Element) -> dict[str, tuple[str, str]]:
    clone = ET.fromstring(ET.tostring(root, encoding="utf-8"))
    tree = clone.find("p:cSld/p:spTree", NS)
    if tree is not None:
        for child in list(tree):
            if child.tag in SHAPE_TAGS:
                tree.remove(child)
    return _flatten(clone, skip_nested_shapes=False, skip_show=True)


def _relationship_signature(zf: zipfile.ZipFile, slide_part: str) -> list[tuple[str, ...]]:
    part = _rels_part(slide_part)
    if part not in zf.namelist():
        return []
    root = _parse_xml(zf.read(part), part)
    result: list[tuple[str, ...]] = []
    for rel in root.findall(f"{{{REL_NS}}}Relationship"):
        rel_type = rel.get("Type", "")
        if rel_type.endswith("/notesSlide"):
            continue
        result.append(
            (
                rel.get("Id", ""),
                rel_type,
                rel.get("Target", ""),
                rel.get("TargetMode", ""),
            )
        )
    return sorted(result)


def _local_hashes(slide: dict[str, object], kind: str) -> list[str]:
    parts = dict(slide["local_parts"])
    if kind == "notes":
        selected = [value for key, value in parts.items() if key.startswith("ppt/notesSlides/")]
    else:
        selected = [
            value
            for key, value in parts.items()
            if not key.startswith("ppt/slides/")
            and not key.startswith("ppt/notesSlides/")
        ]
    return sorted(selected)


def _authorize(
    slide_id: str,
    category: str,
    rules: list[dict[str, object]],
) -> list[str]:
    matched: list[str] = []
    for rule in rules:
        if slide_id in rule["slide_ids"] and category in rule["properties"]:
            rule["used"] = True
            matched.append(str(rule["id"]))
    return matched


def audit_properties(
    source: Path,
    target: Path,
    *,
    scope_path: Path | None = None,
) -> dict[str, object]:
    source = source.expanduser().resolve()
    target = target.expanduser().resolve()
    if not source.is_file() or not target.is_file():
        raise AuditError("source and target PPTX files must exist")
    source_hash_before = _sha256(source)
    target_hash_before = _sha256(target)
    before = build_manifest(source)
    after = build_manifest(target)
    rules = _load_scope(
        scope_path.expanduser().resolve() if scope_path else None,
        before,
        after,
    )
    changes: list[dict[str, object]] = []
    violations: list[dict[str, object]] = []

    def add_change(
        slide_id: object,
        category: str,
        source_page: int | None,
        target_page: int | None,
        details: str,
    ) -> None:
        key = str(slide_id)
        rule_ids = _authorize(key, category, rules)
        item = {
            "slide_id": slide_id,
            "source_page": source_page,
            "target_page": target_page,
            "property": category,
            "details": details,
            "authorized": bool(rule_ids),
            "rule_ids": rule_ids,
        }
        changes.append(item)
        if not rule_ids:
            violations.append({"code": "unauthorized-property-change", **item})

    for side, manifest in (("source", before), ("target", after)):
        if not manifest["integrity_ok"]:
            for warning in manifest["integrity_warnings"]:
                violations.append({"code": f"{side}-integrity-warning", **warning})

    before_by_id = {str(slide["slide_id"]): slide for slide in before["slides"]}
    after_by_id = {str(slide["slide_id"]): slide for slide in after["slides"]}
    all_ids = sorted(set(before_by_id) | set(after_by_id))

    with zipfile.ZipFile(source, "r") as source_zip, zipfile.ZipFile(target, "r") as target_zip:
        for slide_id in all_ids:
            left = before_by_id.get(slide_id)
            right = after_by_id.get(slide_id)
            if left is None or right is None:
                present = left or right
                add_change(
                    present["slide_id"],
                    "order",
                    int(left["page"]) if left else None,
                    int(right["page"]) if right else None,
                    "stable slide id was added to or removed from the presentation",
                )
                continue
            source_page = int(left["page"])
            target_page = int(right["page"])
            stable_id = left["slide_id"]
            if source_page != target_page:
                add_change(stable_id, "order", source_page, target_page, "true-order page changed")
            if bool(left["hidden"]) != bool(right["hidden"]):
                add_change(stable_id, "hidden", source_page, target_page, "hidden state changed")

            left_root = _parse_xml(source_zip.read(str(left["part"])), str(left["part"]))
            right_root = _parse_xml(target_zip.read(str(right["part"])), str(right["part"]))
            left_records, left_duplicates = _shape_records(left_root)
            right_records, right_duplicates = _shape_records(right_root)
            if left_duplicates or right_duplicates:
                add_change(
                    stable_id,
                    "shape-tree",
                    source_page,
                    target_page,
                    f"ambiguous duplicate shape ids: source={left_duplicates}, target={right_duplicates}",
                )

            left_tree = [
                (record["key"], record["tag"], record["parent"], record["ordinal"])
                for record in left_records
            ]
            right_tree = [
                (record["key"], record["tag"], record["parent"], record["ordinal"])
                for record in right_records
            ]
            if left_tree != right_tree and not (left_duplicates or right_duplicates):
                add_change(
                    stable_id, "shape-tree", source_page, target_page,
                    "shape insertion/deletion/type/group/order changed",
                )

            left_shapes = {str(record["key"]): record for record in left_records}
            right_shapes = {str(record["key"]): record for record in right_records}
            categories = _changed_categories(_slide_level(left_root), _slide_level(right_root))
            for key in set(left_shapes) & set(right_shapes):
                categories.update(
                    _changed_categories(
                        _flatten(left_shapes[key]["element"], skip_nested_shapes=True),
                        _flatten(right_shapes[key]["element"], skip_nested_shapes=True),
                    )
                )

            if _relationship_signature(source_zip, str(left["part"])) != _relationship_signature(
                target_zip, str(right["part"])
            ):
                categories.add("relationships")
            if _local_hashes(left, "media") != _local_hashes(right, "media"):
                categories.add("media-data")
            if _local_hashes(left, "notes") != _local_hashes(right, "notes"):
                categories.add("notes")
            for category in sorted(categories):
                add_change(
                    stable_id, category, source_page, target_page,
                    "slide-local property fingerprint changed",
                )

    if before["slide_size"] != after["slide_size"]:
        violations.append(
            {
                "code": "global-slide-size-change",
                "details": f"{before['slide_size']} -> {after['slide_size']}",
            }
        )
    shared_changed = sorted(
        part
        for part in set(before["shared_parts"]) | set(after["shared_parts"])
        if before["shared_parts"].get(part) != after["shared_parts"].get(part)
    )
    for part in shared_changed:
        violations.append(
            {
                "code": "shared-part-change",
                "part": part,
                "details": "master/layout/theme changes are fail-closed",
            }
        )

    source_global = _protected_global_parts(source)
    target_global = _protected_global_parts(target)
    for part in sorted(set(source_global) | set(target_global)):
        if source_global.get(part) != target_global.get(part):
            violations.append(
                {
                    "code": "global-presentation-part-change",
                    "part": part,
                    "details": "protected presentation/notes/handout settings changed",
                }
            )

    for rule in rules:
        if not rule["used"]:
            violations.append(
                {
                    "code": "unused-scope-rule",
                    "rule_id": rule["id"],
                    "details": "rule did not authorize any observed change",
                }
            )

    source_unchanged = source_hash_before == _sha256(source)
    target_unchanged = target_hash_before == _sha256(target)
    if not source_unchanged or not target_unchanged:
        raise AuditError("an input PPTX changed while the read-only audit was running")
    ok = not violations
    return {
        "schema_version": 1,
        "kind": "pptx-property-scope-audit",
        "source": {"path": str(source), "sha256": source_hash_before},
        "target": {"path": str(target), "sha256": target_hash_before},
        "scope": {
            "path": str(scope_path.expanduser().resolve()) if scope_path else None,
            "rules": [
                {
                    "id": rule["id"],
                    "slide_ids": sorted(rule["slide_ids"]),
                    "properties": sorted(rule["properties"]),
                    "used": rule["used"],
                }
                for rule in rules
            ],
        },
        "changes": changes,
        "violations": violations,
        "summary": {
            "change_count": len(changes),
            "authorized_change_count": sum(bool(item["authorized"]) for item in changes),
            "violation_count": len(violations),
        },
        "inputs_unchanged": source_unchanged and target_unchanged,
        "ok": ok,
        "exit_code": 0 if ok else 1,
    }


def report_to_text(report: dict[str, object]) -> str:
    lines = [
        "PPTX PROPERTY SCOPE AUDIT",
        f"Source: {report['source']['path']}",
        f"Target: {report['target']['path']}",
        f"Scope: {report['scope']['path'] or 'deny all changes'}",
        "",
    ]
    if report["changes"]:
        lines.append("Changes:")
        for item in report["changes"]:
            marker = "ALLOW" if item["authorized"] else "FAIL"
            lines.append(
                f"  [{marker}] slide id {item['slide_id']} "
                f"({item['source_page']}->{item['target_page']}): {item['property']}"
            )
    else:
        lines.append("Changes: none")
    if report["violations"]:
        lines.append("Violations:")
        for item in report["violations"]:
            lines.append(f"  - {item['code']}: {item.get('details', item)}")
    lines.append(f"Result: {'PASS' if report['ok'] else 'FAIL'}")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument(
        "--scope",
        type=Path,
        help=(
            "version-1 JSON with rules containing id, pages and/or slide_ids, "
            "optional target_pages/target_slide_ids for explicit insertions, "
            "and explicit properties"
        ),
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    try:
        report = audit_properties(args.source, args.target, scope_path=args.scope)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            sys.stdout.write(report_to_text(report))
        return int(report["exit_code"])
    except (AuditError, OSError, zipfile.BadZipFile) as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "pptx-property-scope-audit",
                        "ok": False,
                        "exit_code": 2,
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(f"audit_pptx_properties: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
