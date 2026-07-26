#!/usr/bin/env python3
"""Regression tests for scripts/transplant_pptx_slides.py."""

from __future__ import annotations

import importlib.util
import os
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
    "deckforge_transplant_fixture",
    ROOT / "tests" / "test_audit_pptx_structure.py",
)
TRANSPLANT = load_module(
    "transplant_pptx_slides",
    ROOT / "scripts" / "transplant_pptx_slides.py",
)


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


def add_image_dependency(
    path: Path,
    *,
    slide_part: str,
    rel_id: str,
    media_part: str,
    payload: bytes,
) -> None:
    rels_part = slide_part.replace("/slides/", "/slides/_rels/") + ".rels"

    def mutate_slide(data: bytes) -> bytes:
        root = ET.fromstring(data)
        shape_props = root.find(
            ".//p:sp/p:spPr",
            {"p": FIXTURE.P_NS, "a": FIXTURE.A_NS},
        )
        ET.SubElement(
            shape_props,
            FIXTURE.q(FIXTURE.A_NS, "blip"),
            {FIXTURE.q(FIXTURE.R_NS, "embed"): rel_id},
        )
        return FIXTURE.xml_bytes(root)

    def mutate_rels(data: bytes) -> bytes:
        root = ET.fromstring(data)
        base = Path(slide_part).parent.as_posix()
        target = posix_relative(base, media_part)
        ET.SubElement(
            root,
            FIXTURE.q(FIXTURE.REL_NS, "Relationship"),
            {
                "Id": rel_id,
                "Type": (
                    "http://schemas.openxmlformats.org/officeDocument/"
                    "2006/relationships/image"
                ),
                "Target": target,
            },
        )
        return FIXTURE.xml_bytes(root)

    def mutate_content_types(data: bytes) -> bytes:
        root = ET.fromstring(data)
        existing = {
            node.get("Extension", "").lower()
            for node in root.findall(
                FIXTURE.q(FIXTURE.CT_NS, "Default")
            )
        }
        if "png" not in existing:
            ET.SubElement(
                root,
                FIXTURE.q(FIXTURE.CT_NS, "Default"),
                {
                    "Extension": "png",
                    "ContentType": "image/png",
                },
            )
        return FIXTURE.xml_bytes(root)

    rewrite_package(
        path,
        mutate={
            slide_part: mutate_slide,
            rels_part: mutate_rels,
            "[Content_Types].xml": mutate_content_types,
        },
        additions={media_part: payload},
    )


def posix_relative(base_dir: str, target: str) -> str:
    base_parts = Path(base_dir).as_posix().split("/")
    target_parts = Path(target).as_posix().split("/")
    common = 0
    for left, right in zip(base_parts, target_parts):
        if left != right:
            break
        common += 1
    return "/".join([".."] * (len(base_parts) - common) + target_parts[common:])


def package_parts(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path, "r") as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def remove_placeholder_dependencies(path: Path) -> None:
    with zipfile.ZipFile(path, "r") as archive:
        slide_parts = [
            name
            for name in archive.namelist()
            if name.startswith("ppt/slides/slide")
            and name.endswith(".xml")
        ]

    def make_direct(data: bytes) -> bytes:
        root = ET.fromstring(data)
        for parent in root.iter():
            for child in list(parent):
                if child.tag == FIXTURE.q(FIXTURE.P_NS, "ph"):
                    parent.remove(child)
        return FIXTURE.xml_bytes(root)

    rewrite_package(
        path,
        mutate={part: make_direct for part in slide_parts},
    )


class TransplantPptxSlidesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="deckforge-transplant-")
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_source_and_candidate(
        self,
        *,
        direct_candidate: bool = True,
    ) -> tuple[Path, Path]:
        source = FIXTURE.make_pptx(
            self.root / "source.pptx",
            order=(257, 256, 258),
            hidden=frozenset({257}),
            texts={
                256: ["Target title", "Source body"],
                257: ["Hidden title", "Hidden body"],
                258: ["Untouched title", "Untouched body"],
            },
            shared_marker="source-theme",
        )
        candidate = FIXTURE.make_pptx(
            self.root / "candidate.pptx",
            order=(300, 301, 302),
            texts={
                300: ["Hidden title", "Candidate changed hidden state"],
                301: ["Target title", "Candidate body"],
                302: ["Untouched title", "Candidate changed untouched page"],
            },
            shared_marker="candidate-normalized-theme",
        )
        if direct_candidate:
            remove_placeholder_dependencies(candidate)
        return source, candidate

    def test_true_order_transplant_preserves_baseline_package_invariants(self) -> None:
        source, candidate = self.make_source_and_candidate()
        output = self.root / "output.pptx"
        report = TRANSPLANT.transplant(
            source,
            candidate,
            output,
            [(2, 2)],
            expected_titles={2: "Target title"},
        )

        manifest = FIXTURE.AUDIT.build_manifest(output)
        self.assertEqual(manifest["slide_order"], [257, 256, 258])
        self.assertEqual(
            [slide["hidden"] for slide in manifest["slides"]],
            [True, False, False],
        )
        self.assertEqual(
            manifest["slides"][1]["text_boxes"][1]["text"],
            "Candidate body",
        )
        self.assertEqual(
            manifest["slides"][2]["text_boxes"][1]["text"],
            "Untouched body",
        )
        self.assertTrue(all(report["invariants"].values()))

        source_parts = package_parts(source)
        output_parts = package_parts(output)
        changed = set(report["changed_parts"])
        self.assertEqual(source_parts.keys(), output_parts.keys())
        for name in source_parts:
            if name not in changed:
                self.assertEqual(source_parts[name], output_parts[name], name)

    def test_image_relationship_id_is_remapped_by_type_and_payload_hash(self) -> None:
        source, candidate = self.make_source_and_candidate()
        source_manifest = FIXTURE.AUDIT.build_manifest(source)
        candidate_manifest = FIXTURE.AUDIT.build_manifest(candidate)
        source_part = source_manifest["slides"][1]["part"]
        candidate_part = candidate_manifest["slides"][1]["part"]
        payload = b"same-image-payload"
        add_image_dependency(
            source,
            slide_part=source_part,
            rel_id="rIdSourceImage",
            media_part="ppt/media/image1.png",
            payload=payload,
        )
        add_image_dependency(
            candidate,
            slide_part=candidate_part,
            rel_id="rIdCandidateImage",
            media_part="ppt/media/image99.png",
            payload=payload,
        )

        output = self.root / "image-output.pptx"
        report = TRANSPLANT.transplant(source, candidate, output, [(2, 2)])
        with zipfile.ZipFile(output, "r") as archive:
            slide_xml = archive.read(source_part)
            source_rels = archive.read(
                source_part.replace("/slides/", "/slides/_rels/") + ".rels"
            )
        self.assertIn(b"rIdSourceImage", slide_xml)
        self.assertNotIn(b"rIdCandidateImage", slide_xml)
        self.assertIn(b"rIdSourceImage", source_rels)
        self.assertEqual(
            report["mappings"][0]["relationship_map"],
            {"rIdCandidateImage": "rIdSourceImage"},
        )

    def test_unmatched_dependency_fails_without_overwriting_existing_output(self) -> None:
        source, candidate = self.make_source_and_candidate()
        source_part = FIXTURE.AUDIT.build_manifest(source)["slides"][1]["part"]
        candidate_part = FIXTURE.AUDIT.build_manifest(candidate)["slides"][1]["part"]
        add_image_dependency(
            source,
            slide_part=source_part,
            rel_id="rIdSourceImage",
            media_part="ppt/media/image1.png",
            payload=b"source-image",
        )
        add_image_dependency(
            candidate,
            slide_part=candidate_part,
            rel_id="rIdCandidateImage",
            media_part="ppt/media/image99.png",
            payload=b"different-candidate-image",
        )
        output = self.root / "existing.pptx"
        output.write_bytes(b"keep-me")

        with self.assertRaises(TRANSPLANT.TransplantError):
            TRANSPLANT.transplant(
                source,
                candidate,
                output,
                [(2, 2)],
                overwrite=True,
            )
        self.assertEqual(output.read_bytes(), b"keep-me")

    def test_shape_tree_mode_rejects_source_timing_bound_to_shape_ids(self) -> None:
        source, candidate = self.make_source_and_candidate()
        source_part = FIXTURE.AUDIT.build_manifest(source)["slides"][1]["part"]

        def add_timing(data: bytes) -> bytes:
            root = ET.fromstring(data)
            ET.SubElement(root, FIXTURE.q(FIXTURE.P_NS, "timing"))
            return FIXTURE.xml_bytes(root)

        rewrite_package(source, mutate={source_part: add_timing})
        with self.assertRaisesRegex(
            TRANSPLANT.TransplantError,
            "timing tied to shape IDs",
        ):
            TRANSPLANT.transplant(
                source,
                candidate,
                self.root / "timing-output.pptx",
                [(2, 2)],
            )

    def test_same_page_mode_requires_equal_counts_but_explicit_map_can_rebase(self) -> None:
        source, _ = self.make_source_and_candidate()
        candidate = FIXTURE.make_pptx(
            self.root / "short-candidate.pptx",
            order=(300, 301),
            texts={
                300: ["Hidden title", "Other"],
                301: ["Target title", "Candidate body"],
            },
        )
        remove_placeholder_dependencies(candidate)
        with self.assertRaisesRegex(
            TRANSPLANT.TransplantError,
            "--pages requires equal",
        ):
            TRANSPLANT.transplant(
                source,
                candidate,
                self.root / "same-page-output.pptx",
                [(2, 2)],
                require_equal_counts=True,
            )
        output = self.root / "mapped-output.pptx"
        TRANSPLANT.transplant(source, candidate, output, [(2, 2)])
        self.assertTrue(output.is_file())

    def test_title_assertion_catches_wrong_page_mapping(self) -> None:
        source, candidate = self.make_source_and_candidate()
        with self.assertRaisesRegex(
            TRANSPLANT.TransplantError,
            "title assertion failed",
        ):
            TRANSPLANT.transplant(
                source,
                candidate,
                self.root / "wrong-map.pptx",
                [(2, 1)],
                expected_titles={2: "Target title"},
            )

    def test_output_must_be_a_pptx(self) -> None:
        source, candidate = self.make_source_and_candidate()
        with self.assertRaisesRegex(
            TRANSPLANT.TransplantError,
            "OUTPUT must use the .pptx extension",
        ):
            TRANSPLANT.transplant(
                source,
                candidate,
                self.root / "not-a-deck.zip",
                [(2, 2)],
            )

    def test_broader_component_modes_are_rejected(self) -> None:
        source, candidate = self.make_source_and_candidate()
        with self.assertRaisesRegex(
            TRANSPLANT.TransplantError,
            "only --component shape-tree is supported",
        ):
            TRANSPLANT.transplant(
                source,
                candidate,
                self.root / "full-slide.pptx",
                [(2, 2)],
                component="slide",
            )

    def test_same_count_reordered_candidate_fails_page_identity(self) -> None:
        source, _ = self.make_source_and_candidate()
        candidate = FIXTURE.make_pptx(
            self.root / "reordered-candidate.pptx",
            order=(300, 302, 301),
            texts={
                300: ["Hidden title", "Candidate hidden"],
                301: ["Target title", "Candidate body"],
                302: ["Untouched title", "Candidate untouched"],
            },
        )
        remove_placeholder_dependencies(candidate)
        with self.assertRaisesRegex(
            TRANSPLANT.TransplantError,
            "cannot prove page identity",
        ):
            TRANSPLANT.transplant(
                source,
                candidate,
                self.root / "reordered-output.pptx",
                [(2, 2)],
                require_equal_counts=True,
            )

    def test_theme_dependent_candidate_shape_tree_is_rejected(self) -> None:
        source, candidate = self.make_source_and_candidate(
            direct_candidate=False
        )
        with self.assertRaisesRegex(
            TRANSPLANT.TransplantError,
            "depends on layout/theme semantics",
        ):
            TRANSPLANT.transplant(
                source,
                candidate,
                self.root / "theme-dependent.pptx",
                [(2, 2)],
                expected_titles={2: "Target title"},
            )

    def test_manifest_integrity_warning_is_rejected(self) -> None:
        source, candidate = self.make_source_and_candidate()

        def duplicate_slide_id(data: bytes) -> bytes:
            root = ET.fromstring(data)
            nodes = root.findall(
                ".//p:sldId",
                {"p": FIXTURE.P_NS},
            )
            nodes[1].set("id", nodes[0].get("id"))
            return FIXTURE.xml_bytes(root)

        rewrite_package(
            candidate,
            mutate={"ppt/presentation.xml": duplicate_slide_id},
        )
        with self.assertRaisesRegex(
            TRANSPLANT.TransplantError,
            "CANDIDATE manifest has integrity warnings",
        ):
            TRANSPLANT.transplant(
                source,
                candidate,
                self.root / "warning-output.pptx",
                [(2, 2)],
            )

    def test_relationship_doctype_is_rejected(self) -> None:
        source, candidate = self.make_source_and_candidate()

        def add_doctype(data: bytes) -> bytes:
            declaration_end = data.find(b"?>")
            self.assertGreaterEqual(declaration_end, 0)
            return (
                data[: declaration_end + 2]
                + b'\n<!DOCTYPE Relationships [<!ENTITY x "x">]>'
                + data[declaration_end + 2 :]
            )

        rewrite_package(
            candidate,
            mutate={
                "ppt/slides/_rels/slide2.xml.rels": add_doctype
            },
        )
        with self.assertRaisesRegex(
            TRANSPLANT.TransplantError,
            "DOCTYPE is not allowed",
        ):
            TRANSPLANT.transplant(
                source,
                candidate,
                self.root / "doctype-output.pptx",
                [(2, 2)],
            )

    def test_zip_comment_is_preserved(self) -> None:
        source, candidate = self.make_source_and_candidate()
        with zipfile.ZipFile(source, "a") as archive:
            archive.comment = b"baseline-package-comment"
        output = self.root / "comment-output.pptx"
        TRANSPLANT.transplant(source, candidate, output, [(2, 2)])
        with zipfile.ZipFile(output, "r") as archive:
            self.assertEqual(archive.comment, b"baseline-package-comment")


if __name__ == "__main__":
    unittest.main()
