#!/usr/bin/env python3
"""Regression tests for scripts/audit_pptx_backups.py."""

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
    "deckforge_backup_fixture",
    ROOT / "tests" / "test_audit_pptx_structure.py",
)
AUDIT = load_module(
    "audit_pptx_backups",
    ROOT / "scripts" / "audit_pptx_backups.py",
)
SCRIPT = ROOT / "scripts" / "audit_pptx_backups.py"


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


class BackupAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="deckforge-backups-")
        self.root = Path(self.temp.name)
        texts = {
            256: ["First question?", "First body"],
            257: ["Second title", "Second body"],
        }
        self.source = FIXTURE.make_pptx(self.root / "source.pptx", texts=texts)
        final_texts = {**texts, 300: list(texts[256])}
        self.target = FIXTURE.make_pptx(
            self.root / "final.pptx",
            order=(256, 257, 300),
            hidden=frozenset({300}),
            texts=final_texts,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_identical_hidden_backup_passes_and_inputs_are_unchanged(self) -> None:
        hashes = (digest(self.source), digest(self.target))
        report = AUDIT.audit_backups(self.source, self.target, [(1, 3)])
        self.assertTrue(report["ok"], report)
        self.assertTrue(report["pairs"][0]["identical"])
        self.assertNotEqual(
            report["pairs"][0]["source_slide_id"],
            report["pairs"][0]["backup_slide_id"],
        )
        self.assertEqual(hashes, (digest(self.source), digest(self.target)))

    def test_visible_backup_fails_even_when_content_is_identical(self) -> None:
        final_texts = {
            256: ["First question?", "First body"],
            257: ["Second title", "Second body"],
            300: ["First question?", "First body"],
        }
        FIXTURE.make_pptx(
            self.target,
            order=(256, 257, 300),
            texts=final_texts,
        )
        report = AUDIT.audit_backups(self.source, self.target, [(1, 3)])
        self.assertFalse(report["ok"])
        self.assertIn("backup-not-hidden", {item["code"] for item in report["violations"]})

    def test_text_style_and_geometry_changes_each_fail_identity(self) -> None:
        mutations = {
            "text": lambda data: data.replace(b"First body", b"Changed body"),
            "style": edit_xml(
                lambda root: root.find(".//a:rPr", FIXTURE.AUDIT.NS).set("sz", "2400")
            ),
            "geometry": edit_xml(
                lambda root: root.find(".//a:off", FIXTURE.AUDIT.NS).set("x", "999999")
            ),
        }
        for name, mutation in mutations.items():
            with self.subTest(name=name):
                final_texts = {
                    256: ["First question?", "First body"],
                    257: ["Second title", "Second body"],
                    300: ["First question?", "First body"],
                }
                FIXTURE.make_pptx(
                    self.target,
                    order=(256, 257, 300),
                    hidden=frozenset({300}),
                    texts=final_texts,
                )
                rewrite_package(
                    self.target,
                    mutate={"ppt/slides/slide3.xml": mutation},
                )
                report = AUDIT.audit_backups(self.source, self.target, [(1, 3)])
                self.assertFalse(report["ok"])
                self.assertIn(
                    "backup-content-mismatch",
                    {item["code"] for item in report["violations"]},
                )

    def add_equivalent_media(self) -> None:
        def add_blip(rel_id: str):
            def callback(root: ET.Element) -> None:
                shape_props = root.find(".//p:sp/p:spPr", FIXTURE.AUDIT.NS)
                ET.SubElement(
                    shape_props,
                    FIXTURE.q(FIXTURE.A_NS, "blip"),
                    {FIXTURE.q(FIXTURE.R_NS, "embed"): rel_id},
                )

            return callback

        def add_rel(rel_id: str, target: str):
            def callback(root: ET.Element) -> None:
                ET.SubElement(
                    root,
                    FIXTURE.q(FIXTURE.REL_NS, "Relationship"),
                    {
                        "Id": rel_id,
                        "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
                        "Target": target,
                    },
                )

            return callback

        media = b"same-media-content"
        rewrite_package(
            self.source,
            mutate={
                "ppt/slides/slide1.xml": edit_xml(add_blip("rIdSourceImage")),
                "ppt/slides/_rels/slide1.xml.rels": edit_xml(
                    add_rel("rIdSourceImage", "../media/source.png")
                ),
            },
            additions={"ppt/media/source.png": media},
        )
        rewrite_package(
            self.target,
            mutate={
                "ppt/slides/slide3.xml": edit_xml(add_blip("rIdBackupImage")),
                "ppt/slides/_rels/slide3.xml.rels": edit_xml(
                    add_rel("rIdBackupImage", "../media/backup.png")
                ),
            },
            additions={"ppt/media/backup.png": media},
        )

    def test_relationship_ids_and_part_names_may_differ_but_media_may_not(self) -> None:
        self.add_equivalent_media()
        equivalent = AUDIT.audit_backups(self.source, self.target, [(1, 3)])
        self.assertTrue(equivalent["ok"], equivalent)

        rewrite_package(
            self.target,
            additions={"ppt/media/backup.png": b"changed-media-content"},
        )
        changed = AUDIT.audit_backups(self.source, self.target, [(1, 3)])
        self.assertFalse(changed["ok"])
        codes = {item["code"] for item in changed["violations"]}
        self.assertIn("backup-content-mismatch", codes)
        self.assertIn("backup-dependency-mismatch", codes)

    def test_notes_slide_backlinks_are_normalized_but_note_text_is_not(self) -> None:
        notes_xml = FIXTURE.xml_bytes(
            ET.Element(FIXTURE.q(FIXTURE.P_NS, "notes"), {"label": "speaker note"})
        )

        def add_notes_rel(rel_id: str, target: str):
            def callback(root: ET.Element) -> None:
                ET.SubElement(
                    root,
                    FIXTURE.q(FIXTURE.REL_NS, "Relationship"),
                    {
                        "Id": rel_id,
                        "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide",
                        "Target": target,
                    },
                )

            return callback

        source_notes_rels = FIXTURE.relationships(
            [
                (
                    "rIdSlide",
                    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide",
                    "../slides/slide1.xml",
                )
            ]
        )
        backup_notes_rels = FIXTURE.relationships(
            [
                (
                    "rIdDifferentSlide",
                    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide",
                    "../slides/slide3.xml",
                )
            ]
        )
        rewrite_package(
            self.source,
            mutate={
                "ppt/slides/_rels/slide1.xml.rels": edit_xml(
                    add_notes_rel("rIdNotesA", "../notesSlides/sourceNotes.xml")
                )
            },
            additions={
                "ppt/notesSlides/sourceNotes.xml": notes_xml,
                "ppt/notesSlides/_rels/sourceNotes.xml.rels": source_notes_rels,
            },
        )
        rewrite_package(
            self.target,
            mutate={
                "ppt/slides/_rels/slide3.xml.rels": edit_xml(
                    add_notes_rel("rIdNotesB", "../notesSlides/backupNotes.xml")
                )
            },
            additions={
                "ppt/notesSlides/backupNotes.xml": notes_xml,
                "ppt/notesSlides/_rels/backupNotes.xml.rels": backup_notes_rels,
            },
        )
        equivalent = AUDIT.audit_backups(self.source, self.target, [(1, 3)])
        self.assertTrue(equivalent["ok"], equivalent)

        changed_notes = FIXTURE.xml_bytes(
            ET.Element(FIXTURE.q(FIXTURE.P_NS, "notes"), {"label": "changed note"})
        )
        rewrite_package(
            self.target,
            additions={"ppt/notesSlides/backupNotes.xml": changed_notes},
        )
        changed = AUDIT.audit_backups(self.source, self.target, [(1, 3)])
        self.assertFalse(changed["ok"])
        self.assertIn(
            "backup-dependency-mismatch",
            {item["code"] for item in changed["violations"]},
        )

    def test_shared_layout_target_identity_is_not_normalized_away(self) -> None:
        with zipfile.ZipFile(self.target, "r") as package:
            layout = package.read("ppt/slideLayouts/slideLayout1.xml")
            layout_rels = package.read(
                "ppt/slideLayouts/_rels/slideLayout1.xml.rels"
            )

        def point_to_second_layout(root: ET.Element) -> None:
            for rel in root.findall(FIXTURE.q(FIXTURE.REL_NS, "Relationship")):
                if rel.get("Type", "").endswith("/slideLayout"):
                    rel.set("Target", "../slideLayouts/slideLayout2.xml")

        rewrite_package(
            self.target,
            mutate={
                "ppt/slides/_rels/slide3.xml.rels": edit_xml(
                    point_to_second_layout
                )
            },
            additions={
                "ppt/slideLayouts/slideLayout2.xml": layout,
                "ppt/slideLayouts/_rels/slideLayout2.xml.rels": layout_rels,
            },
        )
        report = AUDIT.audit_backups(self.source, self.target, [(1, 3)])
        self.assertFalse(report["ok"])
        self.assertIn(
            "backup-dependency-mismatch",
            {item["code"] for item in report["violations"]},
        )

    def test_invalid_duplicate_and_missing_maps_fail_closed(self) -> None:
        with self.assertRaises(AUDIT.AuditError):
            AUDIT.parse_maps(["1:3", "2:3"])
        with self.assertRaises(AUDIT.AuditError):
            AUDIT.parse_maps(["not-a-map"])
        missing = AUDIT.audit_backups(self.source, self.target, [(99, 3)])
        self.assertFalse(missing["ok"])
        self.assertIn("missing-source-page", {item["code"] for item in missing["violations"]})

    def test_cli_json_and_exit_codes(self) -> None:
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        passed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(self.source),
                str(self.target),
                "--map",
                "1:3",
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
        rejected = subprocess.run(
            [sys.executable, str(SCRIPT), str(self.source), str(self.target), "--json"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
        self.assertEqual(passed.returncode, 0, passed.stderr)
        self.assertTrue(json.loads(passed.stdout)["ok"])
        self.assertEqual(rejected.returncode, 2, rejected.stderr)
        self.assertEqual(json.loads(rejected.stdout)["exit_code"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
