#!/usr/bin/env python3
"""Inspect and edit existing native column, bar, line and scatter charts in PPTX.

    native_charts.py inspect SOURCE.pptx
    native_charts.py apply SOURCE.pptx EDITS.json OUTPUT.pptx

Inspect returns JSON with physical pages, shape IDs, chart types, source status
and typed fields. Use the exact field key and current value from the inventory:

    {"edits":[{"page":1,"shape_id":"2","field":"series.0.category.0",
               "from":"East","to":"Eastern region"}]}

Use JSON numbers for numeric fields. This edits existing points only. A change
to a referenced cell updates every aliasing cache in the same chart. OUTPUT
must be new. An unresolved, external, shared, formula-driven or stale source
fails before publication. Inspect never opens external sources.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import posixpath
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

from lxml import etree

from _chart_workbook import (Workbook, checked_zip, copy_archive, range_cells, replace_runs,
                             require_content_type, xml_bytes, xml_part)
from _pptx_charts import read_chart
from _pptx_common import AuditError, _relationships
from audit_pptx_structure import build_manifest


def inspect_charts(path):
    manifest = build_manifest(path)
    return {
        "source_sha256": manifest["package_fingerprint"],
        "integrity_warnings": manifest["integrity_warnings"],
        "charts": [
            {"page": slide["page"], "slide_id": slide["slide_id"], "hidden": slide["hidden"], **chart}
            for slide in manifest["slides"] for chart in slide.get("charts", [])
        ],
    }


def _validate_plan(plan):
    if (not isinstance(plan, dict) or set(plan) != {"edits"}
            or not isinstance(plan["edits"], list) or not plan["edits"]):
        raise AuditError('expected an object with a non-empty "edits" array')
    groups = defaultdict(list)
    seen = set()
    for edit in plan["edits"]:
        if not isinstance(edit, dict) or set(edit) != {"page", "shape_id", "field", "from", "to"}:
            raise AuditError("each edit needs exactly page, shape_id, field, from and to")
        page, shape, field = edit["page"], edit["shape_id"], edit["field"]
        if (type(page) is not int or page < 1 or not isinstance(shape, str) or not shape
                or not isinstance(field, str) or not field):
            raise AuditError("invalid physical page, shape_id or field")
        if (page, shape, field) in seen:
            raise AuditError(f"duplicate edit for {page}/{shape}/{field}")
        seen.add((page, shape, field))
        groups[page, shape].append(edit)
    return groups


def _checked_value(value, kind, key):
    if kind == "number":
        if type(value) not in {float, int} or not math.isfinite(value):
            raise AuditError(f"{key} requires a finite JSON number")
    elif not isinstance(value, str):
        raise AuditError(f"{key} requires a JSON string")
    return value


def _same(kind, left, right):
    if kind == "number":
        try:
            return Decimal(str(left)) == Decimal(str(right))
        except InvalidOperation:
            return False
    return left == right


def _incoming(archive, names):
    counts = Counter()
    for name in names:
        if not name.endswith(".rels"):
            continue
        folder, filename = posixpath.split(name)
        if posixpath.basename(folder) != "_rels":
            continue
        source = posixpath.join(posixpath.dirname(folder), filename[:-5])
        counts.update(rel["resolved"] for rel in _relationships(archive, source, names)
                      if rel["resolved"])
    return counts


def _open_chart(archive, record):
    if record["issues"]:
        raise AuditError(f"{record['part'] or 'chart'}: " + "; ".join(record["issues"]))
    require_content_type(archive, record["part"], "application/vnd.openxmlformats-officedocument.drawingml.chart+xml")
    root = xml_part(archive, record["part"])
    chart = read_chart(root)
    if chart.issues:
        raise AuditError("; ".join(chart.issues))
    source = record["workbook"]
    book = None
    if source["status"] == "embedded":
        require_content_type(archive, source["part"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        book = Workbook(archive.read(source["part"]))
    bindings = {}
    for ref in chart.references:
        if book is None:
            raise AuditError("chart formula has no embedded workbook")
        for idx, cell in enumerate(range_cells(ref.formula, ref.count)):
            kind, text = book.read(cell)
            key = ref.points.get(idx)
            if key is None:
                if kind is not None:
                    raise AuditError(f"workbook has an uncached point at {cell}")
                continue
            item = chart.fields[key]
            cached = item.nodes[0].text if item.kind == "number" else item.value()
            if kind != item.kind or not _same(kind, text, cached):
                raise AuditError(f"stale cache or workbook type mismatch for {key} at {cell}")
            bindings[key] = cell
    return root, chart, book, bindings


def _edit_chart(archive, record, edits):
    root, chart, book, bindings = _open_chart(archive, record)
    field_updates = {}
    cell_updates = {}
    for edit in edits:
        key = edit["field"]
        if key not in chart.fields:
            raise AuditError(f"unknown field {key!r} on {record['part']}")
        item = chart.fields[key]
        expected = _checked_value(edit["from"], item.kind, key)
        new = _checked_value(edit["to"], item.kind, key)
        if not _same(item.kind, expected, item.value()):
            raise AuditError(f"expected current value does not match {key}")
        if key in bindings:
            cell = bindings[key]
            if cell in cell_updates and not _same(item.kind, cell_updates[cell][1], new):
                raise AuditError(f"conflicting edits to one workbook cell at {cell}")
            cell_updates[cell] = item.kind, new
        elif book and key.startswith("series.") and ".label." not in key:
            raise AuditError(f"{key} is a literal with no provable source cell in the embedded workbook")
        field_updates[key] = new
    for key, cell in bindings.items():
        if cell in cell_updates:
            field_updates[key] = cell_updates[cell][1]
    changed = {}
    for key, value in field_updates.items():
        item = chart.fields[key]
        if not _same(item.kind, item.value(), value):
            replace_runs(item.nodes, str(value))
            changed[key] = value
    if not changed:
        return {}, field_updates
    parts = {record["part"]: xml_bytes(root)}
    for cell, (kind, value) in cell_updates.items():
        _, old = book.read(cell)
        if not _same(kind, old, value):
            book.set(cell, kind, str(value))
    if book and book.changed:
        parts[record["workbook"]["part"]] = book.save()
    return parts, field_updates


def _chart_lookup(inventory):
    lookup = defaultdict(list)
    for chart in inventory["charts"]:
        lookup[chart["page"], chart["shape_id"]].append(chart)
    return lookup


def apply_edits(source, plan, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or output.exists():
        raise AuditError(f"output must be a new path: {output}")
    groups = _validate_plan(plan)
    inventory = inspect_charts(source)
    if inventory["integrity_warnings"]:
        raise AuditError("source presentation has package integrity warnings")
    snapshot = source.read_bytes()
    if hashlib.sha256(snapshot).hexdigest() != inventory["source_sha256"]:
        raise AuditError("source changed during inspection")
    lookup = _chart_lookup(inventory)
    occurrences = Counter(chart["part"] for chart in inventory["charts"])
    expected = {}
    changes = {}
    temporary = None
    try:
        with zipfile.ZipFile(io.BytesIO(snapshot)) as archive:
            incoming = _incoming(archive, checked_zip(archive))
            for location, edits in groups.items():
                records = lookup.get(location, [])
                if len(records) != 1:
                    raise AuditError(f"unknown or ambiguous chart at page/shape {location}")
                record = records[0]
                part = record["part"]
                if part and (incoming[part] != 1 or occurrences[part] != 1):
                    raise AuditError(f"shared chart part cannot be edited in isolation: {part}")
                workbook = record["workbook"].get("part")
                if workbook and incoming[workbook] != 1:
                    raise AuditError(f"shared embedded workbook cannot be edited in isolation: {workbook}")
                parts, fields = _edit_chart(archive, record, edits)
                changes.update(parts)
                expected[location] = fields
            with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".pptx", delete=False) as handle:
                temporary = Path(handle.name)
                copy_archive(archive, handle, changes)

        # Re-open the exact bytes that will be published, resolve slides/rIds
        # again, then reconcile every involved range against the embedded XLSX.
        result = inspect_charts(temporary)
        output_lookup = _chart_lookup(result)
        if result["integrity_warnings"]:
            raise AuditError("output has package integrity warnings")
        with zipfile.ZipFile(temporary) as candidate:
            for location, fields in expected.items():
                records = output_lookup.get(location, [])
                if len(records) != 1:
                    raise AuditError(f"changed chart no longer resolves at {location}")
                _, chart, _, _ = _open_chart(candidate, records[0])
                for key, value in fields.items():
                    item = chart.fields.get(key)
                    if item is None or not _same(item.kind, item.value(), value):
                        raise AuditError(f"re-opened output differs at {location}/{key}")
        # Atomic, exclusive publication: an output that appeared meanwhile survives.
        os.link(temporary, output)
    finally:
        if temporary:
            try:
                temporary.unlink()
            except OSError:
                pass
    return {"output": str(output), "sha256": result["source_sha256"],
            "changed_parts": sorted(changes), "verified": True}


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AuditError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="inventory charts and their cached fields as JSON")
    inspect.add_argument("source", type=Path)
    apply = commands.add_parser("apply", help="apply the reviewed JSON patch to a new PPTX")
    apply.add_argument("source", type=Path)
    apply.add_argument("edits", type=Path)
    apply.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            result = inspect_charts(args.source)
        else:
            plan = json.loads(args.edits.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_keys)
            result = apply_edits(args.source, plan, args.output)
        print(json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False))
    except (AuditError, OSError, ValueError, OverflowError, KeyError, zipfile.BadZipFile,
            etree.XMLSyntaxError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
