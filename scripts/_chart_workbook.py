"""Edit the exact worksheet cells behind native chart caches, retaining other XLSX parts."""

from __future__ import annotations

import copy
import io
import re
import zipfile
from collections import Counter
from pathlib import PurePosixPath

from lxml import etree

from _pptx_common import AuditError, NS, _relationships, q

XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
CELL = re.compile(r"\$?([A-Za-z]{1,3})\$?([1-9]\d{0,6})")


def xml_part(archive, part):
    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
    root = etree.fromstring(archive.read(part), parser)
    if root.getroottree().docinfo.doctype:
        raise AuditError(f"unsupported DOCTYPE in {part}")
    return root


def xml_bytes(root):
    return etree.tostring(root, encoding="UTF-8", xml_declaration=True, standalone=True)


def copy_archive(source, destination, changes):
    """Preserve member order, flags/metadata where supported, comments, and opaque parts."""
    with zipfile.ZipFile(destination, "w") as target:
        target.comment = source.comment
        for info in source.infolist():
            data = changes[info.filename] if info.filename in changes else source.read(info)
            target.writestr(copy.copy(info), data)


def checked_zip(archive):
    names = archive.namelist()
    if len(set(names)) != len(names) or archive.testzip():
        raise AuditError("invalid ZIP entries or corrupt package")
    if any(name.startswith("/") or "\\" in name or ".." in PurePosixPath(name).parts
           for name in names):
        raise AuditError("invalid package member path")
    if any(name.lower().startswith("_xmlsignatures/") for name in names):
        raise AuditError("signed packages cannot be edited without invalidating the signature")
    return set(names)


def require_content_type(archive, part, expected):
    root = xml_part(archive, "[Content_Types].xml")
    namespace = "{http://schemas.openxmlformats.org/package/2006/content-types}"
    overrides = [node.get("ContentType") for node in root.findall(namespace + "Override")
                 if node.get("PartName") == "/" + part]
    defaults = [node.get("ContentType") for node in root.findall(namespace + "Default")
                if node.get("Extension", "").lower() == part.rsplit(".", 1)[-1].lower()]
    if (overrides or defaults) != [expected]:
        raise AuditError(f"missing, ambiguous or unsupported content type for {part}")


def replace_runs(nodes, text):
    """Keep run elements and their styles. Retain their original breaks where possible."""
    offset = 0
    for i, node in enumerate(nodes):
        end = len(text) if i == len(nodes) - 1 else offset + len(node.text or "")
        node.text = text[offset:end]
        if node.text and node.text != node.text.strip():
            node.set(XML_SPACE, "preserve")
        offset = end


def cell_coordinates(token):
    match = CELL.fullmatch(token)
    if not match:
        raise AuditError(f"unsupported worksheet cell address {token!r}")
    col = 0
    for char in match[1].upper():
        col = col * 26 + ord(char) - ord("A") + 1
    row = int(match[2])
    if col > 16384 or row > 1048576:
        raise AuditError(f"worksheet address outside Excel limits: {token!r}")
    return col, row


def cell_name(col, row):
    letters = ""
    while col:
        col, rem = divmod(col - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters + str(row)


def range_cells(formula, count):
    sheet_text, bang, area = formula.rpartition("!")
    if sheet_text.startswith("'"):
        if not re.fullmatch(r"'(?:[^']|'')+'", sheet_text):
            raise AuditError(f"unsupported or external chart formula: {formula!r}")
        sheet = sheet_text[1:-1].replace("''", "'")
    else:
        sheet = sheet_text
        if not re.fullmatch(r"[\w.]+", sheet):
            raise AuditError(f"unsupported or external chart formula: {formula!r}")
    if not bang or any(c in sheet for c in "[]:?*/\\"):
        raise AuditError(f"unsupported or external chart formula: {formula!r}")
    first, colon, last = area.partition(":")
    col, row = cell_coordinates(first)
    end_col, end_row = cell_coordinates(last if colon else first)
    if ((col != end_col and row != end_row) or end_col < col or end_row < row
            or (end_col - col + 1) * (end_row - row + 1) != count):
        raise AuditError(f"chart range does not match cache dimensions: {formula!r}")
    for offset in range(count):
        yield sheet.casefold(), cell_name(col + (offset if col != end_col else 0),
                                          row + (offset if row != end_row else 0))


def _target(rels, names, suffix, rid=None, optional=False):
    matches = [r for r in rels if r["type"].endswith("/" + suffix)
               and (rid is None or r["id"] == rid)]
    if not matches and optional:
        return ""
    if (len(matches) != 1 or matches[0]["target_mode"].lower() not in {"", "internal"}
            or matches[0]["resolved"] not in names):
        raise AuditError(f"unresolved, external, or ambiguous workbook {suffix} relationship")
    if rid and sum(r["id"] == rid for r in rels) != 1:
        raise AuditError(f"duplicate workbook relationship ID {rid!r}")
    return matches[0]["resolved"]


def _string_nodes(entry):
    nodes = entry.findall("x:t", NS) + entry.findall("x:r/x:t", NS)
    if not nodes or entry.find("x:rPh", NS) is not None:
        raise AuditError("unsupported embedded workbook rich string")
    return nodes


class Workbook:
    def __init__(self, data):
        self.archive = zipfile.ZipFile(io.BytesIO(data))
        names = checked_zip(self.archive)
        self.trees = {}
        self.changed = set()
        self.sheets = {}
        self.cells = {}
        self.tables = {}
        self.headers = {}
        self.string_uses = Counter()

        # Sources with additional caches or calculations cannot be updated by
        # changing just the chart worksheet cells.
        unsupported = ("xl/externallinks/", "xl/pivot", "xl/charts/", "xl/querytables/",
                       "xl/slicercaches/", "xl/connections.xml", "xl/calcchain.xml", "xl/vbaproject")
        if any(name.lower().startswith(unsupported) for name in names):
            raise AuditError("embedded workbook contains external, calculated, or dependent data")
        part = _target(_relationships(self.archive, "", names), names, "officeDocument")
        require_content_type(self.archive, part, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml")
        book = self.tree(part)
        if book.tag != q("x", "workbook") or book.find("x:externalReferences", NS) is not None:
            raise AuditError("unsupported or externally linked embedded workbook")
        rels = _relationships(self.archive, part, names)
        self.sst = _target(rels, names, "sharedStrings", optional=True)
        self.strings = self.tree(self.sst).findall("x:si", NS) if self.sst else []
        for sheet in book.findall("x:sheets/x:sheet", NS):
            key = sheet.get("name", "").casefold()
            sheet_part = _target(rels, names, "worksheet", sheet.get(q("r", "id"), ""))
            if not key or key in self.sheets or sheet_part in self.sheets.values():
                raise AuditError("missing or ambiguous worksheet identity")
            self.sheets[key] = sheet_part
            root = self.tree(sheet_part)
            if root.tag != q("x", "worksheet") or root.find(".//x:f", NS) is not None:
                raise AuditError("unsupported or formula-driven embedded worksheet")
            if root.find("x:sheetProtection", NS) is not None:
                raise AuditError("protected embedded worksheet")
            for cell in root.findall("x:sheetData/x:row/x:c", NS):
                address = cell.get("r", "")
                if not CELL.fullmatch(address) or (key, address) in self.cells:
                    raise AuditError("missing or duplicate worksheet cell address")
                self.cells[key, address] = cell
                if cell.get("t") == "s":
                    self.string_uses[self._string_index(cell)] += 1
            sheet_rels = _relationships(self.archive, sheet_part, names)
            for ref in root.findall("x:tableParts/x:tablePart", NS):
                table_part = _target(sheet_rels, names, "table", ref.get(q("r", "id"), ""))
                self._index_table(key, table_part)

    def tree(self, part):
        if part not in self.trees:
            self.trees[part] = xml_part(self.archive, part)
        return self.trees[part]

    def _index_table(self, key, part):
        table = self.tree(part)
        if (table.tag != q("x", "table") or part in self.tables
                or table.find(".//x:calculatedColumnFormula", NS) is not None
                or table.find(".//x:totalsRowFormula", NS) is not None):
            raise AuditError("unsupported calculated or shared embedded table")
        columns = table.findall("x:tableColumns/x:tableColumn", NS)
        if any(col.get("totalsRowFunction", "none") != "none" for col in columns):
            raise AuditError("calculated table totals cannot be refreshed")
        self.tables[part] = columns
        if table.get("headerRowCount", "1") == "0":
            return
        first, _, last = table.get("ref", "").partition(":")
        col, row = cell_coordinates(first)
        end_col, _ = cell_coordinates(last or first)
        if end_col - col + 1 != len(columns) or table.get("headerRowCount", "1") != "1":
            raise AuditError("ambiguous embedded table header")
        for offset, column in enumerate(columns):
            cell_key = key, cell_name(col + offset, row)
            if cell_key in self.headers:
                raise AuditError("overlapping embedded table headers")
            self.headers[cell_key] = part, column

    def _string_index(self, cell):
        value = cell.findtext("x:v", default="", namespaces=NS)
        if not re.fullmatch(r"\d+", value) or int(value) >= len(self.strings):
            raise AuditError("invalid embedded workbook shared-string index")
        return int(value)

    def read(self, key):
        if key[0] not in self.sheets:
            raise AuditError(f"chart references missing worksheet {key[0]!r}")
        cell = self.cells.get(key)
        if cell is None:
            return None, None
        typ = cell.get("t", "n")
        value = cell.find("x:v", NS)
        if typ == "n":
            return ("number", value.text) if value is not None and value.text else (None, None)
        if typ == "s":
            nodes = _string_nodes(self.strings[self._string_index(cell)])
        elif typ == "inlineStr":
            entry = cell.find("x:is", NS)
            if entry is None:
                raise AuditError(f"invalid inline workbook string at {key}")
            nodes = _string_nodes(entry)
        elif typ == "str" and value is not None:
            nodes = [value]
        else:
            raise AuditError(f"unsupported worksheet cell type {typ!r} at {key}")
        text = "".join(n.text or "" for n in nodes)
        if re.search(r"_x[0-9A-Fa-f]{4}_", text):
            raise AuditError(f"escaped SpreadsheetML string needs manual handling at {key}")
        return "string", text

    def set(self, key, kind, text):
        cell = self.cells[key]
        old_kind, old_value = self.read(key)
        if old_kind != kind:
            raise AuditError(f"workbook and chart types disagree at {key}")
        if kind == "string" and (len(text.encode("utf-16-le")) > 65534
                                 or re.search(r"_x[0-9A-Fa-f]{4}_", text)):
            raise AuditError(f"unsupported Excel string at {key}")
        if key in self.headers:
            part, column = self.headers[key]
            if kind != "string" or column.get("name") != old_value or not text.strip():
                raise AuditError(f"ambiguous or invalid embedded table header at {key}")
            column.set("name", text)
            self.changed.add(part)
        if cell.get("t") == "s":
            index = self._string_index(cell)
            if self.string_uses[index] > 1:
                # Copy the styled string before modifying one of its consumers.
                entry = copy.deepcopy(self.strings[index])
                sst = self.tree(self.sst)
                self.strings[-1].addnext(entry)
                self.string_uses[index] -= 1
                index = len(self.strings)
                self.strings.append(entry)
                self.string_uses[index] = 1
                cell.find("x:v", NS).text = str(index)
                if "uniqueCount" in sst.attrib:
                    sst.set("uniqueCount", str(len(self.strings)))
                self.changed.add(self.sheets[key[0]])
            nodes = _string_nodes(self.strings[index])
            self.changed.add(self.sst)
        elif cell.get("t") == "inlineStr":
            nodes = _string_nodes(cell.find("x:is", NS))
            self.changed.add(self.sheets[key[0]])
        else:
            nodes = [cell.find("x:v", NS)]
            self.changed.add(self.sheets[key[0]])
        replace_runs(nodes, text)

    def save(self):
        for columns in self.tables.values():
            names = [col.get("name", "").casefold() for col in columns]
            if len(names) != len(set(names)):
                raise AuditError("duplicate embedded table column names")
        target = io.BytesIO()
        changes = {part: xml_bytes(self.trees[part]) for part in self.changed}
        copy_archive(self.archive, target, changes)
        return target.getvalue()
