#!/usr/bin/env python3
"""Translate existing native slide text, table cells and supported native chart text.

    translate_pptx.py extract SOURCE.pptx PLAN.json
    translate_pptx.py apply SOURCE.pptx PLAN.json NEW.pptx

Edit only target in the UTF-8 plan. Null or the original string keeps the
source. A string fills the existing runs using their original boundaries. If
a row has source_runs, target may instead be an array with one string per run
to place emphasis and hyperlinks on the intended translated words. Paragraphs,
hard breaks and dynamic fields retain their positions. Chart aliases share
one editable workbook cell. Numeric data and date categories stay in place.

Single-plot column, bar, line, scatter, pie and doughnut charts are supported.
All physical slides, including hidden ones, participate. Review images,
SmartArt, other embedded objects and dynamic fields separately. Shared layouts,
masters and notes are outside the slide-owned inventory. Unsupported charts
or unsafe workbook sources stop the operation with their slide and shape.
Both destinations must be new. Translation does not call an external service.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from _chart_workbook import checked_zip, copy_archive, replace_runs, xml_bytes, xml_part
from _pptx_charts import read_chart
from _pptx_common import AuditError, NS, q
from _pptx_translation import chart_translation_kind, table_cells
from audit_pptx_structure import build_manifest
from native_charts import _edit_chart, _incoming, _open_chart, _unique_keys


@dataclass
class Field:
    entry: dict
    part: str
    nodes: list
    chart_keys: tuple = ()


@dataclass
class Inventory:
    fields: dict = field(default_factory=dict)
    slides: dict = field(default_factory=dict)
    charts: dict = field(default_factory=dict)
    review: list = field(default_factory=list)

    def add(self, slide, shape, name, kind, key, part, nodes, chart_keys=()):
        source_runs = [n.text or "" for n in nodes]
        source = "".join(source_runs)
        if not source.strip():
            return
        identity = f"slide:{slide['slide_id']}/{key}"
        if identity in self.fields:
            raise AuditError(f"ambiguous translation field {identity}")
        entry = {"id": identity, "page": slide["page"], "hidden": slide["hidden"],
                 "shape_id": shape, "shape_name": name, "kind": kind, "source": source}
        if len(source_runs) > 1:
            entry["source_runs"] = source_runs
        if len(chart_keys) > 1:
            entry["aliases"] = list(chart_keys[1:])
        entry["target"] = None
        self.fields[identity] = Field(entry, part, nodes, chart_keys)

    def plan(self, digest):
        return {"version": 1, "source_sha256": digest, "manual_review": self.review,
                "entries": [item.entry for item in self.fields.values()]}

    def values(self):
        # Include every cached chart value, even protected numbers, excluded
        # dates and other read-only fields. Exact text per original run matters.
        values = {key: [n.text or "" for n in item.nodes]
                  for key, item in self.fields.items() if not item.chart_keys}
        for part, (_, chart) in self.charts.items():
            for key, item in chart.fields.items():
                values[part, key] = [n.text or "" for n in item.nodes]
        return values


def _body_fields(inv, slide, shape, name, kind, prefix, body):
    for p, paragraph in enumerate(body.findall("a:p", NS), 1):
        segment = 1
        nodes = []
        for child in paragraph:
            if child.tag == q("a", "r"):
                texts = child.findall("a:t", NS)
                if len(texts) != 1:
                    raise AuditError(f"invalid text run on page {slide['page']}, {prefix}/p{p}")
                nodes.extend(texts)
            elif child.tag in {q("a", "br"), q("a", "tab"), q("a", "fld")}:
                inv.add(slide, shape, name, kind, f"{prefix}/p{p}/s{segment}", slide["part"], nodes)
                if child.tag == q("a", "fld"):
                    inv.review.append({"page": slide["page"], "shape_id": shape,
                                       "kind": "dynamic-field", "location": f"{prefix}/p{p}/s{segment}"})
                segment += 1
                nodes = []
        inv.add(slide, shape, name, kind, f"{prefix}/p{p}/s{segment}", slide["part"], nodes)


def _slide_fields(inv, slide, root):
    counts = Counter(n.get("id", "") for n in root.iter(q("p", "cNvPr")))

    def check_shape(shape):
        if not re.fullmatch(r"[0-9]+", shape) or counts[shape] != 1:
            raise AuditError(f"missing or ambiguous shape ID {shape!r} on page {slide['page']}")

    for element in root.findall(".//p:sp", NS):
        body = element.find("p:txBody", NS)
        if body is not None:
            props = element.find("p:nvSpPr/p:cNvPr", NS)
            shape = props.get("id", "") if props is not None else ""
            check_shape(shape)
            _body_fields(inv, slide, shape, props.get("name", ""), "text", f"shape:{shape}", body)
    for _, shape, name, row, column, body in table_cells(root):
        check_shape(shape)
        _body_fields(inv, slide, shape, name, "table", f"table:{shape}/r{row}c{column}", body)
    for pic in root.findall(".//p:pic/p:nvPicPr/p:cNvPr", NS):
        inv.review.append({"page": slide["page"], "shape_id": pic.get("id", ""),
                           "kind": "picture", "name": pic.get("name", "")})
    for frame in root.findall(".//p:graphicFrame", NS):
        data = frame.find("a:graphic/a:graphicData", NS)
        if data is not None and any(n.tag in {q("a", "tbl"), q("c", "chart"), q("cx", "chart")} for n in data):
            continue
        props = frame.find("p:nvGraphicFramePr/p:cNvPr", NS)
        inv.review.append({"page": slide["page"], "kind": "graphic-frame",
                           "shape_id": props.get("id", "") if props is not None else "",
                           "name": props.get("name", "") if props is not None else ""})


def _chart_fields(inv, archive, slide, record, incoming, occurrences):
    part = record["part"]
    source = record["workbook"].get("part")
    if part and (incoming[part] != 1 or occurrences[part] != 1):
        raise AuditError(f"shared chart part {part}")
    if source and incoming[source] != 1:
        raise AuditError(f"shared embedded workbook {source}")
    _, chart, book, bindings = _open_chart(archive, record, text_only=True)
    if book is not None:
        book.archive.close()
    inv.charts[part] = record, chart
    groups = defaultdict(list)
    for key in chart.fields:
        groups[bindings.get(key, key)].append(key)
    for keys in groups.values():
        key = keys[0]
        item = chart.fields[key]
        kinds = [chart_translation_kind(k, chart.fields[k].describe()) for k in keys]
        if any(kind is None for kind in kinds):
            continue  # A shared cell also used as protected data cannot be translated.
        if source and key not in bindings and key.startswith("series.") and ".label." not in key:
            raise AuditError(f"{key} has no provable source cell in the embedded workbook")
        inv.add(slide, record["shape_id"], record["name"], kinds[0], f"chart:{record['shape_id']}/{key}",
                part, item.nodes, tuple(keys))


def _collect(archive, manifest):
    if manifest["integrity_warnings"]:
        raise AuditError("presentation has package integrity warnings")
    names = checked_zip(archive)
    occurrences = Counter(chart["part"] for slide in manifest["slides"] for chart in slide["charts"])
    incoming = _incoming(archive, names) if occurrences else {}
    inv = Inventory()
    for slide in manifest["slides"]:
        if type(slide["slide_id"]) is not int or slide["part"] in inv.slides:
            raise AuditError(f"missing or ambiguous stable slide identity on page {slide['page']}")
        root = xml_part(archive, slide["part"])
        inv.slides[slide["part"]] = root
        _slide_fields(inv, slide, root)
        for record in slide["charts"]:
            try:
                _chart_fields(inv, archive, slide, record, incoming, occurrences)
            except (AuditError, ValueError, KeyError, zipfile.BadZipFile, etree.XMLSyntaxError) as exc:
                raise AuditError(f"page {slide['page']}, chart shape {record['shape_id']}: {exc}") from exc
    return inv


def _reviewed_edits(plan, inv, digest):
    expected = inv.plan(digest)
    if not isinstance(plan, dict) or set(plan) != set(expected) or type(plan["version"]) is not int or plan["version"] != 1:
        raise AuditError("invalid translation plan schema")
    if plan["source_sha256"] != digest:
        raise AuditError("stale translation plan: source SHA-256 differs")
    if plan["manual_review"] != inv.review or not isinstance(plan["entries"], list):
        raise AuditError("translation inventory differs; edit only target")
    seen = set()
    edits = {}
    for entry in plan["entries"]:
        key = entry.get("id") if isinstance(entry, dict) else None
        if not isinstance(key, str) or key not in inv.fields or key in seen:
            raise AuditError(f"unknown or duplicate translation field {key!r}")
        seen.add(key)
        item = inv.fields[key]
        reviewed = {**entry, "target": None}
        if "target" not in entry or json.dumps(reviewed, sort_keys=True) != json.dumps(item.entry, sort_keys=True):
            raise AuditError(f"translation inventory differs at {key}; edit only target")
        target = entry["target"]
        if target is None or target == item.entry["source"]:
            continue
        if isinstance(target, list) and "source_runs" in entry and len(target) == len(item.nodes):
            if target == item.entry["source_runs"]:
                continue
            runs = target
        elif isinstance(target, str):
            runs = [target]
        else:
            raise AuditError(f"expected a string or one string per original run at {key}")
        if (any(not isinstance(t, str) or any(ord(c) < 32 for c in t) for t in runs)
                or not "".join(runs).strip()):
            raise AuditError(f"translation requires nonempty text with existing breaks at {key}")
        edits[key] = target
    if seen != inv.fields.keys():
        raise AuditError("translation plan is missing source fields")
    return edits


def _fill(nodes, target):
    if isinstance(target, list):
        for node, text in zip(nodes, target):
            replace_runs([node], text)
    else:
        replace_runs(nodes, target)


def _apply(archive, inv, edits):
    slide_parts = set()
    chart_edits = defaultdict(list)
    chart_runs = defaultdict(dict)
    for key, target in edits.items():
        item = inv.fields[key]
        if not item.chart_keys:
            _fill(item.nodes, target)
            slide_parts.add(item.part)
            continue
        chart = inv.charts[item.part][1]
        for alias in item.chart_keys:
            _fill(chart.fields[alias].nodes, target)
        primary = item.chart_keys[0]
        chart_edits[item.part].append({"field": primary, "from": item.entry["source"],
                                       "to": "".join(target) if isinstance(target, list) else target})
        if isinstance(target, list):
            chart_runs[item.part][primary] = target

    changed = {part: xml_bytes(inv.slides[part]) for part in slide_parts}
    for part, requests in chart_edits.items():
        record = inv.charts[part][0]
        parts, _ = _edit_chart(archive, record, requests, text_only=True)
        if chart_runs[part]:
            # The workbook writer has already reconciled any referenced cells.
            # Rich titles/labels can additionally specify exact run boundaries.
            root = (etree.fromstring(parts[part]) if part in parts else xml_part(archive, part))
            chart = read_chart(root, text_only=True)
            for key, target in chart_runs[part].items():
                _fill(chart.fields[key].nodes, target)
            parts[part] = xml_bytes(root)
        changed.update(parts)
    return changed


def _identity(manifest):
    return [(s["page"], s["slide_id"], s["hidden"], s["part"], s["structure_fingerprint"])
            for s in manifest["slides"]]


def _new_path(path):
    path = Path(path).expanduser().absolute()
    if os.path.lexists(path):
        raise AuditError(f"output must be a new path: {path}")
    return path


def _snapshot(source):
    source = Path(source).expanduser().resolve()
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    manifest = build_manifest(source, chart_text_only=True)
    if digest != manifest["package_fingerprint"]:
        raise AuditError("source changed during inspection")
    return source, data, digest, manifest


def _publish(candidate, output, source, digest):
    if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
        raise AuditError("source changed before publication")
    os.link(candidate, output)


def extract(source, output):
    output = _new_path(output)
    source, data, digest, manifest = _snapshot(source)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        inv = _collect(archive, manifest)
    with tempfile.TemporaryDirectory(dir=output.parent) as staging:
        candidate = Path(staging) / "plan.json"
        plan = inv.plan(digest)
        candidate.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _publish(candidate, output, source, digest)
    return {"output": str(output), "source_sha256": digest, "entries": len(inv.fields),
            "manual_review": len(inv.review)}


def apply(source, plan, output):
    output = _new_path(output)
    source, data, digest, manifest = _snapshot(source)
    with tempfile.TemporaryDirectory(dir=output.parent) as staging, zipfile.ZipFile(io.BytesIO(data)) as archive:
        inv = _collect(archive, manifest)
        edits = _reviewed_edits(plan, inv, digest)
        changed = _apply(archive, inv, edits)
        candidate = Path(staging) / "candidate.pptx"
        if changed:
            copy_archive(archive, candidate, changed)
        else:
            candidate.write_bytes(data)
        result = build_manifest(candidate, chart_text_only=True)
        with zipfile.ZipFile(candidate) as checked:
            if (archive.namelist() != checked.namelist() or _identity(manifest) != _identity(result)
                    or any(archive.read(n) != checked.read(n) for n in archive.namelist() if n not in changed)):
                raise AuditError("re-opened output changed package membership, slide structure or an unrelated part")
            actual = _collect(checked, result)
            if actual.values() != inv.values() or actual.review != inv.review:
                raise AuditError("re-opened output differs from reviewed text, chart data or scope")
        _publish(candidate, output, source, digest)
    return {"output": str(output), "source_sha256": digest, "sha256": result["package_fingerprint"],
            "changed_entries": len(edits), "changed_parts": sorted(changed), "verified": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("extract", help="write a new editable UTF-8 JSON inventory")
    collect.add_argument("source", type=Path)
    collect.add_argument("plan", type=Path)
    edit = commands.add_parser("apply", help="apply the reviewed plan and verify a new PPTX")
    edit.add_argument("source", type=Path)
    edit.add_argument("plan", type=Path)
    edit.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "extract":
            result = extract(args.source, args.plan)
        else:
            plan = json.loads(args.plan.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_keys)
            result = apply(args.source, plan, args.output)
        print(json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False))
    except (AuditError, OSError, ValueError, OverflowError, KeyError, zipfile.BadZipFile,
            etree.XMLSyntaxError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
