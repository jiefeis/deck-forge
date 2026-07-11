#!/usr/bin/env python3
"""Synthetic regression tests for scripts/audit_pptx_structure.py."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "audit_pptx_structure.py"
SPEC = importlib.util.spec_from_file_location("audit_pptx_structure", SCRIPT)
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


def slide_xml(
    texts: list[str],
    *,
    hidden: bool = False,
    shape_ids: list[int] | None = None,
    shape_names: list[str] | None = None,
    bboxes: list[tuple[int, int, int, int]] | None = None,
    placeholders: list[tuple[str, str] | None] | None = None,
) -> bytes:
    root = ET.Element(q(P_NS, "sld"), {"show": "0"} if hidden else {})
    common = ET.SubElement(root, q(P_NS, "cSld"))
    tree = ET.SubElement(common, q(P_NS, "spTree"))
    nv_group = ET.SubElement(tree, q(P_NS, "nvGrpSpPr"))
    ET.SubElement(nv_group, q(P_NS, "cNvPr"), {"id": "1", "name": ""})
    ET.SubElement(nv_group, q(P_NS, "cNvGrpSpPr"))
    ET.SubElement(nv_group, q(P_NS, "nvPr"))
    ET.SubElement(tree, q(P_NS, "grpSpPr"))

    shape_ids = shape_ids or list(range(2, len(texts) + 2))
    shape_names = shape_names or [
        "Title 1" if index == 1 else f"TextBox {index}"
        for index in range(1, len(texts) + 1)
    ]
    bboxes = bboxes or [
        (800000, 400000 + (index - 1) * 900000, 8000000, 600000)
        for index in range(1, len(texts) + 1)
    ]
    placeholders = placeholders or [
        ("title", "0") if index == 1 else ("body", str(index - 1))
        for index in range(1, len(texts) + 1)
    ]
    if not (
        len(texts)
        == len(shape_ids)
        == len(shape_names)
        == len(bboxes)
        == len(placeholders)
    ):
        raise ValueError("text shape fixture lists must have equal lengths")

    for index, (text, shape_id, shape_name, bbox, placeholder_spec) in enumerate(
        zip(texts, shape_ids, shape_names, bboxes, placeholders), 1
    ):
        shape = ET.SubElement(tree, q(P_NS, "sp"))
        nv = ET.SubElement(shape, q(P_NS, "nvSpPr"))
        ET.SubElement(
            nv,
            q(P_NS, "cNvPr"),
            {"id": str(shape_id), "name": shape_name},
        )
        ET.SubElement(nv, q(P_NS, "cNvSpPr"))
        nv_pr = ET.SubElement(nv, q(P_NS, "nvPr"))
        if placeholder_spec is not None:
            ph_type, ph_index = placeholder_spec
            ET.SubElement(nv_pr, q(P_NS, "ph"), {"type": ph_type, "idx": ph_index})
        shape_props = ET.SubElement(shape, q(P_NS, "spPr"))
        transform = ET.SubElement(shape_props, q(A_NS, "xfrm"))
        x, y, cx, cy = bbox
        ET.SubElement(transform, q(A_NS, "off"), {"x": str(x), "y": str(y)})
        ET.SubElement(transform, q(A_NS, "ext"), {"cx": str(cx), "cy": str(cy)})
        tx_body = ET.SubElement(shape, q(P_NS, "txBody"))
        ET.SubElement(tx_body, q(A_NS, "bodyPr"))
        ET.SubElement(tx_body, q(A_NS, "lstStyle"))
        paragraph = ET.SubElement(tx_body, q(A_NS, "p"))
        run = ET.SubElement(paragraph, q(A_NS, "r"))
        ET.SubElement(run, q(A_NS, "rPr"), {"lang": "en-US"})
        ET.SubElement(run, q(A_NS, "t")).text = text
        ET.SubElement(paragraph, q(A_NS, "endParaRPr"), {"lang": "en-US"})
    return xml_bytes(root)


def make_pptx(
    path: Path,
    *,
    order: tuple[int, ...] = (256, 257),
    hidden: frozenset[int] = frozenset(),
    texts: dict[int, list[str]] | None = None,
    shared_marker: str = "shared-v1",
    shape_ids: dict[int, list[int]] | None = None,
    shape_names: dict[int, list[str]] | None = None,
    bboxes: dict[int, list[tuple[int, int, int, int]]] | None = None,
    placeholders: dict[int, list[tuple[str, str] | None]] | None = None,
    omit_slide_relationships: frozenset[int] = frozenset(),
) -> Path:
    texts = texts or {
        256: ["First question?", "First body"],
        257: ["Second title", "Second body"],
    }
    slide_ids = tuple(sorted(texts))
    part_for_id = {
        slide_id: f"ppt/slides/slide{index}.xml"
        for index, slide_id in enumerate(slide_ids, 1)
    }
    rid_for_id = {slide_id: f"rIdSlide{slide_id}" for slide_id in slide_ids}

    presentation = ET.Element(q(P_NS, "presentation"))
    slide_list = ET.SubElement(presentation, q(P_NS, "sldIdLst"))
    for slide_id in order:
        attrs = {"id": str(slide_id), q(R_NS, "id"): rid_for_id[slide_id]}
        ET.SubElement(slide_list, q(P_NS, "sldId"), attrs)
    ET.SubElement(presentation, q(P_NS, "sldSz"), {"cx": "12192000", "cy": "6858000"})

    pres_rels = [
        (
            rid_for_id[slide_id],
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide",
            part_for_id[slide_id].removeprefix("ppt/"),
        )
        for slide_id in slide_ids
        if slide_id not in omit_slide_relationships
    ]
    pres_rels.append(
        (
            "rIdMaster",
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster",
            "slideMasters/slideMaster1.xml",
        )
    )

    layout = ET.Element(q(P_NS, "sldLayout"), {"type": "titleAndContent"})
    ET.SubElement(layout, q(P_NS, "cSld"), {"name": "Synthetic Layout"})
    master = ET.Element(q(P_NS, "sldMaster"))
    ET.SubElement(master, q(P_NS, "cSld"), {"name": "Synthetic Master"})
    theme = ET.Element(q(A_NS, "theme"), {"name": shared_marker})
    ET.SubElement(theme, q(A_NS, "themeElements"))

    content_types = ET.Element(q(CT_NS, "Types"))
    ET.SubElement(
        content_types,
        q(CT_NS, "Default"),
        {"Extension": "xml", "ContentType": "application/xml"},
    )

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", xml_bytes(content_types))
        zf.writestr("ppt/presentation.xml", xml_bytes(presentation))
        zf.writestr("ppt/_rels/presentation.xml.rels", relationships(pres_rels))
        for slide_id in slide_ids:
            part = part_for_id[slide_id]
            zf.writestr(
                part,
                slide_xml(
                    texts[slide_id],
                    hidden=slide_id in hidden,
                    shape_ids=(shape_ids or {}).get(slide_id),
                    shape_names=(shape_names or {}).get(slide_id),
                    bboxes=(bboxes or {}).get(slide_id),
                    placeholders=(placeholders or {}).get(slide_id),
                ),
            )
            rels_part = part.replace("/slides/", "/slides/_rels/") + ".rels"
            zf.writestr(
                rels_part,
                relationships(
                    [
                        (
                            "rIdLayout",
                            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout",
                            "../slideLayouts/slideLayout1.xml",
                        )
                    ]
                ),
            )
        zf.writestr("ppt/slideLayouts/slideLayout1.xml", xml_bytes(layout))
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
        zf.writestr("ppt/slideMasters/slideMaster1.xml", xml_bytes(master))
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
        zf.writestr("ppt/theme/theme1.xml", xml_bytes(theme))
    return path


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def codes(items: list[dict[str, object]]) -> set[str]:
    return {str(item["code"]) for item in items}


def duplicate_zip_entry(path: Path, part: str = "ppt/theme/theme1.xml") -> None:
    with zipfile.ZipFile(path, "r") as zf:
        data = zf.read(part)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(path, "a", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(part, data)


def run_cli(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPT), *(str(arg) for arg in args)],
        capture_output=True,
        text=True,
        check=False,
    )


def write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


class AuditPptxStructureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="audit-pptx-test-")
        self.tmp = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_manifest_uses_true_order_and_is_read_only(self) -> None:
        pptx = make_pptx(self.tmp / "deck.pptx", order=(257, 256), hidden=frozenset({256}))
        before = file_sha256(pptx)

        manifest = AUDIT.build_manifest(pptx)

        self.assertEqual([slide["slide_id"] for slide in manifest["slides"]], [257, 256])
        self.assertEqual([slide["page"] for slide in manifest["slides"]], [1, 2])
        self.assertFalse(manifest["slides"][0]["hidden"])
        self.assertTrue(manifest["slides"][1]["hidden"])
        self.assertEqual(manifest["slides"][0]["title"], "Second title")
        self.assertEqual(manifest["slides"][0]["text_box_count"], 2)
        self.assertEqual(
            manifest["slides"][0]["text_boxes"][0]["bbox"],
            {"x": 800000, "y": 400000, "cx": 8000000, "cy": 600000},
        )
        self.assertEqual(manifest["slides"][0]["layout"]["part"], "ppt/slideLayouts/slideLayout1.xml")
        self.assertEqual(len(manifest["slides"][0]["structure_fingerprint"]), 64)
        self.assertEqual(len(manifest["slides"][0]["text_fingerprint"]), 64)
        self.assertEqual(before, file_sha256(pptx))

    def test_slide_order_swap_is_detected_and_maps_by_stable_id(self) -> None:
        source = make_pptx(self.tmp / "source.pptx")
        target = make_pptx(self.tmp / "target.pptx", order=(257, 256))

        report = AUDIT.compare_pptx(source, target)

        self.assertFalse(report["ok"])
        self.assertIn("slide-order-changed", codes(report["differences"]))
        mapping = {item["slide_id"]: item["target_page"] for item in report["slide_mappings"]}
        self.assertEqual(mapping, {256: 2, 257: 1})
        allowed = AUDIT.compare_pptx(source, target, allow_slides={1, 2})
        self.assertTrue(allowed["ok"])

    def test_auto_true_order_fallback_is_provisional_for_translation(self) -> None:
        source = make_pptx(
            self.tmp / "source.pptx",
            order=(256,),
            texts={256: ["Same title", "Same body"]},
        )
        target = make_pptx(
            self.tmp / "target.pptx",
            order=(900,),
            texts={900: ["Same title", "Same body"]},
        )

        auto_report = AUDIT.compare_pptx(
            source,
            target,
            allow_slides={1},
            translation_check=True,
        )

        self.assertTrue(auto_report["ok"])
        fallback = next(
            item
            for item in auto_report["translation_warnings"]
            if item["code"] == "translation-order-fallback"
        )
        self.assertEqual(fallback["mapping"], "true-order")
        self.assertEqual(fallback["evidence"]["policy"], "auto")
        self.assertFalse(fallback["evidence"]["stable_slide_id_match"])
        mapping = auto_report["slide_mappings"][0]
        self.assertEqual(mapping["mapping"], "true-order")
        self.assertTrue(mapping["evidence"]["provisional"])

        strict_auto = AUDIT.compare_pptx(
            source,
            target,
            allow_slides={1},
            strict_translation=True,
        )
        self.assertFalse(strict_auto["ok"])
        self.assertIn(
            "translation-order-fallback",
            codes(strict_auto["violations"]),
        )

        explicit_order = AUDIT.compare_pptx(
            source,
            target,
            allow_slides={1},
            mapping="order",
            strict_translation=True,
        )
        self.assertTrue(explicit_order["ok"])
        self.assertNotIn(
            "translation-order-fallback",
            codes(explicit_order["translation_warnings"]),
        )
        explicit_mapping = explicit_order["slide_mappings"][0]
        self.assertFalse(explicit_mapping["evidence"]["provisional"])
        self.assertEqual(explicit_mapping["evidence"]["policy"], "order")

    def test_hidden_state_change_is_detected(self) -> None:
        source = make_pptx(self.tmp / "source.pptx")
        target = make_pptx(self.tmp / "target.pptx", hidden=frozenset({257}))

        report = AUDIT.compare_pptx(source, target)

        self.assertFalse(report["ok"])
        self.assertIn("slide-hidden-changed", codes(report["differences"]))
        self.assertTrue(AUDIT.compare_pptx(source, target, allow_slides={2})["ok"])

    def test_unapproved_slide_change_fails(self) -> None:
        source = make_pptx(self.tmp / "source.pptx")
        target = make_pptx(
            self.tmp / "target.pptx",
            texts={
                256: ["First question?", "First body"],
                257: ["Second title", "Changed body"],
            },
        )

        report = AUDIT.compare_pptx(source, target, allow_slides={1})

        self.assertFalse(report["ok"])
        self.assertIn("slide-local-parts-changed", codes(report["differences"]))
        self.assertTrue(AUDIT.compare_pptx(source, target, allow_slides={2})["ok"])

        blocked_cli = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                str(SCRIPT),
                "compare",
                str(source),
                str(target),
                "--allow-slides",
                "1",
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(blocked_cli.returncode, 1)
        self.assertFalse(json.loads(blocked_cli.stdout)["ok"])

        allowed_cli = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                str(SCRIPT),
                "compare",
                str(source),
                str(target),
                "--allow-slides",
                "2",
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(allowed_cli.returncode, 0, allowed_cli.stderr)

    def test_shared_part_change_requires_allow_shared(self) -> None:
        source = make_pptx(self.tmp / "source.pptx", shared_marker="shared-v1")
        target = make_pptx(self.tmp / "target.pptx", shared_marker="shared-v2")

        report = AUDIT.compare_pptx(source, target)

        self.assertFalse(report["ok"])
        self.assertIn("shared-part-changed", codes(report["differences"]))
        self.assertTrue(AUDIT.compare_pptx(source, target, allow_shared=True)["ok"])

    def test_translation_mapping_falls_back_after_shape_id_changes(self) -> None:
        texts = {256: ["Same title?", "Same body", "Detached caption"]}
        placeholders = {256: [("title", "0"), ("body", "1"), None]}
        source = make_pptx(
            self.tmp / "source.pptx",
            order=(256,),
            texts=texts,
            shape_ids={256: [2, 3, 4]},
            placeholders=placeholders,
        )
        target = make_pptx(
            self.tmp / "target.pptx",
            order=(256,),
            texts=texts,
            shape_ids={256: [102, 103, 104]},
            placeholders=placeholders,
        )

        report = AUDIT.compare_pptx(
            source,
            target,
            allow_slides={1},
            translation_check=True,
        )

        warning_codes = codes(report["translation_warnings"])
        self.assertNotIn("translation-text-box-missing", warning_codes)
        self.assertNotIn("translation-text-box-extra", warning_codes)
        mapping_methods = {
            item["mapping"] for item in report["translation_box_mappings"]
        }
        self.assertIn("placeholder", mapping_methods)
        self.assertIn("geometry", mapping_methods)

    def test_translation_exceptions_are_page_scoped_for_reordered_overlay(self) -> None:
        source = make_pptx(
            self.tmp / "source.pptx",
            texts={256: ["Question?", "Rebuilt source body"], 257: ["Other"]},
            shape_names={256: ["Title 1", "Source body"]},
        )
        target = make_pptx(
            self.tmp / "target.pptx",
            order=(257, 256),
            texts={256: ["Question?", "Overlay annotation"], 257: ["Other"]},
            shape_ids={256: [2, 99]},
            shape_names={256: ["Title 1", "EN_overlay_chart_01"]},
            bboxes={
                256: [
                    (800000, 400000, 8000000, 600000),
                    (9500000, 5200000, 1200000, 500000),
                ]
            },
            placeholders={256: [("title", "0"), None]},
        )
        exceptions = write_json(
            self.tmp / "exceptions.json",
            {
                "allow_extra": [
                    {
                        "id": "approved-en-overlays",
                        "target_page": 2,
                        "name": "EN_overlay_*",
                    }
                ],
                "allow_missing": [
                    {
                        "id": "rebuilt-source-body",
                        "source_page": 1,
                        "key": "id:3",
                    }
                ],
            },
        )

        report = AUDIT.compare_pptx(
            source,
            target,
            allow_slides={1, 2},
            translation_check=True,
            strict_translation=True,
            translation_exceptions=exceptions,
        )

        self.assertTrue(report["ok"])
        self.assertFalse(report["translation_warnings"])
        self.assertFalse(report["translation_exception_issues"])
        applied_ids = {
            item["rule_id"] for item in report["translation_exceptions_applied"]
        }
        self.assertEqual(
            applied_ids,
            {"approved-en-overlays", "rebuilt-source-body"},
        )
        overlay = next(
            item
            for item in report["translation_exceptions_applied"]
            if item["rule_id"] == "approved-en-overlays"
        )
        self.assertEqual(overlay["target_page"], 2)
        self.assertEqual(overlay["shape_name"], "EN_overlay_chart_01")

        cli = run_cli(
            "compare",
            source,
            target,
            "--allow-slides",
            "1-2",
            "--strict-translation",
            "--translation-exceptions",
            exceptions,
            "--format",
            "json",
        )
        self.assertEqual(cli.returncode, 0, cli.stderr)
        cli_payload = json.loads(cli.stdout)
        self.assertEqual(
            cli_payload["summary"]["translation_exception_applied_count"],
            2,
        )

        wrong_page = write_json(
            self.tmp / "wrong-page.json",
            {
                "allow_extra": [
                    {"id": "wrong-page", "target_page": 1, "name": "EN_overlay_*"}
                ],
                "allow_missing": [
                    {"source_page": 1, "key": "id:3"}
                ],
            },
        )
        wrong_report = AUDIT.compare_pptx(
            source,
            target,
            allow_slides={1, 2},
            translation_check=True,
            strict_translation=True,
            translation_exceptions=wrong_page,
        )
        self.assertFalse(wrong_report["ok"])
        self.assertIn(
            "translation-text-box-extra",
            codes(wrong_report["translation_warnings"]),
        )
        extra_warning = next(
            item
            for item in wrong_report["translation_warnings"]
            if item["code"] == "translation-text-box-extra"
        )
        self.assertEqual(extra_warning["shape_name"], "EN_overlay_chart_01")
        self.assertEqual(extra_warning["shape_key"], "id:99")
        self.assertIn(
            "translation-exception-unused",
            codes(wrong_report["translation_exception_issues"]),
        )

    def test_explicit_exception_box_mapping_overrides_automatic_mapping(self) -> None:
        source = make_pptx(
            self.tmp / "source.pptx",
            order=(256,),
            texts={256: ["Mapped text"]},
            shape_ids={256: [2]},
            shape_names={256: ["Source rebuilt chart label"]},
            placeholders={256: [None]},
        )
        target = make_pptx(
            self.tmp / "target.pptx",
            order=(256,),
            texts={256: ["Mapped text"]},
            shape_ids={256: [102]},
            shape_names={256: ["Target rebuilt chart label"]},
            bboxes={256: [(9500000, 5200000, 1200000, 500000)]},
            placeholders={256: [None]},
        )
        exceptions = write_json(
            self.tmp / "mapping.json",
            {
                "box_mappings": [
                    {
                        "id": "rebuilt-chart-label",
                        "source_page": 1,
                        "source_key": "id:2",
                        "target_page": 1,
                        "target_key": "id:102",
                    }
                ]
            },
        )

        report = AUDIT.compare_pptx(
            source,
            target,
            allow_slides={1},
            translation_check=True,
            strict_translation=True,
            translation_exceptions=exceptions,
        )

        self.assertTrue(report["ok"])
        self.assertFalse(report["translation_warnings"])
        mapping = report["translation_box_mappings"][0]
        self.assertEqual(mapping["mapping"], "exception-explicit")
        self.assertEqual(mapping["exception_rule_id"], "rebuilt-chart-label")
        self.assertEqual(
            report["translation_exceptions_applied"][0]["kind"],
            "box_mapping",
        )

    def test_unused_and_overbroad_translation_exception_rules_are_reported(self) -> None:
        source = make_pptx(self.tmp / "source.pptx")
        target = make_pptx(self.tmp / "target.pptx")
        exceptions = write_json(
            self.tmp / "unused.json",
            {
                "allow_extra": [
                    {"id": "unused-overlay", "target_page": 1, "name": "EN_overlay_*"}
                ],
                "allow_missing": [
                    {"id": "too-wide", "source_page": 1, "shape": "*"}
                ],
            },
        )

        report = AUDIT.compare_pptx(
            source,
            target,
            allow_slides={1, 2},
            translation_check=True,
            strict_translation=True,
            translation_exceptions=exceptions,
        )

        self.assertFalse(report["ok"])
        issue_codes = codes(report["translation_exception_issues"])
        self.assertIn("translation-exception-unused", issue_codes)
        self.assertIn("translation-exception-too-broad", issue_codes)
        self.assertFalse(report["translation_exceptions_applied"])

    def test_translation_language_is_opt_in_and_en_can_be_strict(self) -> None:
        source = make_pptx(
            self.tmp / "source.pptx",
            order=(256,),
            texts={256: ["Why now?", "Translate this body"]},
        )
        target = make_pptx(
            self.tmp / "target.pptx",
            order=(256,),
            texts={256: ["\u4e3a\u4ec0\u4e48\u73b0\u5728"]},
        )

        neutral_report = AUDIT.compare_pptx(
            source,
            target,
            allow_slides={1},
            translation_check=True,
        )
        neutral_codes = codes(neutral_report["translation_warnings"])
        self.assertTrue(neutral_report["ok"])
        self.assertIn("translation-text-box-missing", neutral_codes)
        self.assertIn("translation-title-question-mismatch", neutral_codes)
        self.assertNotIn("translation-cjk-in-english", neutral_codes)
        self.assertIsNone(neutral_report["policy"]["target_language"])

        english_report = AUDIT.compare_pptx(
            source,
            target,
            allow_slides={1},
            translation_check=True,
            target_language="en",
        )
        self.assertIn(
            "translation-cjk-in-english",
            codes(english_report["translation_warnings"]),
        )
        self.assertEqual(english_report["policy"]["target_language"], "en")

        strict_report = AUDIT.compare_pptx(
            source,
            target,
            allow_slides={1},
            translation_check=True,
            strict_translation=True,
            target_language="en",
        )
        self.assertFalse(strict_report["ok"])
        self.assertEqual(strict_report["translation_status"], "fail")

    def test_zh_language_check_is_conservative(self) -> None:
        source = make_pptx(
            self.tmp / "source.pptx",
            order=(256,),
            texts={
                256: [
                    "\u4e2d\u6587\u6807\u9898",
                    "\u8fd9\u662f\u4e00\u6bb5\u4e2d\u6587\u3002",
                    "\u5e2e\u52a9\u94fe\u63a5",
                    "\u4ea7\u54c1\u540d",
                    "\u8054\u7cfb\u65b9\u5f0f",
                ]
            },
        )
        target = make_pptx(
            self.tmp / "target.pptx",
            order=(256,),
            texts={
                256: [
                    "AI \u7ec4\u7ec7\u7ade\u4e89\u529b",
                    "This paragraph is still entirely written in English and should be translated.",
                    "https://example.com/help",
                    "Product AI Workshop",
                    "support@example.com",
                ]
            },
        )

        report = AUDIT.compare_pptx(
            source,
            target,
            allow_slides={1},
            translation_check=True,
            target_language="zh",
        )

        language_warnings = [
            item
            for item in report["translation_warnings"]
            if item["code"] == "translation-english-prose-in-chinese"
        ]
        self.assertEqual(len(language_warnings), 1)
        self.assertIn("entirely written", language_warnings[0]["excerpt"])
        self.assertEqual(report["policy"]["target_language"], "zh")

    def test_integrity_warnings_fail_manifest_and_compare(self) -> None:
        valid = make_pptx(self.tmp / "valid.pptx")
        duplicate_zip = make_pptx(self.tmp / "duplicate-zip.pptx")
        duplicate_zip_entry(duplicate_zip)
        duplicate_id = make_pptx(
            self.tmp / "duplicate-id.pptx",
            order=(256, 256),
        )
        missing_rel = make_pptx(
            self.tmp / "missing-rel.pptx",
            omit_slide_relationships=frozenset({257}),
        )

        fixtures = [
            (duplicate_zip, "duplicate-zip-entry"),
            (duplicate_id, "duplicate-stable-slide-id"),
            (missing_rel, "missing-slide-relationship"),
        ]
        for pptx, expected_code in fixtures:
            with self.subTest(pptx=pptx.name):
                blocked = run_cli("manifest", pptx, "--format", "json")
                self.assertEqual(blocked.returncode, 1, blocked.stderr)
                payload = json.loads(blocked.stdout)
                self.assertIn(expected_code, codes(payload["integrity_warnings"]))
                allowed = run_cli(
                    "manifest", pptx, "--format", "json", "--allow-warnings"
                )
                self.assertEqual(allowed.returncode, 0, allowed.stderr)
                target_report = AUDIT.compare_pptx(
                    valid,
                    pptx,
                    allow_slides={1, 2},
                    allow_shared=True,
                )
                target_integrity = [
                    item
                    for item in target_report["violations"]
                    if item["code"] == "package-integrity-warning"
                    and item["side"] == "target"
                    and item["integrity_code"] == expected_code
                ]
                self.assertTrue(target_integrity)

        comparison = AUDIT.compare_pptx(
            duplicate_zip,
            valid,
            allow_slides={1, 2},
            allow_shared=True,
        )
        self.assertFalse(comparison["ok"])
        integrity_violations = [
            item
            for item in comparison["violations"]
            if item["code"] == "package-integrity-warning"
        ]
        self.assertTrue(integrity_violations)
        self.assertEqual(integrity_violations[0]["side"], "source")

    def test_cli_emits_json_manifest(self) -> None:
        pptx = make_pptx(self.tmp / "deck.pptx")
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPT), "manifest", str(pptx), "--format", "json"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["slide_count"], 2)

        compare_help = run_cli("compare", "--help")
        self.assertEqual(compare_help.returncode, 0)
        self.assertIn("--target-language", compare_help.stdout)
        self.assertIn("{en,zh}", compare_help.stdout)
        self.assertIn("--translation-exceptions", compare_help.stdout)
        self.assertIn("allow_extra", compare_help.stdout)
        self.assertIn("box_mappings", compare_help.stdout)
        self.assertIn("provisional", compare_help.stdout)
        manifest_help = run_cli("manifest", "--help")
        self.assertEqual(manifest_help.returncode, 0)
        self.assertIn("--allow-warnings", manifest_help.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
