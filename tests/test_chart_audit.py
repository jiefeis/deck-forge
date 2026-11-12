"""Exercise native chart verification on genuine PPTX/XLSX parts, without an Office process."""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Inches

from test_native_charts import (BOOK, CHART, CHART_RELS, NS, SCRIPTS, SHEET, make_deck,
                                members, native_charts, q, xml_change, zipped)


VALUES = ".//c:ser/c:val/c:numRef/c:numCache"


class ChartAuditTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        self.path = make_deck(self.folder / "test.pptx")

    def change(self, part, operation, *, workbook=False):
        package = members(self.path.read_bytes())
        target = members(package[BOOK]) if workbook else package
        target[part] = xml_change(target[part], operation)
        if workbook:
            package[BOOK] = zipped(target)
        self.path.write_bytes(zipped(package))

    def audit(self, code=None):
        before = self.path.read_bytes()
        result = native_charts.audit_charts(self.path)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(result["ok"], code is None, result)
        if code:
            self.assertEqual(result["status"], "failed")
            self.assertIn(code, {f["code"] for f in result["violations"]}, result)
        return result

    def forge(self, folder, code):
        original = self.path.read_bytes()
        out = self.folder / folder
        run = subprocess.run([sys.executable, "-B", str(SCRIPTS / "forge.py"), "verify-pptx", str(self.path),
                              "--structural-only", "--out", str(out), "--json"], capture_output=True)
        self.assertEqual(run.returncode, code, run.stderr + run.stdout)
        report = json.loads(run.stdout)
        chart_check = next(f for f in report["checks"] if f["check"] == "native-charts")
        chart_result = json.loads((out / chart_check["evidence"]).read_text(encoding="utf-8"))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(chart_result["ok"], code == 0)
        return chart_check["status"], chart_result

    def test_no_charts_skip_public_gate(self):
        deck = Presentation()
        deck.slides.add_slide(deck.slide_layouts[6])
        deck.save(self.path)
        result = self.audit()
        self.assertEqual((result["status"], result["reason"]), ("skipped", "no-native-charts"))
        status, evidence = self.forge("noc", 0)
        self.assertEqual((status, evidence["chart_count"]), ("SKIPPED", 0))

    def test_public_gate_rejects_stale_workbook_then_accepts_correction(self):
        def b2(text):
            self.change(SHEET, lambda r: setattr(r.find(".//x:c[@r='B2']/x:v", NS), "text", text), workbook=True)
        b2("123.5")
        status, evidence = self.forge("stale", 1)
        self.assertEqual(status, "FAIL")
        self.assertTrue(any(f["code"] == "cache-workbook-mismatch" and f["cell"] == "B2"
                            for f in evidence["violations"]))
        b2("1.5000")
        status, evidence = self.forge("fixed", 0)
        self.assertEqual((status, evidence["status"]), ("PASS", "passed"))
        self.assertGreater(evidence["charts"][0]["compared_cells"], 0)

    def test_reconciles_shared_and_inline_labels_on_hidden_readonly_plot(self):
        make_deck(self.path, XL_CHART_TYPE.PIE, preface=True, hidden=True)
        clean = self.audit()
        location = clean["charts"][0]["locations"][0]
        self.assertEqual((location["page"], location["hidden"]), (2, True))
        def relabel(root):
            cell = root.find(".//x:c[@r='A2']", NS)
            cell.remove(cell.find("x:v", NS))
            cell.set("t", "inlineStr")
            etree.SubElement(etree.SubElement(cell, q("x", "is")), q("x", "t")).text = "changed label"
        self.change(SHEET, relabel, workbook=True)
        report = self.audit("cache-workbook-mismatch")
        self.assertTrue(any(f.get("cell") == "A2" for f in report["violations"]))

    def test_sparse_blank_points_and_optional_point_count(self):
        self.change(SHEET, lambda r: r.find(".//x:c[@r='B2']", NS).getparent().remove(
            r.find(".//x:c[@r='B2']", NS)), workbook=True)
        def sparse(root):
            cache = root.find(VALUES, NS)
            cache.remove(cache.find("c:pt[@idx='0']", NS))
            cache.remove(cache.find("c:ptCount", NS))
        self.change(CHART, sparse)
        self.audit()
        self.change(CHART, lambda r: r.find(VALUES, NS).remove(r.find(VALUES + "/c:pt", NS)))
        result = self.audit("cache-workbook-mismatch")
        self.assertIn("B3", [f.get("cell") for f in result["violations"]])

    def test_implicit_worksheet_coordinates_and_blank_inline_cell(self):
        def shorten_row(root):
            row = root.find(".//x:row[@r='2']", NS)
            blank = row.find("x:c[@r='B2']", NS)
            blank.remove(blank.find("x:v", NS))
            blank.set("t", "inlineStr")
            del row.attrib["r"]
            for cell in row.findall("x:c", NS):
                del cell.attrib["r"]
        self.change(SHEET, shorten_row, workbook=True)
        self.change(CHART, lambda r: r.find(VALUES, NS).remove(r.find(VALUES + "/c:pt[@idx='0']", NS)))
        self.audit()

    def test_duplicate_out_of_bounds_noninteger_and_count_disagreements(self):
        for attr, before, value, code in (
            ("idx", "c:pt[@idx='1']", "0", "invalid-cache-index"),
            ("idx", "c:pt[@idx='1']", "2", "invalid-cache-index"),
            ("idx", "c:pt[@idx='1']", "1.1", "invalid-cache-index"),
            ("val", "c:ptCount", "-1", "invalid-cache-count"),
            ("val", "c:ptCount", "3", "cache-range-mismatch"),
        ):
            with self.subTest(value=value, before=before):
                make_deck(self.path)
                self.change(CHART, lambda r: r.find(VALUES + "/" + before, NS).set(attr, value))
                self.audit(code)

    def test_cache_kind_must_match_its_parent_reference(self):
        for ref, old, new in ((VALUES, "numCache", "strCache"),
                              (".//c:ser/c:cat/c:strRef/c:strCache", "strCache", "numCache")):
            with self.subTest(old=old):
                make_deck(self.path)
                self.change(CHART, lambda r: setattr(r.find(ref, NS), "tag", q("c", new)))
                self.audit("cache-reference-type-mismatch")

    def test_numeric_text_contradiction_and_custom_display_format(self):
        def numeric_category(root):
            cell = root.find(".//x:c[@r='A2']", NS)
            cell.set("t", "n")
            cell.find("x:v", NS).text = "42"
        self.change(SHEET, numeric_category, workbook=True)
        def numeric_labels(root):
            for label in root.findall(".//c:ser/c:cat/c:strRef/c:strCache/c:pt[@idx='0']/c:v", NS):
                label.text = "42.0"
        self.change(CHART, numeric_labels)
        self.audit()
        self.change(CHART, lambda r: setattr(r.find(".//c:ser/c:cat/c:strRef/c:strCache/c:pt/c:v", NS),
                                             "text", "17"))
        self.audit("cache-workbook-mismatch")
        def percent_style(root):
            formats = root.find("x:cellXfs", NS)
            style = copy.deepcopy(formats[0])
            style.set("numFmtId", "9")
            self.percent_style = str(len(formats))
            formats.append(style)
            formats.set("count", str(len(formats)))
        self.change("xl/styles.xml", percent_style, workbook=True)
        self.change(SHEET, lambda r: r.find(".//x:c[@r='A2']", NS).set("s", self.percent_style), workbook=True)
        result = self.audit()
        self.assertIn("cell-value-unverified", {w["code"] for w in result["limitations"]})
        make_deck(self.path)
        def numeric_string(root):
            cell = root.find(".//x:c[@r='B2']", NS)
            cell.set("t", "str")
            cell.find("x:v", NS).text = "123"
        self.change(SHEET, numeric_string, workbook=True)
        self.audit("cache-workbook-mismatch")

    def test_broken_ambiguous_dangling_and_orphan_external_data(self):
        def orphan(root):
            clone = copy.deepcopy(root[0])
            clone.set("Id", "rIdObsolete")
            clone.set("TargetMode", "External")
            clone.set("Target", "https://example.invalid/private")
            root.append(clone)
        for part, edit, code in (
            (CHART, lambda r: r.find("c:externalData", NS).set(q("r", "id"), "gone"), "broken-external-data"),
            (CHART_RELS, lambda r: r[0].set("Target", "../embeddings/gone.xlsx"), "broken-external-data"),
            (CHART_RELS, lambda r: r[0].set("Type", NS["r"] + "/image"), "broken-external-data"),
            (CHART_RELS, lambda r: r.append(copy.deepcopy(r[0])), "broken-external-data"),
            (CHART, lambda r: r.remove(r.find("c:externalData", NS)), "orphan-workbook-relationship"),
            (CHART_RELS, orphan, "orphan-workbook-relationship"),
        ):
            with self.subTest(part=part, code=code):
                make_deck(self.path)
                self.change(part, edit)
                result = self.audit(code)
                self.assertNotIn("example.invalid", json.dumps(result))

    def test_live_external_source_is_offline_and_cache_structure_still_checked(self):
        def external(root):
            root[0].set("TargetMode", "External")
            root[0].set("Target", "https://example.invalid/private")
        self.change(CHART_RELS, external)
        with mock.patch("socket.socket", side_effect=AssertionError("network access")):
            limited = self.audit()
            self.assertEqual(limited["charts"][0]["workbook"]["status"], "external")
            self.assertIn("external-workbook-unverified", {f["code"] for f in limited["limitations"]})
            self.assertNotIn("example.invalid", json.dumps(limited))
            self.change(CHART, lambda r: r.find(VALUES + "/c:ptCount", NS).set("val", "3"))
            self.audit("cache-range-mismatch")

    def test_unreferenced_and_shared_parts_still_receive_cache_checks(self):
        # Two valid frames use the same chart and workbook.
        def share(root):
            frame = root.find(".//p:graphicFrame", NS)
            copy_frame = copy.deepcopy(frame)
            copy_frame.find("p:nvGraphicFramePr/p:cNvPr", NS).set("id", "17")
            frame.addnext(copy_frame)
        self.change("ppt/slides/slide1.xml", share)
        clean = self.audit()
        self.assertEqual(len(clean["charts"][0]["locations"]), 2)
        # A separate, unreachable packaged chart points to the same book with a stale cache.
        parts = members(self.path.read_bytes())
        orphan = "ppt/charts/chart77.xml"
        parts[orphan] = xml_change(parts[CHART], lambda r: setattr(r.find(VALUES + "/c:pt/c:v", NS), "text", "555"))
        parts["ppt/charts/_rels/chart77.xml.rels"] = parts[CHART_RELS]
        def declare(types):
            source = next(n for n in types if n.get("PartName") == "/" + CHART)
            clone = copy.deepcopy(source)
            clone.set("PartName", "/" + orphan)
            types.append(clone)
        parts["[Content_Types].xml"] = xml_change(parts["[Content_Types].xml"], declare)
        self.path.write_bytes(zipped(parts))
        report = self.audit("cache-workbook-mismatch")
        self.assertEqual(report["chart_count"], 2)
        self.assertIn(orphan, [v["part"] for v in report["violations"]])

    def test_frame_without_relationship_and_missing_chart_part_do_not_skip(self):
        self.change("ppt/slides/slide1.xml", lambda r: r.find(".//c:chart", NS).set(q("r", "id"), "absent"))
        self.audit("broken-chart-relationship")
        make_deck(self.path)
        parts = members(self.path.read_bytes())
        del parts[CHART]
        self.path.write_bytes(zipped(parts))
        self.audit("missing-chart-part")

    def test_extended_chart_and_strict_namespaces(self):
        # Strict OOXML changes namespace URIs while retaining the same A1 references.
        from _chart_workbook import STRICT_NAMESPACES
        def strict(parts):
            for name, data in list(parts.items()):
                if name.endswith((".xml", ".rels")):
                    for strict_uri, transitional_uri in STRICT_NAMESPACES.items():
                        data = data.replace(transitional_uri.encode(), strict_uri.encode())
                    parts[name] = data
        parts = members(self.path.read_bytes())
        book = members(parts[BOOK])
        strict(book)
        parts[BOOK] = zipped(book)
        strict(parts)
        self.path.write_bytes(zipped(parts))
        result = self.audit()
        self.assertGreater(result["charts"][0]["compared_cells"], 0)
        self.assertEqual(result["charts"][0]["locations"][0]["page"], 1)

        make_deck(self.path)
        parts = members(self.path.read_bytes())
        cx = etree.Element(q("cx", "chartSpace"), nsmap={"cx": NS["cx"], "r": NS["r"]})
        chart_data = etree.SubElement(cx, q("cx", "chartData"))
        etree.SubElement(chart_data, q("cx", "externalData")).set(q("r", "id"), "rId1")
        parts[CHART] = etree.tostring(cx)
        def convert_slide(root):
            root.find(".//c:chart", NS).tag = q("cx", "chart")
        parts["ppt/slides/slide1.xml"] = xml_change(parts["ppt/slides/slide1.xml"], convert_slide)
        def convert_link(root):
            chart = next(rel for rel in root if rel.get("Type").endswith("/chart"))
            chart.set("Type", "http://schemas.microsoft.com/office/2014/relationships/chartEx")
        rels = "ppt/slides/_rels/slide1.xml.rels"
        parts[rels] = xml_change(parts[rels], convert_link)
        def convert_type(root):
            chart = next(node for node in root if node.get("PartName") == "/" + CHART)
            chart.set("ContentType", "application/vnd.ms-office.chartex+xml")
        parts["[Content_Types].xml"] = xml_change(parts["[Content_Types].xml"], convert_type)
        self.path.write_bytes(zipped(parts))
        result = self.audit()
        self.assertIn("extended-chart-cache-unverified", [w["code"] for w in result["limitations"]])
        self.change(CHART, lambda r: r.find(".//cx:externalData", NS).set(q("r", "id"), "missing"))
        self.audit("broken-external-data")

    def test_numeric_date_categories_and_stored_formula_results(self):
        deck = Presentation()
        slide = deck.slides.add_slide(deck.slide_layouts[6])
        data = CategoryChartData()
        data.categories = (date(2025, 1, 1), date(2025, 6, 1))
        data.add_series("Sales", (1.5, 2))
        slide.shapes.add_chart(XL_CHART_TYPE.LINE, Inches(1), Inches(1), Inches(6), Inches(3), data)
        deck.save(self.path)
        self.audit()
        def calculation(root):
            cell = root.find(".//x:c[@r='B2']", NS)
            formula = etree.Element(q("x", "f"))
            formula.text = "1+0.5"
            cell.insert(0, formula)
            etree.SubElement(root, q("x", "sheetProtection"), sheet="1")
        self.change(SHEET, calculation, workbook=True)
        result = self.audit()
        self.assertIn("worksheet-formula-not-recalculated", [f["code"] for f in result["limitations"]])
        self.change(SHEET, lambda r: setattr(r.find(".//x:c[@r='A2']/x:v", NS), "text", "888"), workbook=True)
        self.audit("cache-workbook-mismatch")


if __name__ == "__main__":
    unittest.main(verbosity=2)
