"""Whole-deck translation through the public CLI and an independent PPTX/XLSX readback."""

import copy
import hashlib
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

from test_native_charts import BOOK, CHART, CHART_RELS, SCRIPTS, cell_values, make_deck, members, xml_change, zipped

import native_charts
import translate_pptx
from _pptx_common import AuditError, NS, q
from audit_pptx_properties import audit_properties
from audit_pptx_structure import compare_pptx


def category_deck(path, categories, kind=XL_CHART_TYPE.LINE):
    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    data = CategoryChartData()
    data.categories = categories
    data.add_series("销量", tuple(range(1, len(categories) + 1)))
    chart = slide.shapes.add_chart(kind, Inches(1), Inches(1),
                                   Inches(6), Inches(4), data).chart
    chart.has_title = True
    chart.chart_title.text_frame.text = "销售趋势"
    deck.save(path)


class WholeDeckTranslationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.work = Path(tmp.name)
        self.src = self.work / "原稿.pptx"
        self.plan = self.work / "翻译.json"
        self.out = self.work / "翻译版.pptx"

    def invoke(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPTS / "translate_pptx.py"), *map(str, args)],
                              cwd=self.work, capture_output=True, text=True, encoding="utf-8", timeout=30)

    def extract(self):
        translate_pptx.extract(self.src, self.plan)
        return json.loads(self.plan.read_text(encoding="utf-8"))

    def test_real_mixed_deck_with_one_reviewed_plan(self):
        make_deck(self.src, preface=True, hidden=True)
        deck = Presentation(self.src)
        slide = deck.slides[0]
        group = slide.shapes.add_group_shape()
        box = group.shapes.add_textbox(Inches(1), Inches(.4), Inches(7), Inches(1))
        p = box.text_frame.paragraphs[0]
        p.add_run().text = "经营"
        link = p.add_run()
        link.text = "概览"
        link.font.bold = True
        link.hyperlink.address = "https://example.invalid/overview"
        p.add_line_break()
        p.add_run().text = "已审阅"
        box.text_frame.add_paragraph().text = "ACME"
        table = slide.shapes.add_table(1, 2, Inches(1), Inches(2), Inches(4), Inches(1)).table
        table.cell(0, 0).text = "区域"
        table.cell(0, 1).text = "2026"
        slide.notes_slide.notes_text_frame.text = "原始备注"
        deck.save(self.src)
        baseline = self.src.read_bytes()
        originals = members(baseline)

        result = self.invoke("extract", self.src, self.plan)
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        self.assertIn("经营概览", self.plan.read_text(encoding="utf-8"))
        self.assertEqual(plan["source_sha256"], hashlib.sha256(baseline).hexdigest())
        rows = {e["source"]: e for e in plan["entries"]}
        self.assertEqual(rows["东部"]["aliases"], ["series.1.category.0"])
        self.assertEqual((rows["年度趋势"]["page"], rows["年度趋势"]["hidden"]), (2, True))
        self.assertEqual(rows["经营概览"]["source_runs"], ["经营", "概览"])
        self.assertEqual(rows["区域"]["kind"], "table")
        self.assertNotIn("原始备注", rows)
        for source, target in {
            "经营概览": ["Business ", "overview"], "已审阅": "Reviewed", "区域": "Region",
            "年度趋势": ["Annual ", "trend"], "金额": "Amount", "销售": "Sales", "支出": "Expenses",
            "东部": "East", "西部": "West",
        }.items():
            rows[source]["target"] = target
        self.plan.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        applied = self.invoke("apply", self.src, self.plan, self.out)
        self.assertEqual(applied.returncode, 0, applied.stderr)
        report = json.loads(applied.stdout)
        self.assertTrue(report["verified"])
        self.assertEqual(report["sha256"], hashlib.sha256(self.out.read_bytes()).hexdigest())
        final = members(self.out.read_bytes())
        self.assertEqual(final.keys(), originals.keys())
        self.assertEqual({name for name in final if final[name] != originals[name]},
                         {"ppt/slides/slide1.xml", CHART, BOOK})
        self.assertEqual(self.src.read_bytes(), baseline)

        ppt = Presentation(self.out)
        edited_box = ppt.slides[0].shapes[0].shapes[0]
        self.assertEqual(edited_box.text, "Business overview\vReviewed\nACME")
        emphasized = edited_box.text_frame.paragraphs[0].runs[1]
        self.assertEqual(emphasized.text, "overview")
        self.assertTrue(emphasized.font.bold)
        self.assertEqual(emphasized.hyperlink.address, "https://example.invalid/overview")
        self.assertEqual([c.text for c in ppt.slides[0].shapes[1].table.iter_cells()], ["Region", "2026"])
        self.assertEqual(ppt.slides[1]._element.get("show"), "0")
        chart = ppt.slides[1].shapes[0].chart
        self.assertEqual([r.text for r in chart.chart_title.text_frame.paragraphs[0].runs], ["Annual ", "trend"])
        self.assertTrue(chart.chart_title.text_frame.paragraphs[0].runs[1].font.bold)
        self.assertEqual(chart.value_axis.axis_title.text_frame.text, "Amount")
        self.assertEqual([s.name for s in chart.series], ["Sales", "Expenses"])
        self.assertEqual([s.values for s in chart.series], [(1.5, 2), (3, 4)])
        cached = etree.fromstring(final[CHART])
        for series in cached.findall(".//c:ser", NS):
            self.assertEqual([n.text for n in series.findall("c:cat/c:strRef/c:strCache/c:pt/c:v", NS)],
                             ["East", "West"])
        self.assertEqual(cell_values(members(final[BOOK])), {
            "B1": "Sales", "C1": "Expenses", "A2": "East", "A3": "West",
            "B2": 1.5, "B3": 2, "C2": 3, "C3": 4})
        qa = compare_pptx(self.src, self.out, allow_slides="1-2", target_language="en", strict_translation=True)
        self.assertTrue(qa["ok"], qa["violations"])
        scope = self.work / "scope.json"
        scope.write_text(json.dumps({"version": 1, "rules": [
            {"id": "wording", "pages": "1", "properties": ["text"]},
            {"id": "chart", "pages": "2", "properties": ["media-data"]},
        ]}), encoding="utf-8")
        properties = audit_properties(self.src, self.out, scope_path=scope)
        self.assertTrue(properties["ok"], properties["violations"])
        self.assertEqual({c["property"] for c in properties["changes"] if c["target_page"] == 1}, {"text"})
        slide_part = "ppt/slides/slide1.xml"
        final[slide_part] = xml_change(final[slide_part], lambda root:
            root.find(".//a:tbl/a:tblGrid/a:gridCol", NS).set("w", "12345"))
        resized = self.work / "resized-table.pptx"
        resized.write_bytes(zipped(final))
        properties = audit_properties(self.src, resized, scope_path=scope)
        self.assertIn("media-data", {v.get("property") for v in properties["violations"]})

    def test_text_and_table_without_a_chart_including_strict_table_residue(self):
        deck = Presentation()
        slide = deck.slides.add_slide(deck.slide_layouts[6])
        slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1)).text = "摘要"
        slide.shapes.add_table(1, 1, Inches(1), Inches(2), Inches(3), Inches(1)).table.cell(0, 0).text = "客户"
        deck.save(self.src)
        original_bytes = self.src.read_bytes()
        plan = self.extract()
        result = translate_pptx.apply(self.src, plan, self.out)
        self.assertEqual(result["changed_parts"], [])
        self.assertEqual(self.out.read_bytes(), original_bytes)
        plan["entries"][0]["target"] = "Summary"
        partial = self.work / "partial.pptx"
        translate_pptx.apply(self.src, plan, partial)
        qa = compare_pptx(self.src, partial, allow_slides={1}, target_language="en", strict_translation=True)
        self.assertEqual([w["text_box"] for w in qa["translation_warnings"]], ["table:3/row.1.column.1"])
        legacy = self.work / "legacy-scope.json"
        legacy.write_text(json.dumps({"version": 1, "rules": [
            {"id": "table-data", "pages": "1", "properties": ["media-data"]}
        ]}), encoding="utf-8")
        plan["entries"][0]["target"] = None
        plan["entries"][1]["target"] = "Client "
        table_only = self.work / "table-only.pptx"
        translate_pptx.apply(self.src, plan, table_only)
        self.assertTrue(audit_properties(self.src, table_only, scope_path=legacy)["ok"])
        self.assertFalse(audit_properties(self.src, partial, scope_path=legacy)["ok"])

    def test_numeric_and_date_string_categories_are_absent_and_not_injectable(self):
        dates = ["2025年3月", "2025-03-02", "Jan 2026", "0020", "−12.5%", "1.7e4", "2025-Q3"]
        category_deck(self.src, [*dates, "北区", "第一季度"])
        plan = self.extract()
        categories = {e["source"]: e for e in plan["entries"] if e["kind"] == "category"}
        self.assertEqual(set(categories), {"北区", "第一季度"})
        forged = copy.deepcopy(plan)
        forged["entries"].append({**categories["北区"], "id": "slide:256/chart:2/series.0.category.0",
                                  "source": dates[0], "target": "Corrupted"})
        with self.assertRaisesRegex(AuditError, "unknown"):
            translate_pptx.apply(self.src, forged, self.out)
        self.assertFalse(self.out.exists())
        for e in plan["entries"]:
            e["target"] = {"北区": "North", "第一季度": "Q1", "销量": "Sales", "销售趋势": "Sales trend"}[e["source"]]
        translate_pptx.apply(self.src, plan, self.out)
        cells = cell_values(members(members(self.out.read_bytes())[BOOK]))
        self.assertEqual([cells[f"A{i + 2}"] for i in range(len(dates))], dates)
        qa = compare_pptx(self.src, self.out, allow_slides={1}, target_language="en", strict_translation=True)
        self.assertTrue(qa["ok"], qa["violations"])

    def test_real_date_axis_and_explicitly_formatted_category_axes(self):
        category_deck(self.src, [date(2025, 1, 1), date(2025, 2, 1)])
        base = members(self.src.read_bytes())
        self.assertIsNotNone(etree.fromstring(base[CHART]).find(".//c:dateAx", NS))
        plan = self.extract()
        self.assertFalse(any(row["kind"] == "category" for row in plan["entries"]))
        next(row for row in plan["entries"] if row["kind"] == "chart-title")["target"] = "Sales trend"
        translate_pptx.apply(self.src, plan, self.out)
        final = members(self.out.read_bytes())
        self.assertEqual(base[BOOK], final[BOOK])
        for axis_type in ("dateAx", "catAx"):
            with self.subTest(axis=axis_type):
                path = self.work / (axis_type + ".pptx")
                category_deck(path, ["上旬", "下旬"])
                parts = members(path.read_bytes())
                def configure(root):
                    axis = root.find(".//c:catAx", NS)
                    axis.tag = q("c", axis_type)
                    if axis_type == "catAx":
                        fmt = etree.SubElement(axis, q("c", "numFmt"))
                        fmt.set("formatCode", 'yyyy"年"m"月"')
                parts[CHART] = xml_change(parts[CHART], configure)
                path.write_bytes(zipped(parts))
                catalog = self.work / (axis_type + ".json")
                target = self.work / (axis_type + "-out.pptx")
                translate_pptx.extract(path, catalog)
                p = json.loads(catalog.read_text(encoding="utf-8"))
                self.assertEqual({r["kind"] for r in p["entries"]}, {"chart-title", "series-name"})
                for row in p["entries"]:
                    row["target"] = {"chart-title": "Sales trend", "series-name": "Sales"}[row["kind"]]
                translate_pptx.apply(path, p, target)
                qa = compare_pptx(path, target, allow_slides={1}, target_language="en", strict_translation=True)
                self.assertTrue(qa["ok"], qa["violations"])
                altered = self.work / (axis_type + "-altered.pptx")
                native_charts.apply_edits(target, {"edits": [
                    {"page": 1, "shape_id": "2", "field": "series.0.category.0", "from": "上旬", "to": "下旬"}
                ]}, altered)
                qa = compare_pptx(path, altered, allow_slides={1}, target_language="en", strict_translation=True)
                self.assertIn("translation-chart-category-data-changed", {w["code"] for w in qa["violations"]})

    def test_classic_pie_and_doughnut_translate_text_preserving_values(self):
        for kind in (XL_CHART_TYPE.PIE, XL_CHART_TYPE.DOUGHNUT):
            with self.subTest(kind=kind):
                src = self.work / f"{int(kind)}.pptx"
                catalog = src.with_suffix(".json")
                output = self.work / f"{int(kind)}-output.pptx"
                category_deck(src, ["直营", "合作", "2025"], kind)
                translate_pptx.extract(src, catalog)
                plan = json.loads(catalog.read_text(encoding="utf-8"))
                self.assertEqual({r["source"] for r in plan["entries"]}, {"销售趋势", "销量", "直营", "合作"})
                for row in plan["entries"]:
                    row["target"] = {"销售趋势": "Sales by channel", "销量": "Sales",
                                     "直营": "Direct", "合作": "Partner"}[row["source"]]
                translate_pptx.apply(src, plan, output)
                chart = Presentation(output).slides[0].shapes[0].chart
                self.assertEqual(chart.chart_type, kind)
                self.assertEqual(chart.chart_title.text_frame.text, "Sales by channel")
                self.assertEqual(chart.series[0].name, "Sales")
                self.assertEqual(chart.series[0].values, (1, 2, 3))
                self.assertEqual(list(chart.plots[0].categories), ["Direct", "Partner", "2025"])
                cells = cell_values(members(members(output.read_bytes())[BOOK]))
                self.assertEqual(cells, {"B1": "Sales", "A2": "Direct", "A3": "Partner",
                                         "A4": "2025", "B2": 1., "B3": 2., "B4": 3.})
                with self.assertRaisesRegex(AuditError, "editing supports"):
                    native_charts.apply_edits(src, {"edits": [
                        {"page": 1, "shape_id": "2", "field": "series.0.value.0", "from": 1, "to": 9}
                    ]}, self.out)
                self.assertFalse(self.out.exists())

    def test_stale_forged_and_competing_outputs_fail_without_clobbering(self):
        make_deck(self.src)
        plan = self.extract()
        with self.assertRaisesRegex(AuditError, "new path"):
            translate_pptx.extract(self.src, self.plan)
        with self.assertRaisesRegex(AuditError, "new path"):
            translate_pptx.apply(self.src, plan, self.src)
        for change in ("missing", "duplicate", "source", "numeric-field", "run-count"):
            with self.subTest(change=change):
                modified = copy.deepcopy(plan)
                rows = modified["entries"]
                if change == "missing":
                    rows.pop()
                elif change == "duplicate":
                    rows.append(rows[0])
                elif change == "source":
                    rows[0]["source"] = "Drift"
                elif change == "numeric-field":
                    rows[0]["id"] = "slide:256/chart:2/series.0.value.0"
                else:
                    rows[0]["target"] = ["one"]
                with self.assertRaises(AuditError):
                    translate_pptx.apply(self.src, modified, self.out)
                self.assertFalse(self.out.exists())
        real_link = translate_pptx.os.link
        def competing_link(candidate, destination):
            destination.write_bytes(b"another user's file")
            real_link(candidate, destination)
        with mock.patch.object(translate_pptx.os, "link", side_effect=competing_link):
            with self.assertRaises(FileExistsError):
                translate_pptx.apply(self.src, plan, self.out)
        self.assertEqual(self.out.read_bytes(), b"another user's file")
        make_deck(self.src, preface=True)
        second = self.work / "second.pptx"
        with self.assertRaisesRegex(AuditError, "stale"):
            translate_pptx.apply(self.src, plan, second)
        self.assertFalse(second.exists())

    def test_unresolved_external_and_stale_workbook_links_remain_intact(self):
        for case in ("external", "dangling", "literal-dangling", "stale", "formula"):
            with self.subTest(case=case):
                make_deck(self.src)
                parts = members(self.src.read_bytes())
                if case == "external":
                    def external(root):
                        root[0].set("TargetMode", "External")
                        root[0].set("Target", "https://example.invalid/book.xlsx")
                    parts[CHART_RELS] = xml_change(parts[CHART_RELS], external)
                elif case in {"dangling", "literal-dangling"}:
                    def dangling(root):
                        root.find("c:externalData", NS).set(q("r", "id"), "missing")
                        if case == "literal-dangling":
                            for series in root.findall(".//c:ser", NS):
                                tx = series.find("c:tx", NS)
                                ref = tx.find("c:strRef", NS)
                                value = ref.findtext("c:strCache/c:pt/c:v", namespaces=NS)
                                tx.remove(ref)
                                etree.SubElement(tx, q("c", "v")).text = value
                                for role, typ in (("cat", "str"), ("val", "num")):
                                    source = series.find(f"c:{role}/c:{typ}Ref", NS)
                                    cache = source.find(f"c:{typ}Cache", NS)
                                    cache.tag = q("c", typ + "Lit")
                                    source.getparent().replace(source, cache)
                    parts[CHART] = xml_change(parts[CHART], dangling)
                elif case == "stale":
                    parts[CHART] = xml_change(parts[CHART], lambda root:
                        setattr(root.find(".//c:ser/c:val/c:numRef/c:numCache/c:pt/c:v", NS), "text", "99"))
                else:
                    wb = members(parts[BOOK])
                    worksheet = "xl/worksheets/sheet1.xml"
                    wb[worksheet] = xml_change(wb[worksheet], lambda root:
                        etree.SubElement(root.find(".//x:c[@r='B2']", NS), q("x", "f")))
                    parts[BOOK] = zipped(wb)
                baseline = zipped(parts)
                self.src.write_bytes(baseline)
                with self.assertRaisesRegex(AuditError, "page 1, chart shape 2"):
                    translate_pptx.extract(self.src, self.plan)
                with self.assertRaises(AuditError):
                    translate_pptx.apply(self.src, {}, self.out)
                self.assertFalse(self.plan.exists())
                self.assertFalse(self.out.exists())
                self.assertEqual(self.src.read_bytes(), baseline)


if __name__ == "__main__":
    unittest.main()
