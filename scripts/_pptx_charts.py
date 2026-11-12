"""Read the native chart objects referenced by slide graphic frames.

The read-only manifest uses ElementTree. The editor uses the same field reader
on lxml elements to preserve original namespace declarations when writing XML.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field

from _pptx_common import NS, _relationships, _root_for, q


def _local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _number(text):
    if re.fullmatch(r"[+-]?\d+", text):
        return int(text)
    number = float(text)
    if not math.isfinite(number):
        raise ValueError("non-finite number")
    return number


def _external_formula(formula):
    # A workbook qualifier is illegal in an internal worksheet name.
    return "[" in formula or "]" in formula or "://" in formula or "\\" in formula


def _calendar_format(code):
    # Quoted/escaped literals and colour, condition or locale brackets are
    # display decorations. A standalone Excel date/time token carries meaning.
    tokens = re.sub(r'"[^"]*"|\\.|_.|\*.|\[(?![hms]+\])[^\]]*\]', "", code, flags=re.I)
    return bool(re.search(r"(?<![A-Za-z])[ymdhs]+(?![A-Za-z])", tokens, re.I))


@dataclass
class ChartField:
    kind: str
    nodes: list[ET.Element]
    formula: str = ""
    storage: str = "literal"
    date_category: bool = False

    def value(self):
        text = "".join(node.text or "" for node in self.nodes)
        return _number(text) if self.kind == "number" else text

    def describe(self):
        info = {"kind": self.kind, "value": self.value(), "storage": self.storage}
        if self.formula:
            info["formula"] = "(external reference)" if _external_formula(self.formula) else self.formula
        if self.date_category:
            info["date_category"] = True
        return info


@dataclass
class Reference:
    formula: str
    count: int
    points: dict[int, str]


@dataclass
class Chart:
    types: list[str] = field(default_factory=list)
    fields: dict[str, ChartField] = field(default_factory=dict)
    references: list[Reference] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    inspection_issues: list[str] = field(default_factory=list)

    def incomplete(self, message):
        self.issues.append(message)
        self.inspection_issues.append(message)

    def add(self, key, kind, nodes, formula="", storage="literal"):
        item = ChartField(kind, nodes, formula, storage)
        try:
            item.value()
        except (ValueError, OverflowError):
            self.issues.append(f"{key}: invalid {kind} cache value")
            return
        if key in self.fields:
            self.incomplete(f"ambiguous chart field: {key}")
            return
        self.fields[key] = item


def read_chart(root, *, text_only=False):
    chart = Chart()
    seen_formulas = set()

    def read_text_or_data(container, key, scalar=False):
        if container is None:
            return
        sources = [child for child in container if _local(child.tag) in {
            "v", "rich", "strRef", "strLit", "numRef", "numLit", "multiLvlStrRef",
        }]
        if len(sources) != 1:
            chart.incomplete(f"{key}: missing or ambiguous text/data source")
            return
        source = sources[0]
        typ = _local(source.tag)
        if typ == "v":
            chart.add(key, "string", [source])
            return
        if typ == "rich":
            for i, paragraph in enumerate(source.findall("a:p", NS), 1):
                paragraph_key = key if i == 1 else f"{key}.p{i}"
                # A hard break keeps its logical position as a separate field.
                groups = [[]]
                for child in paragraph:
                    if child.tag == q("a", "br"):
                        groups.append([])
                    elif child.tag in {q("a", "r"), q("a", "fld")}:
                        groups[-1].extend(child.findall("a:t", NS))
                        if child.tag == q("a", "fld"):
                            chart.issues.append(f"{key}: dynamic rich-text field")
                for j, nodes in enumerate(groups, 1):
                    if nodes:
                        name = paragraph_key if j == 1 else f"{paragraph_key}.line{j}"
                        chart.add(name, "string", nodes, storage="rich")
            return

        formula = ""
        cache = source
        if typ.endswith("Ref"):
            formulas = source.findall("c:f", NS)
            seen_formulas.update(formulas)
            if len(formulas) != 1 or not formulas[0].text:
                chart.incomplete(f"{key}: missing or ambiguous chart formula")
                return
            formula = formulas[0].text
            if _external_formula(formula):
                chart.issues.append(f"{key}: external workbook formula")
            cache_tag = {"strRef": "strCache", "numRef": "numCache",
                         "multiLvlStrRef": "multiLvlStrCache"}[typ]
            caches = source.findall(f"c:{cache_tag}", NS)
            if len(caches) != 1:
                chart.incomplete(f"{key}: missing or ambiguous {cache_tag}")
                return
            cache = caches[0]
        if typ == "multiLvlStrRef":
            chart.issues.append(f"{key}: multi-level categories are read-only")
            for level, group in enumerate(cache.findall("c:lvl", NS)):
                for point in group.findall("c:pt", NS):
                    nodes = point.findall("c:v", NS)
                    if nodes:
                        chart.add(f"{key}.level{level}.{point.get('idx')}", "string",
                                  nodes, formula, "cache")
            return
        kind = "number" if typ.startswith("num") else "string"
        counts = cache.findall("c:ptCount", NS)
        count_node = counts[0] if len(counts) == 1 else None
        raw_count = count_node.get("val", "") if count_node is not None else ""
        count = int(raw_count) if re.fullmatch(r"\d{1,7}", raw_count) else -1
        if count < 0 or (scalar and count != 1):
            chart.issues.append(f"{key}: invalid cache point count")
        indexed = {}
        for point in cache.findall("c:pt", NS):
            raw_index = point.get("idx", "")
            idx = int(raw_index) if re.fullmatch(r"\d{1,7}", raw_index) else -1
            nodes = point.findall("c:v", NS)
            if not 0 <= idx < count or idx in indexed or len(nodes) != 1:
                chart.incomplete(f"{key}: invalid or duplicate cache point {raw_index!r}")
                continue
            name = key if scalar else f"{key}.{idx}"
            chart.add(name, kind, nodes, formula, "cache" if formula else "literal")
            indexed[idx] = name
        if formula:
            chart.references.append(Reference(formula, count, indexed))

    def read_one(parent, path, key, scalar=False):
        nodes = parent.findall(path, NS)
        if len(nodes) > 1:
            chart.incomplete(f"multiple chart sources for {key}")
        for node in nodes:
            read_text_or_data(node, key, scalar)

    def read_labels(parent, prefix):
        for label in parent.findall("c:dLbls/c:dLbl", NS):
            index = label.find("c:idx", NS)
            idx = index.get("val", "") if index is not None else ""
            if not re.fullmatch(r"\d+", idx):
                chart.incomplete(f"{prefix}: data label lacks a valid point index")
            read_one(label, "c:tx", f"{prefix}.label.{idx}", scalar=True)

    if root.tag != q("c", "chartSpace"):
        chart.incomplete("unsupported chart part root")
        return chart
    read_one(root, "c:chart/c:title/c:tx", "title", scalar=True)
    plot = root.find("c:chart/c:plotArea", NS)
    if plot is None:
        chart.incomplete("chart has no plot area")
        return chart
    calendar_axes = set()
    date_series = set()
    for axis in list(plot.findall("c:dateAx", NS)) + list(plot.findall("c:catAx", NS)):
        style = axis.find("c:numFmt", NS)
        if axis.tag == q("c", "dateAx") or (style is not None and _calendar_format(style.get("formatCode", ""))):
            axis_id = axis.find("c:axId", NS)
            calendar_axes.add(axis_id.get("val", "") if axis_id is not None else "")
    for element in plot:
        tag = _local(element.tag)
        if tag in {"catAx", "valAx", "dateAx", "serAx"}:
            ax_id = element.find("c:axId", NS)
            title = element.find("c:title/c:tx", NS)
            if title is not None:
                axis = ax_id.get("val", "") if ax_id is not None else ""
                if not axis:
                    chart.issues.append("axis title lacks an axis ID")
                read_one(element, "c:title/c:tx", f"axis.{axis}.title", scalar=True)
            continue
        if not tag.endswith("Chart"):
            continue
        chart_type = tag[:-5]
        if tag == "barChart":
            direction = element.find("c:barDir", NS)
            val = direction.get("val") if direction is not None else None
            chart_type = {"bar": "bar", "col": "column"}.get(val, "unknown-bar-direction")
        chart.types.append(chart_type)
        plot_axes = {node.get("val", "") for node in element.findall("c:axId", NS)}
        date_axis = bool(calendar_axes and (not plot_axes or "" in calendar_axes or plot_axes & calendar_axes))
        read_labels(element, "plot")
        for series in element.findall("c:ser", NS):
            idx_node = series.find("c:idx", NS)
            idx = idx_node.get("val", "") if idx_node is not None else ""
            if not re.fullmatch(r"\d+", idx):
                chart.issues.append("series lacks a valid series index")
            prefix = f"series.{idx}."
            read_labels(series, prefix[:-1])
            for child, role in (("tx", "name"), ("cat", "category"), ("val", "value"),
                                ("xVal", "x"), ("yVal", "y")):
                read_one(series, f"c:{child}", prefix + role, child == "tx")
            categories = series.find("c:cat", NS)
            if categories is not None and (date_axis or any(
                    _calendar_format(node.text or "") for node in categories.iter(q("c", "formatCode")))):
                date_series.add(idx)
    if date_series:
        for key, item in chart.fields.items():
            parts = key.split(".", 3)
            if len(parts) == 4 and parts[0] == "series" and parts[1] in date_series and parts[2] == "category":
                item.date_category = True
    supported = {"bar", "column", "line", "scatter"}
    if text_only:
        supported.update({"pie", "doughnut"})
    if len(chart.types) != 1 or chart.types[0] not in supported:
        chart.issues.append("text translation supports one column, bar, line, scatter, pie, or doughnut plot"
                            if text_only else "editing supports one column, bar, line, or scatter plot")
    if any(_local(node.tag) == "f" and node not in seen_formulas for node in root.iter()):
        chart.issues.append("chart contains a source formula outside the supported fields")
    if root.find("c:pivotSource", NS) is not None:
        chart.issues.append("pivot chart sources are read-only")
    return chart


def _source_relationship(relationships, rid, names, suffixes):
    matches = [rel for rel in relationships if rel["id"] == rid]
    if not rid or len(matches) != 1:
        return {"status": "unresolved"}
    rel = matches[0]
    if rel["target_mode"].lower() == "external":
        # Do not open, or include potentially credentialed external URLs in reports.
        return {"status": "external"}
    if (rel["target_mode"].lower() not in {"", "internal"}
            or not rel["type"].endswith(suffixes) or rel["resolved"] not in names):
        return {"status": "unresolved"}
    return {"status": "internal", "part": rel["resolved"]}


def slide_charts(zf, slide_part, slide_root, names, roots, *, text_only=False):
    """Resolve only chart objects actually referenced by this slide, including groups."""
    records = []
    shape_ids = Counter(p.get("id", "") for p in slide_root.iter(q("p", "cNvPr")))
    for frame in slide_root.findall(".//p:graphicFrame", NS):
        data = frame.find("a:graphic/a:graphicData", NS)
        if data is None:
            continue
        objects = list(data.findall("c:chart", NS)) + list(data.findall("cx:chart", NS))
        for obj in objects:
            props = frame.find("p:nvGraphicFramePr/p:cNvPr", NS)
            shape_id = props.get("id", "") if props is not None else ""
            name = props.get("name", "") if props is not None else ""
            rid = obj.get(q("r", "id"), "")
            link = _source_relationship(_relationships(zf, slide_part, names, roots),
                                        rid, names, ("/chart", "/chartEx"))
            record = {"shape_id": shape_id, "name": name, "relationship_id": rid,
                      "part": link.get("part", ""), "types": [], "fields": {},
                      "workbook": {"status": "none"}, "issues": [], "inspection_issues": []}
            records.append(record)
            if link["status"] != "internal" or obj.tag == q("cx", "chart"):
                message = ("extended chart source requires separate inspection" if obj.tag == q("cx", "chart")
                           else f"{link['status']} chart relationship")
                record["issues"].append(message)
                record["inspection_issues"].append(message)
                if link["status"] == "external":
                    record["workbook"] = {"status": "external"}
                continue
            root = _root_for(zf, link["part"], roots)
            chart = read_chart(root, text_only=text_only)
            record.update(types=chart.types, issues=chart.issues, inspection_issues=chart.inspection_issues,
                          fields={key: item.describe() for key, item in chart.fields.items()})
            if not shape_id or shape_ids[shape_id] != 1 or len(objects) != 1:
                chart.incomplete("missing or ambiguous chart frame identity")
            links = root.findall("c:externalData", NS)
            rels = _relationships(zf, link["part"], names, roots)
            if len(links) == 1:
                source = _source_relationship(rels, links[0].get(q("r", "id"), ""),
                                              names, ("/package",))
                if source["status"] == "internal":
                    source["status"] = "embedded" if source["part"].lower().endswith(".xlsx") else "unsupported"
                record["workbook"] = source
            elif links or any(rel["type"].endswith(("/package", "/oleObject")) for rel in rels):
                record["workbook"] = {"status": "unresolved"}
            status = record["workbook"]["status"]
            if status not in {"none", "embedded"} or (chart.references and status == "none"):
                record["issues"].append(f"no editable embedded workbook for chart source ({status})")
    return records
