#!/usr/bin/env python3
"""Synthetic regression tests for scripts/audit_pptx_typography.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "audit_pptx_typography.py"
SPEC = importlib.util.spec_from_file_location("audit_pptx_typography", SCRIPT)
AUDIT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AUDIT
SPEC.loader.exec_module(AUDIT)

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"

ET.register_namespace("p", P_NS)
ET.register_namespace("a", A_NS)
ET.register_namespace("r", R_NS)
ET.register_namespace("", REL_NS)


def q(namespace: str, tag: str) -> str:
    return f"{{{namespace}}}{tag}"


def xml_bytes(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def relationships(entries: list[tuple[str, str, str]]) -> bytes:
    root = ET.Element(q(REL_NS, "Relationships"))
    for rel_id, rel_type, target in entries:
        ET.SubElement(
            root,
            q(REL_NS, "Relationship"),
            {"Id": rel_id, "Type": rel_type, "Target": target},
        )
    return xml_bytes(root)


def add_fonts(props: ET.Element, latin: str | None, east_asia: str | None) -> None:
    if latin is not None:
        ET.SubElement(props, q(A_NS, "latin"), {"typeface": latin})
    if east_asia is not None:
        ET.SubElement(props, q(A_NS, "ea"), {"typeface": east_asia})


def make_props(
    parent: ET.Element,
    tag: str,
    *,
    latin: str | None = None,
    east_asia: str | None = None,
    size: int | None = None,
    bold: bool | None = None,
    language: str | None = None,
) -> ET.Element:
    attrs: dict[str, str] = {}
    if size is not None:
        attrs["sz"] = str(size)
    if bold is not None:
        attrs["b"] = "1" if bold else "0"
    if language is not None:
        attrs["lang"] = language
    props = ET.SubElement(parent, q(A_NS, tag), attrs)
    add_fonts(props, latin, east_asia)
    return props


def shape_tree(root: ET.Element) -> ET.Element:
    common = ET.SubElement(root, q(P_NS, "cSld"))
    tree = ET.SubElement(common, q(P_NS, "spTree"))
    nv_group = ET.SubElement(tree, q(P_NS, "nvGrpSpPr"))
    ET.SubElement(nv_group, q(P_NS, "cNvPr"), {"id": "1", "name": ""})
    ET.SubElement(nv_group, q(P_NS, "cNvGrpSpPr"))
    ET.SubElement(nv_group, q(P_NS, "nvPr"))
    ET.SubElement(tree, q(P_NS, "grpSpPr"))
    return tree


def add_shape(
    tree: ET.Element,
    *,
    shape_id: int,
    name: str,
    text: str,
    placeholder_type: str | None,
    placeholder_index: str = "",
    field_type: str | None = None,
    run_font: tuple[str | None, str | None] | None = None,
    run_size: int | None = None,
    run_bold: bool | None = None,
    run_language: str | None = None,
    default_font: tuple[str | None, str | None] | None = None,
    default_size: int | None = None,
    default_bold: bool | None = None,
    default_language: str | None = None,
) -> ET.Element:
    shape = ET.SubElement(tree, q(P_NS, "sp"))
    non_visual = ET.SubElement(shape, q(P_NS, "nvSpPr"))
    ET.SubElement(
        non_visual,
        q(P_NS, "cNvPr"),
        {"id": str(shape_id), "name": name},
    )
    ET.SubElement(non_visual, q(P_NS, "cNvSpPr"))
    nv_pr = ET.SubElement(non_visual, q(P_NS, "nvPr"))
    if placeholder_type is not None:
        attrs = {"type": placeholder_type} if placeholder_type else {}
        if placeholder_index:
            attrs["idx"] = placeholder_index
        ET.SubElement(nv_pr, q(P_NS, "ph"), attrs)
    ET.SubElement(shape, q(P_NS, "spPr"))

    text_body = ET.SubElement(shape, q(P_NS, "txBody"))
    ET.SubElement(text_body, q(A_NS, "bodyPr"))
    list_style = ET.SubElement(text_body, q(A_NS, "lstStyle"))
    if any(
        value is not None
        for value in (default_font, default_size, default_bold, default_language)
    ):
        level = ET.SubElement(list_style, q(A_NS, "lvl1pPr"))
        latin, east_asia = default_font or (None, None)
        make_props(
            level,
            "defRPr",
            latin=latin,
            east_asia=east_asia,
            size=default_size,
            bold=default_bold,
            language=default_language,
        )

    paragraph = ET.SubElement(text_body, q(A_NS, "p"))
    node = ET.SubElement(
        paragraph,
        q(A_NS, "fld" if field_type else "r"),
        {"type": field_type} if field_type else {},
    )
    if any(
        value is not None
        for value in (run_font, run_size, run_bold, run_language)
    ):
        latin, east_asia = run_font or (None, None)
        make_props(
            node,
            "rPr",
            latin=latin,
            east_asia=east_asia,
            size=run_size,
            bold=run_bold,
            language=run_language,
        )
    ET.SubElement(node, q(A_NS, "t")).text = text
    ET.SubElement(paragraph, q(A_NS, "endParaRPr"), {"lang": "en-US"})
    return shape


def add_master_style(
    tx_styles: ET.Element,
    tag: str,
    *,
    latin: str,
    east_asia: str,
    size: int,
    bold: bool,
    language: str,
) -> None:
    style = ET.SubElement(tx_styles, q(P_NS, tag))
    level = ET.SubElement(style, q(A_NS, "lvl1pPr"))
    make_props(
        level,
        "defRPr",
        latin=latin,
        east_asia=east_asia,
        size=size,
        bold=bold,
        language=language,
    )


def theme_xml(*, include_hans: bool = True) -> bytes:
    theme = ET.Element(q(A_NS, "theme"), {"name": "Synthetic Theme"})
    elements = ET.SubElement(theme, q(A_NS, "themeElements"))
    scheme = ET.SubElement(elements, q(A_NS, "fontScheme"), {"name": "Synthetic Fonts"})
    major = ET.SubElement(scheme, q(A_NS, "majorFont"))
    ET.SubElement(major, q(A_NS, "latin"), {"typeface": "Aptos Display"})
    ET.SubElement(major, q(A_NS, "ea"), {"typeface": ""})
    ET.SubElement(major, q(A_NS, "cs"), {"typeface": ""})
    if include_hans:
        ET.SubElement(
            major,
            q(A_NS, "font"),
            {"script": "Hans", "typeface": "Noto Sans CJK SC"},
        )
    minor = ET.SubElement(scheme, q(A_NS, "minorFont"))
    ET.SubElement(minor, q(A_NS, "latin"), {"typeface": "Aptos"})
    ET.SubElement(minor, q(A_NS, "ea"), {"typeface": "Microsoft YaHei"})
    ET.SubElement(minor, q(A_NS, "cs"), {"typeface": ""})
    return xml_bytes(theme)


def layout_xml() -> bytes:
    root = ET.Element(q(P_NS, "sldLayout"), {"type": "titleAndContent"})
    tree = shape_tree(root)
    add_shape(
        tree,
        shape_id=2,
        name="Title 1",
        text="Title prompt",
        placeholder_type="title",
        placeholder_index="1",
        default_font=("+mj-lt", "+mj-ea"),
        default_size=3000,
        default_bold=True,
        default_language="zh-CN",
    )
    add_shape(
        tree,
        shape_id=3,
        name="Subtitle 2",
        text="Subtitle prompt",
        placeholder_type="subTitle",
        placeholder_index="3",
    )
    add_shape(
        tree,
        shape_id=4,
        name="Content 3",
        text="Body prompt",
        placeholder_type="body",
        placeholder_index="2",
    )
    return xml_bytes(root)


def master_xml() -> bytes:
    root = ET.Element(q(P_NS, "sldMaster"))
    tree = shape_tree(root)
    add_shape(
        tree,
        shape_id=2,
        name="Master Title",
        text="Master title prompt",
        placeholder_type="title",
        placeholder_index="1",
    )
    add_shape(
        tree,
        shape_id=3,
        name="Master Subtitle",
        text="Master subtitle prompt",
        placeholder_type="subTitle",
        placeholder_index="3",
    )
    add_shape(
        tree,
        shape_id=4,
        name="Master Body",
        text="Master body prompt",
        placeholder_type="body",
        placeholder_index="2",
    )
    add_shape(
        tree,
        shape_id=5,
        name="Slide Number Placeholder",
        text="1",
        placeholder_type="sldNum",
        placeholder_index="9",
        field_type="slidenum",
        run_font=("+mn-lt", "+mn-ea"),
        run_size=900,
        run_bold=False,
        run_language="en-US",
    )
    add_shape(
        tree,
        shape_id=6,
        name="Footer Placeholder",
        text="Confidential",
        placeholder_type="ftr",
        placeholder_index="8",
        run_font=("+mn-lt", "+mn-ea"),
        run_size=800,
        run_bold=False,
        run_language="en-US",
    )
    tx_styles = ET.SubElement(root, q(P_NS, "txStyles"))
    add_master_style(
        tx_styles,
        "titleStyle",
        latin="+mj-lt",
        east_asia="+mj-ea",
        size=3200,
        bold=True,
        language="zh-CN",
    )
    add_master_style(
        tx_styles,
        "bodyStyle",
        latin="+mn-lt",
        east_asia="+mn-ea",
        size=1800,
        bold=False,
        language="en-US",
    )
    add_master_style(
        tx_styles,
        "otherStyle",
        latin="+mn-lt",
        east_asia="+mn-ea",
        size=1400,
        bold=False,
        language="en-US",
    )
    return xml_bytes(root)


def slide_xml(
    *,
    title: str,
    subtitle: str,
    body: str,
    body_font: tuple[str, str],
    body_size: int,
    body_bold: bool,
    hidden: bool,
) -> bytes:
    root = ET.Element(q(P_NS, "sld"), {"show": "0"} if hidden else {})
    tree = shape_tree(root)
    add_shape(
        tree,
        shape_id=2,
        name="Title 1",
        text=title,
        placeholder_type="title",
        placeholder_index="1",
    )
    add_shape(
        tree,
        shape_id=3,
        name="Subtitle 2",
        text=subtitle,
        placeholder_type="subTitle",
        placeholder_index="3",
    )
    add_shape(
        tree,
        shape_id=4,
        name="Content 3",
        text=body,
        placeholder_type="body",
        placeholder_index="2",
        run_font=body_font,
        run_size=body_size,
        run_bold=body_bold,
        run_language="zh-CN" if "\u6c49" in body else "en-US",
    )
    add_shape(
        tree,
        shape_id=5,
        name="Caption 4",
        text="Source caption",
        placeholder_type=None,
        run_font=("Arial", "SimSun"),
        run_size=1000,
        run_bold=False,
        run_language="en-US",
    )
    return xml_bytes(root)


def make_pptx(
    path: Path,
    *,
    inconsistent: bool = False,
    include_hans: bool = True,
    hidden_backup: bool = True,
) -> Path:
    presentation = ET.Element(q(P_NS, "presentation"))
    slide_list = ET.SubElement(presentation, q(P_NS, "sldIdLst"))
    ET.SubElement(
        slide_list,
        q(P_NS, "sldId"),
        {"id": "257", q(R_NS, "id"): "rIdSlide257"},
    )
    ET.SubElement(
        slide_list,
        q(P_NS, "sldId"),
        {"id": "256", q(R_NS, "id"): "rIdSlide256"},
    )
    ET.SubElement(
        presentation,
        q(P_NS, "sldSz"),
        {"cx": "12192000", "cy": "6858000"},
    )

    content_types = ET.Element(q(CT_NS, "Types"))
    ET.SubElement(
        content_types,
        q(CT_NS, "Default"),
        {"Extension": "xml", "ContentType": "application/xml"},
    )
    slide_two_font = ("Calibri", "Microsoft YaHei") if inconsistent else ("Arial", "SimSun")
    slide_two_size = 2000 if inconsistent else 1800
    slide_two_bold = inconsistent

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", xml_bytes(content_types))
        zf.writestr("ppt/presentation.xml", xml_bytes(presentation))
        zf.writestr(
            "ppt/_rels/presentation.xml.rels",
            relationships(
                [
                    (
                        "rIdSlide256",
                        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide",
                        "slides/slide1.xml",
                    ),
                    (
                        "rIdSlide257",
                        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide",
                        "slides/slide2.xml",
                    ),
                ]
            ),
        )
        zf.writestr(
            "ppt/slides/slide1.xml",
            slide_xml(
                title="First title",
                subtitle="First subtitle",
                body="Alpha",
                body_font=("Arial", "SimSun"),
                body_size=1800,
                body_bold=False,
                hidden=hidden_backup,
            ),
        )
        zf.writestr(
            "ppt/slides/slide2.xml",
            slide_xml(
                title="Second title",
                subtitle="Second subtitle",
                body="Beta \u6c49",
                body_font=slide_two_font,
                body_size=slide_two_size,
                body_bold=slide_two_bold,
                hidden=False,
            ),
        )
        slide_relationships = relationships(
            [
                (
                    "rIdLayout",
                    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout",
                    "../slideLayouts/slideLayout1.xml",
                )
            ]
        )
        zf.writestr("ppt/slides/_rels/slide1.xml.rels", slide_relationships)
        zf.writestr("ppt/slides/_rels/slide2.xml.rels", slide_relationships)
        zf.writestr("ppt/slideLayouts/slideLayout1.xml", layout_xml())
        zf.writestr(
            "ppt/slideLayouts/_rels/slideLayout1.xml.rels",
            relationships(
                [
                    (
                        "rIdMaster",
                        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster",
                        "../slideMasters/slideMaster1.xml",
                    )
                ]
            ),
        )
        zf.writestr("ppt/slideMasters/slideMaster1.xml", master_xml())
        zf.writestr(
            "ppt/slideMasters/_rels/slideMaster1.xml.rels",
            relationships(
                [
                    (
                        "rIdTheme",
                        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme",
                        "../theme/theme1.xml",
                    )
                ]
            ),
        )
        zf.writestr("ppt/theme/theme1.xml", theme_xml(include_hans=include_hans))
    return path


def role_runs(report: dict[str, object], role: str) -> list[dict[str, object]]:
    return [
        run
        for slide in report["slides"]
        for run in slide["runs"]
        if run["role"] == role
    ]


def failure_codes(report: dict[str, object]) -> set[str]:
    return {item["code"] for item in report["validation"]["failures"]}


class AuditPptxTypographyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="audit-pptx-typography-")
        self.tmp = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_true_order_hidden_page_and_inheritance_sources(self) -> None:
        pptx = make_pptx(self.tmp / "deck.pptx")

        report = AUDIT.audit_pptx(pptx)

        self.assertEqual([slide["slide_id"] for slide in report["slides"]], [257, 256])
        self.assertEqual([slide["hidden"] for slide in report["slides"]], [False, True])
        self.assertEqual(report["summary"]["hidden"], 1)
        self.assertEqual(report["summary"]["audited_slides"], 1)
        self.assertEqual(report["scope"]["policy"], "all-visible")
        self.assertEqual(report["scope"]["audited_pages"], [1])
        self.assertEqual(report["scope"]["excluded_hidden_pages"], [2])
        self.assertEqual(
            [slide["in_scope"] for slide in report["slides"]], [True, False]
        )
        self.assertEqual(report["status"], "report")
        self.assertTrue(report["ok"])

        page_one_title = role_runs(report, "title")[0]
        self.assertEqual(page_one_title["text"], "Second title")
        self.assertEqual(page_one_title["font"]["latin"]["value"], "Aptos Display")
        self.assertEqual(page_one_title["font"]["latin"]["raw"], "+mj-lt")
        self.assertEqual(page_one_title["font"]["latin"]["theme_reference"], "+mj-lt")
        self.assertEqual(page_one_title["font"]["latin"]["source_level"], "layout")
        self.assertTrue(page_one_title["font"]["latin"]["inherited"])
        self.assertEqual(page_one_title["font"]["eastAsia"]["value"], "Noto Sans CJK SC")
        self.assertEqual(page_one_title["font"]["eastAsia"]["theme_script"], "Hans")
        self.assertEqual(page_one_title["size"]["value"], 3000)
        self.assertTrue(page_one_title["bold"]["value"])
        self.assertTrue(
            any(item["source_level"] == "master" for item in page_one_title["size"]["chain"])
        )

        page_one_subtitle = role_runs(report, "subtitle")[0]
        self.assertEqual(page_one_subtitle["font"]["latin"]["source_level"], "master")
        self.assertEqual(page_one_subtitle["font"]["latin"]["value"], "Aptos")
        self.assertEqual(page_one_subtitle["size"]["value"], 1400)

        page_one_body = role_runs(report, "body")[0]
        self.assertEqual(page_one_body["font"]["latin"]["value"], "Arial")
        self.assertEqual(page_one_body["font"]["eastAsia"]["value"], "SimSun")
        self.assertEqual(page_one_body["font"]["latin"]["source_level"], "slide")
        self.assertTrue(page_one_body["font"]["latin"]["explicit"])
        self.assertFalse(page_one_body["font"]["latin"]["inherited"])

        page_numbers = role_runs(report, "page-number")
        self.assertEqual(len(page_numbers), 1)
        self.assertTrue(all(run["origin_level"] == "master" for run in page_numbers))
        self.assertTrue(all(run["inherited_content"] for run in page_numbers))
        self.assertEqual(len(role_runs(report, "caption")), 1)
        footers = role_runs(report, "footer")
        self.assertEqual(len(footers), 1)
        self.assertTrue(all(run["origin_level"] == "master" for run in footers))
        self.assertIn("rendered font substitution", " ".join(report["limitations"]))
        self.assertIn("overflow", " ".join(report["limitations"]))

    def test_default_reports_but_strict_fails_inconsistent_role(self) -> None:
        pptx = make_pptx(
            self.tmp / "inconsistent.pptx",
            inconsistent=True,
            hidden_backup=False,
        )

        report = AUDIT.audit_pptx(pptx)
        strict = AUDIT.audit_pptx(pptx, fail_inconsistent_role=True)

        self.assertTrue(report["ok"])
        body_inventory = next(
            item for item in report["inventory"] if item["role"] == "body"
        )
        self.assertEqual(
            {item["value"] for item in body_inventory["fonts"]["latin"]},
            {"Arial", "Calibri"},
        )
        self.assertEqual(
            {item["value"] for item in body_inventory["sizes"]}, {1800, 2000}
        )
        self.assertFalse(strict["ok"])
        self.assertIn("inconsistent-role-font", failure_codes(strict))
        self.assertIn("inconsistent-role-size", failure_codes(strict))
        self.assertIn("inconsistent-role-bold", failure_codes(strict))

    def test_hidden_backup_is_excluded_unless_explicitly_included(self) -> None:
        pptx = make_pptx(self.tmp / "hidden-backup.pptx", inconsistent=True)
        visible_expectation = AUDIT.parse_expectation(
            "body=latin:Calibri|eastAsia:Microsoft YaHei,20,true"
        )

        default_scope = AUDIT.audit_pptx(
            pptx,
            expectations=[visible_expectation],
            fail_inconsistent_role=True,
        )
        including_hidden = AUDIT.audit_pptx(
            pptx,
            expectations=[visible_expectation],
            fail_inconsistent_role=True,
            include_hidden=True,
        )
        including_hidden_consistency = AUDIT.audit_pptx(
            pptx,
            fail_inconsistent_role=True,
            include_hidden=True,
        )
        selected_hidden_default = AUDIT.audit_pptx(
            pptx,
            slide_ranges=["2"],
        )
        selected_hidden_included = AUDIT.audit_pptx(
            pptx,
            slide_ranges=["2"],
            include_hidden=True,
        )

        self.assertTrue(default_scope["ok"], default_scope["validation"]["failures"])
        self.assertEqual(default_scope["summary"]["hidden"], 1)
        self.assertEqual(default_scope["summary"]["audited_hidden"], 0)
        self.assertEqual(default_scope["scope"]["audited_pages"], [1])
        body_inventory = next(
            item for item in default_scope["inventory"] if item["role"] == "body"
        )
        self.assertEqual(
            {item["value"] for item in body_inventory["fonts"]["latin"]},
            {"Calibri"},
        )

        self.assertFalse(including_hidden["ok"])
        self.assertEqual(including_hidden["scope"]["policy"], "all-including-hidden")
        self.assertEqual(including_hidden["scope"]["audited_pages"], [1, 2])
        self.assertEqual(including_hidden["summary"]["audited_hidden"], 1)
        self.assertIn("expectation-mismatch", failure_codes(including_hidden))
        self.assertFalse(including_hidden_consistency["ok"])
        self.assertIn(
            "inconsistent-role-font", failure_codes(including_hidden_consistency)
        )
        self.assertEqual(selected_hidden_default["scope"]["audited_pages"], [])
        self.assertEqual(
            selected_hidden_default["scope"]["excluded_hidden_pages"], [2]
        )
        self.assertEqual(selected_hidden_default["inventory"], [])
        self.assertEqual(selected_hidden_included["scope"]["audited_pages"], [2])
        self.assertEqual(
            selected_hidden_included["scope"]["policy"],
            "selected-including-hidden",
        )
        self.assertTrue(selected_hidden_included["inventory"])

    def test_physical_slide_scope_isolates_other_visible_history(self) -> None:
        pptx = make_pptx(
            self.tmp / "local-change.pptx",
            inconsistent=True,
            hidden_backup=False,
        )

        whole_deck = AUDIT.audit_pptx(pptx, fail_inconsistent_role=True)
        page_one = AUDIT.audit_pptx(
            pptx,
            fail_inconsistent_role=True,
            slide_ranges=["1"],
        )

        self.assertFalse(whole_deck["ok"])
        self.assertTrue(page_one["ok"], page_one["validation"]["failures"])
        self.assertEqual(page_one["scope"]["policy"], "selected-visible")
        self.assertEqual(page_one["scope"]["requested_pages"], [1])
        self.assertEqual(page_one["scope"]["audited_pages"], [1])
        self.assertEqual(page_one["scope"]["excluded_unselected_pages"], [2])
        self.assertEqual(
            [slide["in_scope"] for slide in page_one["slides"]], [True, False]
        )
        body_inventory = next(
            item for item in page_one["inventory"] if item["role"] == "body"
        )
        self.assertEqual(
            {item["value"] for item in body_inventory["fonts"]["latin"]},
            {"Calibri"},
        )
        self.assertEqual(AUDIT.parse_slide_ranges(["1,3-4", "2"]), {1, 2, 3, 4})

    def test_repeated_expectations_authorize_variants(self) -> None:
        pptx = make_pptx(
            self.tmp / "authorized.pptx",
            inconsistent=True,
            hidden_backup=False,
        )
        expectations = [
            AUDIT.parse_expectation(
                "body=latin:Arial|eastAsia:SimSun,18,false"
            ),
            AUDIT.parse_expectation(
                "body=latin:Calibri|eastAsia:Microsoft YaHei,20,true"
            ),
        ]

        authorized = AUDIT.audit_pptx(
            pptx,
            expectations=expectations,
            fail_inconsistent_role=True,
        )
        rejected = AUDIT.audit_pptx(
            pptx,
            expectations=[AUDIT.parse_expectation("body=Arial,18,false")],
        )

        self.assertTrue(authorized["ok"], authorized["validation"]["failures"])
        self.assertEqual(authorized["status"], "ok")
        self.assertFalse(rejected["ok"])
        self.assertIn("expectation-mismatch", failure_codes(rejected))

    def test_unresolved_theme_reference_is_reported_without_guessing(self) -> None:
        pptx = make_pptx(self.tmp / "unresolved.pptx", include_hans=False)

        report = AUDIT.audit_pptx(pptx, include_hidden=True)

        title = role_runs(report, "title")[0]
        east_asia = title["font"]["eastAsia"]
        self.assertFalse(east_asia["resolved"])
        self.assertEqual(east_asia["raw"], "+mj-ea")
        self.assertIn("Hans", east_asia["unresolved_reason"])
        unresolved = [
            item
            for item in report["unresolved"]
            if item["role"] == "title" and item["property"] == "font.eastAsia"
        ]
        self.assertEqual(len(unresolved), 2)
        self.assertTrue(report["ok"])
        self.assertIn("<unresolved>", AUDIT.report_to_text(report))

    def test_mojibake_typeface_is_unresolved_instead_of_accepted(self) -> None:
        props = ET.Element(AUDIT.q("a", "rPr"))
        ET.SubElement(props, AUDIT.q("a", "latin"), {"typeface": "????"})
        candidate = AUDIT.Candidate(
            props=props,
            font_ref=None,
            level="run",
            part="ppt/slides/slide1.xml",
            path="shape[1]/p[1]/r[1]",
            explicit=True,
            inherited=False,
        )

        value = AUDIT._resolve_font(
            "latin", [candidate], None, language="en-US", text="Title"
        )

        self.assertFalse(value["resolved"])
        self.assertIsNone(value["value"])
        self.assertIn("mojibake", value["unresolved_reason"])

    def test_cli_json_and_failure_exit_code(self) -> None:
        pptx = make_pptx(
            self.tmp / "cli.pptx",
            inconsistent=True,
            hidden_backup=False,
        )

        json_result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), str(pptx), "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        strict_result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(SCRIPT),
                str(pptx),
                "--json",
                "--fail-inconsistent-role",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        scoped_result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(SCRIPT),
                str(pptx),
                "--json",
                "--slides",
                "1",
                "--fail-inconsistent-role",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        repeated_scope_result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(SCRIPT),
                str(pptx),
                "--json",
                "--slides",
                "1",
                "--slides",
                "2",
                "--fail-inconsistent-role",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

        self.assertEqual(json_result.returncode, 0, json_result.stderr)
        payload = json.loads(json_result.stdout)
        self.assertEqual(payload["status"], "report")
        self.assertEqual(payload["slides"][0]["slide_id"], 257)
        self.assertEqual(strict_result.returncode, 1, strict_result.stderr)
        strict_payload = json.loads(strict_result.stdout)
        self.assertFalse(strict_payload["ok"])
        self.assertIn("inconsistent-role-font", failure_codes(strict_payload))
        self.assertEqual(scoped_result.returncode, 0, scoped_result.stderr)
        scoped_payload = json.loads(scoped_result.stdout)
        self.assertEqual(scoped_payload["scope"]["policy"], "selected-visible")
        self.assertEqual(scoped_payload["scope"]["audited_pages"], [1])
        self.assertEqual(repeated_scope_result.returncode, 1, repeated_scope_result.stderr)
        repeated_payload = json.loads(repeated_scope_result.stdout)
        self.assertEqual(repeated_payload["scope"]["slide_ranges"], ["1", "2"])
        self.assertEqual(repeated_payload["scope"]["requested_pages"], [1, 2])


if __name__ == "__main__":
    unittest.main(verbosity=2)
