"""Audit chart relationships, cached points and embedded worksheet values without editing."""

from __future__ import annotations

import math
import posixpath
import re
import zipfile
from collections import defaultdict
from datetime import datetime
from functools import partial

from lxml import etree

from _chart_workbook import (Workbook, checked_zip, part_content_type, range_bounds, range_cells,
                             xml_part)
from _pptx_common import AuditError, NS, _relationships, _shown, q


CHART_TYPES = {
    q("c", "chartSpace"): "application/vnd.openxmlformats-officedocument.drawingml.chart+xml",
    q("cx", "chartSpace"): "application/vnd.ms-office.chartex+xml",
}
BOOK_TYPES = {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
              "application/vnd.ms-excel.sheet.macroEnabled.12"}
OTHER_BOOK_TYPES = {"application/vnd.ms-excel", "application/vnd.ms-excel.sheet.binary.macroEnabled.12",
                    "application/vnd.openxmlformats-officedocument.oleObject"}
CHART_REL = ("/chart", "/chartEx")
DATA_REL = ("/package", "/oleObject")
OFFICE_REL = {NS["r"], "http://purl.oclc.org/ooxml/officeDocument/relationships"}
FRAME_TYPES = {q("c", "chart"): {uri + "/chart" for uri in OFFICE_REL},
               q("cx", "chart"): {"http://schemas.microsoft.com/office/2014/relationships/chartEx"}}
DATA_TYPES = {uri + suffix for uri in OFFICE_REL for suffix in DATA_REL}
PART_ERRORS = (AuditError, OSError, KeyError, ValueError, zipfile.BadZipFile, etree.XMLSyntaxError)
ERROR_VALUES = {"#N/A", "#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#NUM!", "#NULL!",
                "#SPILL!", "#CALC!", "#GETTING_DATA"}


def _issue(items, code, detail, **location):
    items.append({"code": code, "detail": detail, **location})


def _uint(raw):
    value = (raw or "").strip()
    if not re.fullmatch(r"\+?[0-9]+", value):
        return None
    digits = value.lstrip("+0") or "0"
    return int(digits) if len(digits) <= 10 and int(digits) <= 4294967295 else None


def _inventory(archive, names, types, report):
    """Count each chart part once, including unreferenced parts and shared charts."""
    fail = partial(_issue, report["violations"])
    limit = partial(_issue, report["limitations"])
    chart_parts = {node.get("PartName", "").lstrip("/") for node in types
                   if node.get("PartName") and node.get("ContentType") in CHART_TYPES.values()}
    # Recover a normal chart filename even if its relationship and type declaration were lost.
    chart_file = re.compile(r"ppt/charts/chart(?:Ex)?[0-9]+\.xml", re.I)
    chart_parts.update(name for name in names if chart_file.fullmatch(name))
    for node in types:
        if node.get("Extension") and node.get("ContentType") in CHART_TYPES.values():
            ext = "." + node.get("Extension").lower()
            chart_parts.update(name for name in names if name.lower().endswith(ext)
                               and part_content_type(types, name) in CHART_TYPES.values())
    rels = {}
    owners = {name for name in names if name.endswith(".xml") and name.startswith((
        "ppt/slides/", "ppt/slideLayouts/", "ppt/slideMasters/", "ppt/notesSlides/",
        "ppt/notesMasters/", "ppt/handoutMasters/"))}
    for name in sorted(names):
        folder, filename = posixpath.split(name)
        if posixpath.basename(folder) != "_rels" or not filename.endswith(".rels"):
            continue
        owner = posixpath.join(posixpath.dirname(folder), filename[:-5])
        relationships = _relationships(archive, owner, names)
        rels[owner] = relationships
        if owner not in names and chart_file.fullmatch(owner):
            chart_parts.add(owner)
        for rel in relationships:
            if rel["type"].endswith(CHART_REL):
                owners.add(owner)
                if rel["resolved"] in names:
                    chart_parts.add(rel["resolved"])

    presentation = xml_part(archive, "ppt/presentation.xml", read_only=True)
    page_by_rid = {node.get(q("r", "id")): page for page, node in enumerate(
        presentation.findall("p:sldIdLst/p:sldId", NS), 1)}
    pages = {rel["resolved"]: page_by_rid[rel["id"]] for rel in rels.get("ppt/presentation.xml", [])
             if rel["type"].endswith("/slide") and rel["id"] in page_by_rid}
    owners.update(part for part in pages if part in names)
    locations = defaultdict(list)
    for owner in sorted(owners):
        if owner not in names:
            fail("missing-chart-owner", "The owner of a chart relationship is missing.", part=owner)
            continue
        root = xml_part(archive, owner, read_only=True)
        relationships = rels.get(owner, [])
        used = set()
        for data in root.iter(q("a", "graphicData")):
            for ref in data.iter(q("c", "chart"), q("cx", "chart")):
                rid = ref.get(q("r", "id"), "")
                used.add(rid)
                matches = [rel for rel in relationships if rel["id"] == rid]
                loc = {"part": owner, "relationship_id": rid}
                if owner in pages:
                    loc.update(page=pages[owner], hidden=not _shown(root.get("show")))
                frame = next(data.iterancestors(q("p", "graphicFrame")), None)
                if frame is not None:
                    props = frame.find("p:nvGraphicFramePr/p:cNvPr", NS)
                    if props is not None:
                        loc["shape_id"] = props.get("id", "")
                if not rid or len(matches) != 1 or matches[0]["type"] not in FRAME_TYPES[ref.tag]:
                    fail("broken-chart-relationship", "Chart frame has no unique matching relationship.", **loc)
                    continue
                rel = matches[0]
                if rel["target_mode"].lower() == "external" and rel["target"].strip():
                    limit("external-chart-unverified", "The chart itself is external and was not opened.", **loc)
                elif rel["target_mode"].lower() not in {"", "internal"} or rel["resolved"] not in names:
                    fail("broken-chart-relationship", "Chart frame points to an invalid or missing part.", **loc)
                else:
                    locations[rel["resolved"]].append(loc)
        for rel in relationships:
            if rel["type"].endswith(CHART_REL) and rel["id"] not in used:
                fail("orphan-chart-relationship", "No chart frame uses this chart relationship.",
                     part=owner, relationship_id=rel["id"])
    return sorted(chart_parts), locations, rels


def _workbook(archive, names, types, rels, root, books, fail, limit):
    links = list(root.iter(q("c", "externalData"), q("cx", "externalData")))
    ids = {node.get(q("r", "id"), "") for node in links}
    used = {value for node in root.iter() for key, value in node.attrib.items()
            if key.startswith("{" + NS["r"] + "}")}
    for rel in rels:
        if rel["type"].endswith(DATA_REL) and rel["id"] not in ids:
            fail("orphan-workbook-relationship", "No externalData element uses this workbook relationship.",
                 relationship_id=rel["id"])
        elif rel["target_mode"].lower() == "external" and rel["id"] not in used:
            fail("orphan-external-relationship", "The chart has an unused external relationship.",
                 relationship_id=rel["id"])
    if not links:
        return {"status": "none"}, None
    if len(links) != 1:
        fail("ambiguous-external-data", "The chart has multiple externalData elements.")
        return {"status": "unresolved"}, None
    rid = links[0].get(q("r", "id"), "")
    matches = [rel for rel in rels if rel["id"] == rid]
    if not rid or len(matches) != 1 or matches[0]["type"] not in DATA_TYPES:
        fail("broken-external-data", "externalData has no unique workbook relationship.", relationship_id=rid)
        return {"status": "unresolved"}, None
    rel = matches[0]
    mode = rel["target_mode"].lower()
    if mode == "external" and rel["target"].strip():
        limit("external-workbook-unverified", "Workbook values cannot be checked offline.", relationship_id=rid)
        return {"status": "external"}, None
    part = rel["resolved"]
    if mode not in {"", "internal"} or part not in names:
        fail("broken-external-data", "externalData points to an invalid or missing workbook.", relationship_id=rid)
        return {"status": "unresolved"}, None
    content_type = part_content_type(types, part)
    if content_type in OTHER_BOOK_TYPES:
        limit("unsupported-workbook-format", "The linked binary workbook requires separate inspection.")
        return {"status": "unsupported", "part": part}, None
    if content_type not in BOOK_TYPES:
        fail("workbook-content-type", "The workbook target has a missing, ambiguous or incorrect content type.")
        return {"status": "unresolved", "part": part}, None
    if part not in books:
        try:
            books[part] = Workbook(archive.read(part), read_only=True)
        except PART_ERRORS:
            books[part] = None
    if books[part] is None:
        fail("invalid-embedded-workbook", "The embedded workbook's package or worksheets could not be read.")
        return {"status": "unresolved", "part": part}, None
    return {"status": "embedded", "part": part}, books[part]


def _points(cache, fail):
    counts = cache.findall("c:ptCount", NS)
    count = _uint(counts[0].get("val")) if counts else None
    if len(counts) > 1 or (counts and count is None):
        fail("invalid-cache-count", "A cache declares an invalid or duplicate point count.")
    points = {}
    for point in cache.findall("c:pt", NS):
        index = _uint(point.get("idx"))
        if index is None or index in points or (count is not None and index >= count):
            fail("invalid-cache-index", "A cache point index is missing, duplicated or outside its declared count.",
                 index=point.get("idx"))
            continue
        values = point.findall("c:v", NS)
        if len(values) != 1:
            fail("invalid-cache-point", "A point must contain exactly one value.", index=index)
        points[index] = (values[0].text or "") if values else ""
    return count, points


def _numeric_equal(left, right):
    try:
        a, b = float(left), float(right)
        return math.isfinite(a) and math.isfinite(b) and math.isclose(a, b, rel_tol=1e-15, abs_tol=0)
    except (TypeError, ValueError, OverflowError):
        return False


def _excel_date(value, date1904):
    dt = datetime.fromisoformat(value)
    base = datetime(1904, 1, 1) if date1904 else datetime(1899, 12, 31)
    days = (dt - base).total_seconds() / 86400
    return days + (not date1904 and dt >= datetime(1900, 3, 1))


def _matches(kind, value, text, numeric, book, cell):
    """True/False for observed facts, None when Excel calculation or display formatting is needed."""
    if kind == "uncalculated":
        return None
    if kind is None or (kind == "string" and value == ""):
        return text in {None, ""}
    if kind == "error":
        return text == value or (numeric and text is None)
    if kind == "date":
        if not numeric:
            return None
        try:
            return _numeric_equal(_excel_date(value, book.date1904), text)
        except (TypeError, ValueError, OverflowError):
            return None
    if kind == "boolean":
        return None
    if numeric:
        if kind == "number":
            return _numeric_equal(value, text)
        if _numeric_equal(value, text):
            return True
        # Excel can skip a text cell or plot it at zero on a numeric series.
        return None if text in {None, ""} or _numeric_equal(text, "0") else False
    if kind == "number":
        if _numeric_equal(value, text):
            return True
        # A custom number/date format can change displayed text, including
        # rounding and literal words. General has no such explicit formatting.
        return False if book.general_number_format(cell) else None
    return value == text


def _audit_cache(cache, book, source, fail, limit):
    count, points = _points(cache, fail)
    numeric = cache.tag in {q("c", "numCache"), q("c", "numLit")}
    if numeric:
        for idx, text in points.items():
            if text and text not in ERROR_VALUES and not _numeric_equal(text, text):
                fail("invalid-numeric-cache-value", "Numeric cache contains an invalid numeric value.", index=idx)
    if cache.tag in {q("c", "numLit"), q("c", "strLit")}:
        return 0
    ref = cache.getparent()
    if ref.tag not in {q("c", "numRef"), q("c", "strRef")}:
        limit("unmapped-cache", "Cache has no standard chart reference to bind to a worksheet.")
        return 0
    formulas = ref.findall("c:f", NS)
    if len(formulas) != 1 or not (formulas[0].text or "").strip():
        fail("invalid-chart-formula", "The cache has no unique nonempty formula.")
        return 0
    formula = formulas[0].text.strip()
    if "#REF!" in re.sub(r"'(?:[^']|'')*'", "", formula).upper():
        fail("broken-chart-formula", "The chart formula contains a broken reference.")
        return 0
    try:
        sheet, col, row, end_col, end_row = range_bounds(formula)
    except AuditError:
        limit("unverified-chart-formula", "The formula is not a direct internal A1 range.")
        return 0
    width, height = end_col - col + 1, end_row - row + 1
    if width <= 0 or height <= 0:
        limit("unverified-chart-formula", "The formula is not a forward worksheet range.")
        return 0
    length = width * height
    if (count is not None and count != length) or any(i >= length for i in points):
        fail("cache-range-mismatch", "The cache indices or declared point count disagree with the formula range.",
             point_count=count, range_cells=length)
        return 0
    if width > 1 and height > 1:
        limit("unverified-chart-formula", "The order of a two-dimensional worksheet range is unverified.")
        return 0
    if book is None:
        if source["status"] == "none":
            limit("cache-without-workbook", "The chart has a reference cache and no workbook to compare.")
        return 0
    if sheet not in book.sheets:
        fail("missing-worksheet", "The formula references a worksheet missing from the embedded workbook.")
        return 0
    compared = 0
    limited = False
    formula_result = False
    for i, key in enumerate(range_cells(formula, length)):
        address = {"worksheet": book.sheets[sheet], "cell": key[1], "index": i}
        try:
            kind, value = book.read(key)
        except AuditError:
            fail("invalid-workbook-cell", "The stored worksheet cell cannot be read.", **address)
            continue
        cell = book.cells.get(key)
        formula_result |= cell is not None and cell.find("x:f", NS) is not None
        matches = _matches(kind, value, points.get(i), numeric, book, cell)
        if matches is None:
            limited = True
        else:
            compared += 1
            if not matches:
                fail("cache-workbook-mismatch", "Chart cache differs from the embedded worksheet cell.", **address)
    if limited:
        limit("cell-value-unverified", "Some cells require Excel formatting or calculation to compare.")
    if formula_result:
        limit("worksheet-formula-not-recalculated", "Only stored worksheet formula results were available.")
    return compared


def _audit_part(archive, names, types, rels, part, locations, books, report):
    fail = partial(_issue, report["violations"], part=part)
    limit = partial(_issue, report["limitations"], part=part)
    record = {"part": part, "locations": locations, "cache_count": 0, "compared_cells": 0}
    report["charts"].append(record)
    if part not in names:
        fail("missing-chart-part", "The declared chart part is missing.")
        return
    try:
        root = xml_part(archive, part, read_only=True)
    except PART_ERRORS:
        fail("invalid-chart-xml", "The chart XML could not be read.")
        return
    if root.tag not in CHART_TYPES:
        fail("invalid-chart-root", "The relationship or declaration points to an invalid chart part.")
        return
    if CHART_TYPES[root.tag] != part_content_type(types, part):
        fail("chart-content-type", "The chart part has a missing, ambiguous or incorrect content type.")
    if not locations:
        limit("unreferenced-chart-part", "This packaged chart has no referencing frame.")
    source, book = _workbook(archive, names, types, rels, root, books, fail, limit)
    record["workbook"] = source
    if root.tag == q("cx", "chartSpace"):
        limit("extended-chart-cache-unverified", "Extended chart dimensions require separate inspection.")
    else:
        plot = root.find("c:chart/c:plotArea", NS)
        if plot is None:
            fail("missing-chart-plot", "The chart has no plot area.")
        else:
            record["plots"] = [etree.QName(n).localname for n in plot if isinstance(n.tag, str)
                               and etree.QName(n).localname.endswith("Chart")]
    for ref_name, cache_name in (("numRef", "numCache"), ("strRef", "strCache")):
        for ref in root.iter(q("c", ref_name)):
            caches = ref.findall("c:" + cache_name, NS)
            wrong_types = {q("c", name) for name in ("numCache", "strCache", "multiLvlStrCache") if name != cache_name}
            wrong_cache = any(child.tag in wrong_types for child in ref)
            if wrong_cache:
                fail("cache-reference-type-mismatch", "The cache type does not match its chart reference.",
                     reference=root.getroottree().getpath(ref))
            if len(caches) > 1:
                fail("duplicate-chart-cache", "A chart reference contains more than one cache.",
                     reference=root.getroottree().getpath(ref))
            elif not caches and not wrong_cache:
                limit("reference-without-cache", "The optional display cache is absent.",
                      reference=root.getroottree().getpath(ref))
    if root.find(".//c:multiLvlStrRef", NS) is not None:
        limit("multi-level-cache-unverified", "Multi-level category ranges require separate inspection.")
    for cache in root.iter(*(q("c", name) for name in ("numCache", "strCache", "numLit", "strLit"))):
        where = {"cache": root.getroottree().getpath(cache)}
        record["cache_count"] += 1
        record["compared_cells"] += _audit_cache(cache, book, source, partial(fail, **where), partial(limit, **where))


def audit_charts(path):
    report = {"charts": [], "violations": [], "limitations": []}
    books = {}
    try:
        with zipfile.ZipFile(path) as archive:
            names = checked_zip(archive, read_only=True)
            types = xml_part(archive, "[Content_Types].xml")
            parts, locations, rels = _inventory(archive, names, types, report)
            for part in parts:
                _audit_part(archive, names, types, rels.get(part, []), part, locations[part], books, report)
    except PART_ERRORS as exc:
        _issue(report["violations"], "invalid-package", f"The chart inventory could not be read ({type(exc).__name__}).")
    finally:
        for book in books.values():
            if book is not None:
                book.archive.close()
    report["chart_count"] = len(report["charts"])
    report["ok"] = not report["violations"]
    if not report["ok"]:
        report["status"] = "failed"
    elif report["charts"] or report["limitations"]:
        report["status"] = "passed"
    else:
        report.update(status="skipped", reason="no-native-charts")
    return report
