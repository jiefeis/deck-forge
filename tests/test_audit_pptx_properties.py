#!/usr/bin/env python3
"""Regression tests for scripts/audit_pptx_properties.py."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


FIXTURE = load_module(
    "deckforge_structure_fixture",
    ROOT / "tests" / "test_audit_pptx_structure.py",
)
AUDIT = load_module(
    "audit_pptx_properties",
    ROOT / "scripts" / "audit_pptx_properties.py",
)
SCRIPT = ROOT / "scripts" / "audit_pptx_properties.py"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rewrite_package(
    path: Path,
    *,
    mutate: dict[str, Callable[[bytes], bytes]] | None = None,
    additions: dict[str, bytes] | None = None,
) -> None:
    mutate = mutate or {}
    additions = additions or {}
    with zipfile.ZipFile(path, "r") as source:
        parts = {name: source.read(name) for name in source.namelist()}
    for name, callback in mutate.items():
        parts[name] = callback(parts[name])
    parts.update(additions)
    replacement = path.with_suffix(".rewrite.pptx")
    with zipfile.ZipFile(replacement, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for name, data in parts.items():
            target.writestr(name, data)
    os.replace(replacement, path)


def edit_xml(callback):
    def mutate(data: bytes) -> bytes:
        root = ET.fromstring(data)
        callback(root)
        return FIXTURE.xml_bytes(root)

    return mutate


def write_scope(path: Path, rules: list[dict[str, object]]) -> Path:
    path.write_text(json.dumps({"version": 1, "rules": rules}), encoding="utf-8")
    return path


def properties(report: dict[str, object]) -> set[str]:
    return {str(item["property"]) for item in report["changes"]}


class PropertyAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="deckforge-properties-")
        self.root = Path(self.temp.name)
        self.source = FIXTURE.make_pptx(self.root / "source.pptx")
        self.target = FIXTURE.make_pptx(self.root / "target.pptx")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def audit_with_scope(self, *allowed: str) -> dict[str, object]:
        scope = write_scope(
            self.root / "scope.json",
            [{"id": "page-1", "pages": "1", "properties": list(allowed)}],
        )
        return AUDIT.audit_properties(self.source, self.target, scope_path=scope)

    def test_identical_inputs_pass_with_deny_all_and_remain_unchanged(self) -> None:
        before = (digest(self.source), digest(self.target))
        report = AUDIT.audit_properties(self.source, self.target)
        self.assertTrue(report["ok"])
        self.assertEqual(report["changes"], [])
        self.assertEqual(before, (digest(self.source), digest(self.target)))

    def test_text_change_requires_text_scope(self) -> None:
        rewrite_package(
            self.target,
            mutate={
                "ppt/slides/slide1.xml": lambda data: data.replace(
                    b"First body", b"Changed body"
                )
            },
        )
        blocked = AUDIT.audit_properties(self.source, self.target)
        allowed = self.audit_with_scope("text")
        self.assertEqual(properties(blocked), {"text"})
        self.assertFalse(blocked["ok"])
        self.assertTrue(allowed["ok"])

    def test_typography_color_background_and_geometry_are_distinct(self) -> None:
        cases = {
            "typography": edit_xml(
                lambda root: root.find(".//a:rPr", FIXTURE.AUDIT.NS).set("sz", "2400")
            ),
            "geometry": edit_xml(
                lambda root: root.find(".//a:off", FIXTURE.AUDIT.NS).set("x", "900001")
            ),
        }
        for category, mutator in cases.items():
            with self.subTest(category=category):
                FIXTURE.make_pptx(self.target)
                rewrite_package(self.target, mutate={"ppt/slides/slide1.xml": mutator})
                report = self.audit_with_scope(category)
                self.assertTrue(report["ok"], report)
                self.assertEqual(properties(report), {category})

        def add_color(root: ET.Element) -> None:
            props = root.find(".//p:sp/p:spPr", FIXTURE.AUDIT.NS)
            fill = ET.SubElement(props, FIXTURE.q(FIXTURE.A_NS, "solidFill"))
            ET.SubElement(fill, FIXTURE.q(FIXTURE.A_NS, "srgbClr"), {"val": "FF0000"})

        FIXTURE.make_pptx(self.target)
        rewrite_package(
            self.target,
            mutate={"ppt/slides/slide1.xml": edit_xml(add_color)},
        )
        self.assertTrue(self.audit_with_scope("color")["ok"])

        def add_background(root: ET.Element) -> None:
            common = root.find("p:cSld", FIXTURE.AUDIT.NS)
            background = ET.Element(FIXTURE.q(FIXTURE.P_NS, "bg"))
            props = ET.SubElement(background, FIXTURE.q(FIXTURE.P_NS, "bgPr"))
            fill = ET.SubElement(props, FIXTURE.q(FIXTURE.A_NS, "solidFill"))
            ET.SubElement(fill, FIXTURE.q(FIXTURE.A_NS, "srgbClr"), {"val": "FFFFFF"})
            common.insert(0, background)

        FIXTURE.make_pptx(self.target)
        rewrite_package(
            self.target,
            mutate={"ppt/slides/slide1.xml": edit_xml(add_background)},
        )
        report = self.audit_with_scope("background")
        self.assertTrue(report["ok"], report)
        self.assertEqual(properties(report), {"background"})

    def test_added_shape_is_shape_tree_not_silently_style_only(self) -> None:
        def add_shape(root: ET.Element) -> None:
            tree = root.find("p:cSld/p:spTree", FIXTURE.AUDIT.NS)
            original = root.find(".//p:sp", FIXTURE.AUDIT.NS)
            clone = ET.fromstring(ET.tostring(original))
            clone.find(".//p:cNvPr", FIXTURE.AUDIT.NS).set("id", "99")
            tree.append(clone)

        rewrite_package(
            self.target,
            mutate={"ppt/slides/slide1.xml": edit_xml(add_shape)},
        )
        blocked = self.audit_with_scope("typography", "color", "geometry")
        self.assertFalse(blocked["ok"])
        self.assertIn("shape-tree", properties(blocked))

    def test_timing_hidden_and_order_are_explicit_categories(self) -> None:
        def add_transition(root: ET.Element) -> None:
            ET.SubElement(
                root,
                FIXTURE.q(FIXTURE.P_NS, "transition"),
                {"spd": "fast"},
            )

        rewrite_package(
            self.target,
            mutate={"ppt/slides/slide1.xml": edit_xml(add_transition)},
        )
        timing = self.audit_with_scope("timing")
        self.assertTrue(timing["ok"], timing)
        self.assertEqual(properties(timing), {"timing"})

        FIXTURE.make_pptx(self.target, hidden=frozenset({256}))
        hidden = self.audit_with_scope("hidden")
        self.assertTrue(hidden["ok"], hidden)
        self.assertEqual(properties(hidden), {"hidden"})

        FIXTURE.make_pptx(self.target, order=(257, 256))
        scope = write_scope(
            self.root / "order-scope.json",
            [{"id": "reorder", "pages": "1-2", "properties": ["order"]}],
        )
        order = AUDIT.audit_properties(self.source, self.target, scope_path=scope)
        self.assertTrue(order["ok"], order)
        self.assertEqual(properties(order), {"order"})

    def test_relationship_and_media_dependency_need_both_permissions(self) -> None:
        rel_part = "ppt/slides/_rels/slide1.xml.rels"

        def add_image_rel(root: ET.Element) -> None:
            ET.SubElement(
                root,
                FIXTURE.q(FIXTURE.REL_NS, "Relationship"),
                {
                    "Id": "rIdImage",
                    "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
                    "Target": "../media/image1.png",
                },
            )

        rewrite_package(
            self.target,
            mutate={rel_part: edit_xml(add_image_rel)},
            additions={"ppt/media/image1.png": b"synthetic-image-bytes"},
        )
        blocked = self.audit_with_scope("relationships")
        allowed = self.audit_with_scope("relationships", "media-data")
        self.assertEqual(properties(blocked), {"relationships", "media-data"})
        self.assertFalse(blocked["ok"])
        self.assertTrue(allowed["ok"])

    def test_off_scope_slide_and_shared_part_changes_fail(self) -> None:
        rewrite_package(
            self.target,
            mutate={
                "ppt/slides/slide2.xml": lambda data: data.replace(
                    b"Second body", b"Changed body"
                )
            },
        )
        report = self.audit_with_scope("text")
        self.assertFalse(report["ok"])
        self.assertTrue(any(item.get("source_page") == 2 for item in report["violations"]))

        FIXTURE.make_pptx(self.target, shared_marker="shared-v2")
        shared = AUDIT.audit_properties(self.source, self.target)
        self.assertFalse(shared["ok"])
        self.assertIn("shared-part-change", {item["code"] for item in shared["violations"]})

    def test_global_presentation_settings_fail_closed(self) -> None:
        def change_presentation(root: ET.Element) -> None:
            root.set("showSpecialPlsOnTitleSld", "0")

        rewrite_package(
            self.target,
            mutate={"ppt/presentation.xml": edit_xml(change_presentation)},
        )
        report = AUDIT.audit_properties(self.source, self.target)
        self.assertFalse(report["ok"])
        self.assertIn(
            "global-presentation-part-change",
            {item["code"] for item in report["violations"]},
        )

        FIXTURE.make_pptx(self.target)
        rewrite_package(
            self.target,
            additions={
                "ppt/presProps.xml": FIXTURE.xml_bytes(
                    ET.Element(FIXTURE.q(FIXTURE.P_NS, "presentationPr"))
                )
            },
        )
        added = AUDIT.audit_properties(self.source, self.target)
        self.assertFalse(added["ok"])
        self.assertIn(
            "global-presentation-part-change",
            {item["code"] for item in added["violations"]},
        )

    def test_invalid_and_unused_scope_rules_fail_closed(self) -> None:
        invalid = write_scope(
            self.root / "invalid.json",
            [{"id": "broad", "pages": "1", "properties": ["*"]}],
        )
        with self.assertRaises(AUDIT.AuditError):
            AUDIT.audit_properties(self.source, self.target, scope_path=invalid)

        unused = write_scope(
            self.root / "unused.json",
            [{"id": "unused", "pages": "1", "properties": ["text"]}],
        )
        report = AUDIT.audit_properties(self.source, self.target, scope_path=unused)
        self.assertFalse(report["ok"])
        self.assertIn("unused-scope-rule", {item["code"] for item in report["violations"]})

    def test_new_slide_requires_explicit_target_page_scope(self) -> None:
        texts = {
            256: ["First question?", "First body"],
            257: ["Second title", "Second body"],
            300: ["New title", "New body"],
        }
        FIXTURE.make_pptx(
            self.target,
            order=(256, 257, 300),
            texts=texts,
        )
        blocked = AUDIT.audit_properties(self.source, self.target)
        self.assertFalse(blocked["ok"])
        self.assertEqual(properties(blocked), {"order"})

        scope = write_scope(
            self.root / "insert-scope.json",
            [
                {
                    "id": "new-page",
                    "target_pages": "3",
                    "properties": ["order"],
                }
            ],
        )
        allowed = AUDIT.audit_properties(self.source, self.target, scope_path=scope)
        self.assertTrue(allowed["ok"], allowed)

    def test_cli_json_uses_policy_exit_codes(self) -> None:
        rewrite_package(
            self.target,
            mutate={
                "ppt/slides/slide1.xml": lambda data: data.replace(
                    b"First body", b"Changed body"
                )
            },
        )
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        failed = subprocess.run(
            [sys.executable, str(SCRIPT), str(self.source), str(self.target), "--json"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
        scope = write_scope(
            self.root / "cli-scope.json",
            [{"id": "text", "slide_ids": [256], "properties": ["text"]}],
        )
        passed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(self.source),
                str(self.target),
                "--scope",
                str(scope),
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
        self.assertEqual(failed.returncode, 1, failed.stderr)
        self.assertEqual(passed.returncode, 0, passed.stderr)
        self.assertTrue(json.loads(passed.stdout)["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
