"""Real editable PPTX charts, embedded XLSX sources and atomic failure cases."""

import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import xlsxwriter
from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData, XyChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Inches

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import native_charts
from _pptx_common import AuditError, NS, q
from audit_pptx_structure import build_manifest, compare_pptx

CHART = "ppt/charts/chart1.xml"
CHART_RELS = "ppt/charts/_rels/chart1.xml.rels"
SHEET = "xl/worksheets/sheet1.xml"
BOOK = "ppt/embeddings/Microsoft_Excel_Sheet1.xlsx"


def make_deck(path, kind=XL_CHART_TYPE.COLUMN_CLUSTERED, *, preface=False, hidden=False):
    deck = Presentation()
    if preface:
        deck.slides.add_slide(deck.slide_layouts[6])
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    if hidden:
        slide._element.set("show", "0")
    if kind == XL_CHART_TYPE.XY_SCATTER:
        data = XyChartData()
        series = data.add_series("趋势")
        series.add_data_point(10, 0.5)
        series.add_data_point(20, 1.5)
    else:
        data = CategoryChartData()
        data.categories = ("东部", "西部")
        data.add_series("销售", (1.5, 2))
        data.add_series("支出", (3, 4))
    chart = slide.shapes.add_chart(kind, Inches(1), Inches(1), Inches(7), Inches(4), data).chart
    chart.has_title = True
    title = chart.chart_title.text_frame.paragraphs[0]
    title.add_run().text = "年度"
    styled = title.add_run()
    styled.text = "趋势"
    styled.font.bold = True
    if kind != XL_CHART_TYPE.PIE:
        chart.value_axis.has_title = True
        chart.value_axis.axis_title.text_frame.text = "金额"
    deck.save(path)
    return path


def members(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def zipped(parts):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return buf.getvalue()


def xml_change(data, edit):
    root = etree.fromstring(data)
    edit(root)
    return etree.tostring(root, encoding="utf-8", xml_declaration=True)


def cell_values(parts):
    """Independent reader of the observable worksheet values, including shared strings."""
    worksheet = etree.fromstring(parts[SHEET])
    sst = (etree.fromstring(parts["xl/sharedStrings.xml"])
           if "xl/sharedStrings.xml" in parts else None)
    table = ([] if sst is None else
             ["".join(si.itertext()) for si in sst.findall("x:si", NS)])
    values = {}
    for cell in worksheet.findall("x:sheetData/x:row/x:c", NS):
        value = cell.findtext("x:v", namespaces=NS)
        typ = cell.get("t", "n")
        if typ == "s":
            value = table[int(value)]
        elif typ == "inlineStr":
            value = "".join(cell.find("x:is", NS).itertext())
        elif typ == "n":
            value = float(value)
        values[cell.get("r")] = value
    return values


def edit(field, before, after, *, page=1, shape="2"):
    return {"page": page, "shape_id": shape, "field": field, "from": before, "to": after}


class NativeChartTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native-chart-")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.src = make_deck(self.work / "source.pptx")
        self.out = self.work / "out.pptx"

    def rewrite(self, part, operation, embedded=False):
        parts = members(self.src.read_bytes())
        inside = members(parts[BOOK]) if embedded else parts
        inside[part] = xml_change(inside[part], operation)
        if embedded:
            parts[BOOK] = zipped(inside)
        self.src.write_bytes(zipped(parts))

    def apply(self, *changes):
        return native_charts.apply_edits(self.src, {"edits": list(changes)}, self.out)

    def record(self, path):
        return native_charts.inspect_charts(path)["charts"][0]

    def rejected(self, *changes, match=None):
        source = self.src.read_bytes()
        if match:
            with self.assertRaisesRegex(AuditError, match):
                self.apply(*changes)
        else:
            with self.assertRaises(AuditError):
                self.apply(*changes)
        self.assertEqual(self.src.read_bytes(), source)
        self.assertFalse(self.out.exists())

    def test_inventory_is_scoped_to_physical_slide_and_named_fields(self):
        make_deck(self.src, preface=True, hidden=True)
        before = self.src.read_bytes()
        c = self.record(self.src)
        self.assertEqual((c["page"], c["hidden"], c["shape_id"], c["types"]),
                         (2, True, "2", ["column"]))
        self.assertEqual(c["workbook"], {"status": "embedded", "part": BOOK})
        self.assertEqual(c["fields"]["title"]["value"], "年度趋势")
        self.assertEqual(c["fields"]["series.0.name"]["formula"], "Sheet1!$B$1")
        self.assertEqual(c["fields"]["series.0.value.0"]["kind"], "number")
        self.assertEqual(c["issues"], [])
        self.assertEqual(build_manifest(self.src)["slides"][1]["text_box_count"], 0)
        self.assertEqual(self.src.read_bytes(), before)

    def test_content_and_embedded_source_reopen_without_package_churn(self):
        axis = next(key for key in self.record(self.src)["fields"] if key.startswith("axis."))
        baseline = members(self.src.read_bytes())
        result = self.apply(edit("title", "年度趋势", "Annual trend"),
                            edit(axis, "金额", "Amount"),
                            edit("series.0.name", "销售", "Sales"),
                            edit("series.1.category.0", "东部", "East"),
                            edit("series.0.value.0", 1.5, -3.125))
        final = members(self.out.read_bytes())
        self.assertTrue(result["verified"])
        self.assertEqual(baseline.keys(), final.keys())
        self.assertEqual({p for p in final if final[p] != baseline[p]}, {BOOK, CHART})
        values = cell_values(members(final[BOOK]))
        self.assertEqual((values["B1"], values["A2"], values["B2"]), ("Sales", "East", -3.125))
        ppt_chart = Presentation(self.out).slides[0].shapes[0].chart
        self.assertEqual(ppt_chart.chart_title.text_frame.text, "Annual trend")
        self.assertTrue(ppt_chart.chart_title.text_frame.paragraphs[0].runs[1].font.bold)
        self.assertEqual(ppt_chart.value_axis.axis_title.text_frame.text, "Amount")
        self.assertEqual(ppt_chart.series[0].values, (-3.125, 2.0))
        self.assertEqual(ppt_chart.series[0].name, "Sales")
        fields = self.record(self.out)["fields"]
        for n in range(2):
            self.assertEqual(fields[f"series.{n}.category.0"]["value"], "East")
        self.assertEqual(members(self.src.read_bytes()), baseline)

    def test_formula_titles_horizontal_quoted_ranges_and_inline_strings(self):
        def convert_chart(root):
            title = root.find("c:chart/c:title/c:tx", NS)
            name = root.find(".//c:ser/c:tx/c:strRef", NS)
            title.replace(title[0], copy.deepcopy(name))
            for node in root.iter(q("c", "f")):
                node.text = node.text.replace("Sheet1!", "'O''Brien data'!")
            for node in root.findall(".//c:ser/c:cat/c:strRef/c:f", NS):
                node.text = "'O''Brien data'!$A$4:$B$4"
        self.rewrite(CHART, convert_chart)
        self.rewrite("xl/workbook.xml",
                     lambda r: r.find("x:sheets/x:sheet", NS).set("name", "O'Brien data"), True)

        def add_inline_row(root):
            row = etree.SubElement(root.find("x:sheetData", NS), q("x", "row"), r="4")
            for address, value in (("A4", "东部"), ("B4", "西部")):
                cell = etree.SubElement(row, q("x", "c"), r=address, t="inlineStr")
                s = etree.SubElement(cell, q("x", "is"))
                etree.SubElement(s, q("x", "t")).text = value
        self.rewrite(SHEET, add_inline_row, True)
        self.apply(edit("title", "销售", "Sales"), edit("series.1.category.1", "西部", "West"))
        final = members(self.out.read_bytes())
        values = cell_values(members(final[BOOK]))
        self.assertEqual((values["B1"], values["B4"], values["A3"]), ("Sales", "West", "西部"))
        fields = self.record(self.out)["fields"]
        self.assertEqual(fields["title"]["value"], fields["series.0.name"]["value"])
        self.assertEqual(fields["series.0.category.1"]["value"], "West")

    def test_table_series_headers_and_unrelated_shared_strings(self):
        buf = io.BytesIO()
        book = xlsxwriter.Workbook(buf, {"in_memory": True})
        sheet = book.add_worksheet()
        sheet.add_table("A1:C3", {"columns": [{"header": h} for h in ("地区", "销售", "支出")],
                                  "data": [["东部", 1.5, 3], ["西部", 2, 4]]})
        sheet.write("D4", "东部")
        book.close()
        parts = members(self.src.read_bytes())
        parts[BOOK] = buf.getvalue()
        self.src.write_bytes(zipped(parts))
        self.apply(edit("series.0.name", "销售", "Sales"), edit("series.0.category.0", "东部", "East"))
        final_book = members(members(self.out.read_bytes())[BOOK])
        cells = cell_values(final_book)
        self.assertEqual((cells["A2"], cells["D4"]), ("East", "东部"))
        table = etree.fromstring(final_book["xl/tables/table1.xml"])
        self.assertEqual([col.get("name") for col in table.findall("x:tableColumns/x:tableColumn", NS)],
                         ["地区", "Sales", "支出"])

    def test_bar_line_scatter_and_numeric_xy(self):
        for typ, name in [(XL_CHART_TYPE.BAR_CLUSTERED, "bar"), (XL_CHART_TYPE.LINE, "line"),
                          (XL_CHART_TYPE.XY_SCATTER, "scatter")]:
            with self.subTest(name):
                make_deck(self.src, typ)
                self.out = self.work / (name + ".pptx")
                self.assertEqual(self.record(self.src)["types"], [name])
                edits = ((edit("series.0.x.1", 20, 35), edit("series.0.y.0", 0.5, -2.5))
                         if name == "scatter" else (edit("series.0.value.1", 2, 8.75),))
                self.apply(*edits)
                cells = cell_values(members(members(self.out.read_bytes())[BOOK]))
                for change in edits:
                    self.assertEqual(self.record(self.out)["fields"][change["field"]]["value"], change["to"])
                    self.assertIn(change["to"], cells.values())

    def test_strict_translation_reads_native_labels_and_honors_exact_term_exceptions(self):
        self.apply(edit("series.0.name", "销售", "Sales"))
        report = compare_pptx(self.src, self.out, allow_slides={1}, target_language="en",
                              strict_translation=True)
        failures = {item.get("text_box") for item in report["translation_warnings"]}
        self.assertIn("chart:2/title", failures)
        self.assertIn("chart:2/series.1.name", failures)
        self.assertIn("chart:2/series.0.category.0", failures)
        self.assertNotIn("chart:2/series.0.name", failures)
        self.assertNotIn("chart:2/series.0.value.0", failures)
        zh = compare_pptx(self.out, self.out, target_language="zh", strict_translation=True)
        self.assertFalse(zh["ok"])
        rule = {"id": "reviewed-term", "target_page": 1,
                "key": "chart:2/series.0.name", "text": "Sales"}
        accepted = compare_pptx(self.out, self.out, strict_translation=True, target_language="zh",
                                translation_exceptions={"allow_chart_terms": [rule]})
        self.assertTrue(accepted["ok"], accepted["violations"])
        bad_page = compare_pptx(self.out, self.out, strict_translation=True, target_language="zh",
                                translation_exceptions={"allow_chart_terms": [{**rule, "target_page": 2}]})
        self.assertFalse(bad_page["ok"])
        self.assertIn("translation-exception-unused", {w["code"] for w in bad_page["violations"]})

    def test_page_scoped_box_rules_and_explicit_mapping_cover_chart_fields(self):
        self.out.write_bytes(self.src.read_bytes())
        parts = members(self.out.read_bytes())
        slide = "ppt/slides/slide1.xml"
        parts[slide] = xml_change(parts[slide], lambda r: r.find(
            ".//p:graphicFrame/p:nvGraphicFramePr/p:cNvPr", NS).set("id", "7"))
        self.out.write_bytes(zipped(parts))
        rules = {"box_mappings": [{"source_page": 1, "source_key": "chart:2/title",
                                   "target_page": 1, "target_key": "chart:7/title"}],
                 "allow_missing": [{"source_page": 1, "key": "chart:2/*"}],
                 "allow_extra": [{"target_page": 1, "key": "chart:7/*"}]}
        strict = compare_pptx(self.src, self.out, allow_slides={1}, strict_translation=True,
                              translation_exceptions=rules)
        self.assertTrue(strict["ok"], strict["violations"])
        self.assertEqual(strict["translation_box_mappings"][0]["mapping"], "exception-explicit")

    def test_invalid_plans_stale_expectations_and_conflicting_aliases_create_nothing(self):
        for change in [edit("title", "not the title", "x"), edit("title", "年度趋势", 3),
                       edit("series.0.value.0", 1.5, True), edit("series.0.value.0", 1.5, float("nan")),
                       edit("missing", "x", "y"), edit("title", "年度趋势", "x", page=2)]:
            with self.subTest(change=change):
                self.rejected(change)
        self.rejected(edit("series.0.category.0", "东部", "A"),
                      edit("series.1.category.0", "东部", "B"), match="conflicting")
        self.out.write_bytes(b"pre-existing output")
        with self.assertRaisesRegex(AuditError, "new path"):
            self.apply(edit("title", "年度趋势", "Annual"))
        self.assertEqual(self.out.read_bytes(), b"pre-existing output")

    def test_external_source_is_identified_and_never_dereferenced(self):
        def external(root):
            root[0].set("TargetMode", "External")
            root[0].set("Target", "https://example.invalid/workbook.xlsx")
        self.rewrite(CHART_RELS, external)
        with mock.patch("socket.socket", side_effect=AssertionError("network access")):
            self.assertEqual(self.record(self.src)["workbook"], {"status": "external"})
            self.rejected(edit("title", "年度趋势", "Annual"), match="external")

    def test_unreadable_chart_is_reported_by_strict_translation(self):
        def external(root):
            chart = next(rel for rel in root if rel.get("Type").endswith("/chart"))
            chart.set("TargetMode", "External")
            chart.set("Target", "https://example.invalid/chart.xml")
        self.rewrite("ppt/slides/_rels/slide1.xml.rels", external)
        self.assertEqual(self.record(self.src)["workbook"]["status"], "external")
        report = compare_pptx(self.src, self.src, target_language="en", strict_translation=True)
        self.assertFalse(report["ok"])
        self.assertIn("translation-chart-uninspected", {w["code"] for w in report["violations"]})

    def test_real_custom_data_label_and_literal_numeric_source(self):
        def literals(root):
            root.remove(root.find("c:externalData", NS))
            for series in root.findall(".//c:ser", NS):
                tx = series.find("c:tx", NS)
                value = tx.findtext("c:strRef/c:strCache/c:pt/c:v", namespaces=NS)
                tx.remove(tx[0])
                etree.SubElement(tx, q("c", "v")).text = value
                for role, typ in (("cat", "str"), ("val", "num")):
                    holder = series.find(f"c:{role}", NS)
                    ref = holder[0]
                    cache = ref.find(f"c:{typ}Cache", NS)
                    cache.tag = q("c", typ + "Lit")
                    holder.replace(ref, cache)
            labels = etree.SubElement(root.find(".//c:ser", NS), q("c", "dLbls"))
            label = etree.SubElement(labels, q("c", "dLbl"))
            etree.SubElement(label, q("c", "idx"), val="0")
            label.append(copy.deepcopy(root.find("c:chart/c:title/c:tx", NS)))
        self.rewrite(CHART, literals)
        parts = members(self.src.read_bytes())
        del parts[BOOK], parts[CHART_RELS]
        self.src.write_bytes(zipped(parts))
        self.assertEqual(self.record(self.src)["workbook"]["status"], "none")
        self.apply(edit("series.0.value.1", 2, 2.75),
                   edit("series.0.label.0", "年度趋势", "Annual trend"))
        self.assertEqual(self.record(self.out)["fields"]["series.0.label.0"]["value"], "Annual trend")
        self.assertEqual(Presentation(self.out).slides[0].shapes[0].chart.series[0].values, (1.5, 2.75))
        report = compare_pptx(self.src, self.src, target_language="en", strict_translation=True)
        self.assertIn("chart:2/series.0.label.0", {w.get("text_box") for w in report["violations"]})

    def test_duplicate_frame_identity_and_wrong_package_content_type(self):
        self.rewrite("ppt/slides/slide1.xml", lambda r: r.find(
            ".//p:spTree/p:nvGrpSpPr/p:cNvPr", NS).set("id", "2"))
        self.rejected(edit("title", "年度趋势", "Annual"), match="frame identity")
        make_deck(self.src)
        def wrong(root):
            override = next(x for x in root if x.get("PartName") == "/" + CHART)
            override.set("ContentType", "application/xml")
        self.rewrite("[Content_Types].xml", wrong)
        self.rejected(edit("title", "年度趋势", "Annual"), match="content type")

    def test_stale_cache_unsupported_ranges_and_formula_cells_fail_closed(self):
        for case in ("stale", "range", "external-formula", "formula-cell", "unsupported", "missing"):
            with self.subTest(case):
                make_deck(self.src)
                if case == "stale":
                    self.rewrite(CHART, lambda r: setattr(
                        r.find(".//c:ser/c:val/c:numRef/c:numCache/c:pt/c:v", NS), "text", "99"))
                if case in {"range", "external-formula"}:
                    formula = "'[other.xlsx]Sheet1'!$B$1" if case == "external-formula" else "Sheet1!$A$1:$B$2"
                    self.rewrite(CHART, lambda r: setattr(
                        r.find(".//c:ser/c:tx/c:strRef/c:f", NS), "text", formula))
                if case == "formula-cell":
                    self.rewrite(SHEET, lambda r: etree.SubElement(
                        r.find(".//x:c[@r='B2']", NS), q("x", "f")), True)
                if case == "unsupported":
                    make_deck(self.src, XL_CHART_TYPE.PIE)
                if case == "missing":
                    parts = members(self.src.read_bytes())
                    del parts[BOOK]
                    self.src.write_bytes(zipped(parts))
                self.rejected(edit("title", "年度趋势", "Annual"))

    def test_shared_part_and_ambiguous_relationship_are_blocked(self):
        for part in (CHART_RELS, "ppt/slides/_rels/slide1.xml.rels"):
            for duplicate_id in (True, False):
                with self.subTest(part=part, duplicate_id=duplicate_id):
                    make_deck(self.src)
                    def duplicate(root):
                        rel = next(r for r in root if r.get("Type").endswith(("/package", "/chart")))
                        clone = copy.deepcopy(rel)
                        if not duplicate_id:
                            clone.set("Id", "rId99")
                        root.append(clone)
                    self.rewrite(part, duplicate)
                    self.rejected(edit("title", "年度趋势", "Annual"))

    def test_cli_json_and_concurrent_output_creation(self):
        plan = self.work / "edits.json"
        plan.write_text(json.dumps({"edits": [edit("title", "年度趋势", "Annual")]}), encoding="utf-8")
        command = [sys.executable, "-B", str(SCRIPTS / "native_charts.py")]
        inv = subprocess.run([*command, "inspect", str(self.src)], check=True, capture_output=True)
        self.assertTrue(json.loads(inv.stdout)["charts"])
        # Check that publication does not replace a destination created after staging.
        original = native_charts.os.link
        def competing_output(temporary, destination):
            Path(destination).write_bytes(b"winner")
            return original(temporary, destination)
        with mock.patch.object(native_charts.os, "link", side_effect=competing_output):
            with self.assertRaises(FileExistsError):
                self.apply(edit("title", "年度趋势", "Annual"))
        self.assertEqual(self.out.read_bytes(), b"winner")
        self.assertEqual(set(self.work.iterdir()), {self.src, self.out, plan})
        valid = self.work / "valid.pptx"
        run = subprocess.run([*command, "apply", str(self.src), str(plan), str(valid)],
                             capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(json.loads(run.stdout)["verified"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
