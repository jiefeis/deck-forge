#!/usr/bin/env python3
"""Rebase authorized slide-local PPTX content onto an untouched baseline.

This is a fail-closed recovery path for candidates produced by high-level PPTX
tools that render correctly but normalize slide IDs, hidden flags, relationships,
masters, layouts, or themes. The output package is copied from SOURCE; only the
selected source slide XML parts are changed.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import posixpath
import re
import sys
import tempfile
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Sequence

try:
    from lxml import etree
except ImportError:
    sys.exit(
        "transplant_pptx_slides: lxml required. "
        "Run check_env.py and use its reported Python."
    )


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from audit_pptx_structure import AuditError, build_manifest  # noqa: E402


P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
STRICT_R_NS = "http://purl.oclc.org/ooxml/officeDocument/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
NS = {"a": A_NS, "p": P_NS}
RELATIONSHIP_ATTRIBUTE_NAMESPACES = {R_NS, STRICT_R_NS}
SAFE_INTERNAL_RELATIONSHIP_SUFFIXES = ("/image", "/audio", "/video", "/media")
SHAPE_ID_COUPLED_RELATIONSHIP_SUFFIXES = (
    "/comments",
    "/tags",
    "/control",
    "/vmlDrawing",
)
UNSAFE_ACTIVE_RELATIONSHIP_SUFFIXES = (
    "/digital-signature/origin",
    "/digital-signature/signature",
    "/vbaProject",
)
UNSAFE_ACTIVE_PART_PREFIXES = (
    "_xmlsignatures/",
)
THEME_DEPENDENT_QNAMES = {
    f"{{{P_NS}}}ph",
    f"{{{P_NS}}}style",
    f"{{{A_NS}}}schemeClr",
    f"{{{A_NS}}}fontRef",
    f"{{{A_NS}}}fillRef",
    f"{{{A_NS}}}lnRef",
    f"{{{A_NS}}}effectRef",
}


class TransplantError(RuntimeError):
    """Raised when a minimal slide-local transplant cannot be proven safe."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_pages(spec: str) -> set[int]:
    pages: set[int] = set()
    for raw in spec.split(","):
        token = raw.strip()
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", token)
        if not match:
            raise TransplantError(f"invalid physical page range token: {token!r}")
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if start < 1 or end < start:
            raise TransplantError(f"invalid physical page range: {token!r}")
        pages.update(range(start, end + 1))
    return pages


def _parse_mapping(raw: str) -> tuple[int, int]:
    match = re.fullmatch(r"\s*(\d+)\s*:\s*(\d+)\s*", raw)
    if not match:
        raise TransplantError(
            f"invalid --map value {raw!r}; expected SOURCE_PAGE:CANDIDATE_PAGE"
        )
    source_page, candidate_page = map(int, match.groups())
    if source_page < 1 or candidate_page < 1:
        raise TransplantError(f"invalid --map value {raw!r}")
    return source_page, candidate_page


def _parse_expected_title(raw: str) -> tuple[int, str]:
    page_text, separator, title = raw.partition("=")
    if not separator or not page_text.strip().isdigit() or not title:
        raise TransplantError(
            f"invalid --expect-title value {raw!r}; expected SOURCE_PAGE=TITLE"
        )
    page = int(page_text.strip())
    if page < 1:
        raise TransplantError(f"invalid --expect-title page: {page}")
    return page, title


def _assert_package_integrity(
    archive: zipfile.ZipFile, label: str
) -> set[str]:
    names = [info.filename for info in archive.infolist()]
    duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
    if duplicates:
        raise TransplantError(
            f"{label} has duplicate ZIP entries: {', '.join(duplicates)}"
        )
    unsafe_names = [
        name
        for name in names
        if name.startswith(("/", "\\"))
        or "\\" in name
        or ".." in PurePosixPath(name).parts
    ]
    if unsafe_names:
        raise TransplantError(
            f"{label} has unsafe ZIP member paths: {', '.join(unsafe_names)}"
        )
    bad_part = archive.testzip()
    if bad_part:
        raise TransplantError(f"{label} ZIP integrity failure at {bad_part}")
    return set(names)


def _parse_xml(
    data: bytes,
    *,
    label: str,
    expected_root: str,
) -> etree._Element:
    parser = etree.XMLParser(
        remove_blank_text=False,
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        huge_tree=False,
    )
    try:
        root = etree.fromstring(data, parser)
    except etree.XMLSyntaxError as exc:
        raise TransplantError(f"invalid XML: {label}") from exc
    if root.getroottree().docinfo.doctype:
        raise TransplantError(f"DOCTYPE is not allowed in {label}")
    if root.tag != expected_root:
        raise TransplantError(
            f"unexpected XML root in {label}: {root.tag!r}; "
            f"expected {expected_root!r}"
        )
    return root


def _content_types(
    archive: zipfile.ZipFile,
    names: set[str],
    label: str,
) -> tuple[dict[str, str], dict[str, str]]:
    part = "[Content_Types].xml"
    if part not in names:
        raise TransplantError(f"{label} is missing {part}")
    root = _parse_xml(
        archive.read(part),
        label=f"{label}:{part}",
        expected_root=f"{{{CT_NS}}}Types",
    )
    defaults: dict[str, str] = {}
    overrides: dict[str, str] = {}
    for node in root:
        local = etree.QName(node).localname
        content_type = node.get("ContentType", "")
        if not content_type:
            raise TransplantError(f"missing ContentType in {label}:{part}")
        if local == "Default":
            extension = node.get("Extension", "").lower()
            if not extension or extension in defaults:
                raise TransplantError(
                    f"invalid or duplicate content-type default in {label}:{part}"
                )
            defaults[extension] = content_type
        elif local == "Override":
            part_name = node.get("PartName", "")
            if not part_name.startswith("/") or part_name in overrides:
                raise TransplantError(
                    f"invalid or duplicate content-type override in {label}:{part}"
                )
            overrides[part_name] = content_type
        else:
            raise TransplantError(
                f"unexpected content-type element in {label}:{part}: {local}"
            )
    return defaults, overrides


def _effective_content_type(
    part: str,
    content_types: tuple[dict[str, str], dict[str, str]],
) -> str:
    defaults, overrides = content_types
    override = overrides.get(f"/{part}")
    if override:
        return override
    suffix = PurePosixPath(part).suffix.lower().lstrip(".")
    return defaults.get(suffix, "")


def _assert_no_active_content(
    archive: zipfile.ZipFile,
    names: set[str],
    label: str,
    content_types: tuple[dict[str, str], dict[str, str]],
) -> None:
    unsafe_parts = sorted(
        name
        for name in names
        if name.lower().endswith("vbaproject.bin")
        or name.lower().endswith("origin.sigs")
        or name.startswith(UNSAFE_ACTIVE_PART_PREFIXES)
    )
    if unsafe_parts:
        raise TransplantError(
            f"{label} contains active or signed package parts: "
            + ", ".join(unsafe_parts)
        )
    defaults, overrides = content_types
    unsafe_types = sorted(
        value
        for value in [*defaults.values(), *overrides.values()]
        if "digital-signature" in value.lower()
        or "macroenabled" in value.lower()
        or "activex" in value.lower()
        or "vba" in value.lower()
    )
    if unsafe_types:
        raise TransplantError(
            f"{label} contains unsafe active/signature content types: "
            + ", ".join(unsafe_types)
        )
    for rels_part in sorted(name for name in names if name.endswith(".rels")):
        root = _parse_xml(
            archive.read(rels_part),
            label=f"{label}:{rels_part}",
            expected_root=f"{{{REL_NS}}}Relationships",
        )
        unsafe_rels = [
            node.get("Type", "")
            for node in root.findall(f"{{{REL_NS}}}Relationship")
            if node.get("Type", "").endswith(
                UNSAFE_ACTIVE_RELATIONSHIP_SUFFIXES
            )
        ]
        if unsafe_rels:
            raise TransplantError(
                f"{label} contains unsafe active/signature relationships in "
                f"{rels_part}: {', '.join(sorted(unsafe_rels))}"
            )


def _relationship_part(base_part: str) -> str:
    path = PurePosixPath(base_part)
    return str(path.parent / "_rels" / f"{path.name}.rels")


def _resolve_target(base_part: str, target: str) -> str:
    if target.startswith("/"):
        resolved = posixpath.normpath(target.lstrip("/"))
    else:
        resolved = posixpath.normpath(
            posixpath.join(posixpath.dirname(base_part), target)
        )
    if resolved == ".." or resolved.startswith("../"):
        raise TransplantError(
            f"relationship target escapes the package: {base_part} -> {target}"
        )
    return resolved


def _relationships(
    archive: zipfile.ZipFile,
    base_part: str,
    names: set[str],
) -> dict[str, dict[str, str]]:
    rels_part = _relationship_part(base_part)
    if rels_part not in names:
        return {}
    root = _parse_xml(
        archive.read(rels_part),
        label=rels_part,
        expected_root=f"{{{REL_NS}}}Relationships",
    )

    result: dict[str, dict[str, str]] = {}
    for node in root.findall(f"{{{REL_NS}}}Relationship"):
        rel_id = node.get("Id", "")
        if not rel_id or rel_id in result:
            raise TransplantError(
                f"missing or duplicate relationship id in {rels_part}: {rel_id!r}"
            )
        target = node.get("Target", "")
        mode = node.get("TargetMode", "")
        resolved = target if mode == "External" else _resolve_target(
            base_part, target
        )
        if mode != "External" and resolved not in names:
            raise TransplantError(
                f"{rels_part} points to missing package part: {resolved}"
            )
        result[rel_id] = {
            "id": rel_id,
            "type": node.get("Type", ""),
            "target": target,
            "mode": mode,
            "resolved": resolved,
        }
    return result


def _used_relationship_ids(
    element: etree._Element,
    known_relationship_ids: set[str],
) -> set[str]:
    used: set[str] = set()
    for node in element.iter():
        for attr_name, value in node.attrib.items():
            name = etree.QName(attr_name)
            if name.namespace in RELATIONSHIP_ATTRIBUTE_NAMESPACES and value:
                used.add(value)
            elif value in known_relationship_ids:
                raise TransplantError(
                    "relationship-like attribute uses an unsupported namespace: "
                    f"{attr_name!r}={value!r}"
                )
    return used


def _payload_match(
    candidate: zipfile.ZipFile,
    source: zipfile.ZipFile,
    candidate_rel: dict[str, str],
    source_rel: dict[str, str],
    candidate_names: set[str],
    source_names: set[str],
    candidate_content_types: tuple[dict[str, str], dict[str, str]],
    source_content_types: tuple[dict[str, str], dict[str, str]],
) -> bool:
    if candidate_rel["mode"] == "External":
        return candidate_rel["target"] == source_rel["target"]
    candidate_target = candidate_rel["resolved"]
    source_target = source_rel["resolved"]
    if candidate_target not in candidate_names or source_target not in source_names:
        return False
    candidate_type = _effective_content_type(
        candidate_target, candidate_content_types
    )
    source_type = _effective_content_type(source_target, source_content_types)
    if not candidate_type or candidate_type != source_type:
        return False
    candidate_dependency_rels = _relationship_part(candidate_target)
    source_dependency_rels = _relationship_part(source_target)
    if (
        candidate_dependency_rels in candidate_names
        or source_dependency_rels in source_names
    ):
        return False
    return _sha256(candidate.read(candidate_target)) == _sha256(
        source.read(source_target)
    )


def _map_relationship_ids(
    source: zipfile.ZipFile,
    candidate: zipfile.ZipFile,
    source_slide_part: str,
    candidate_slide_part: str,
    transplanted_element: etree._Element,
    source_names: set[str],
    candidate_names: set[str],
    source_content_types: tuple[dict[str, str], dict[str, str]],
    candidate_content_types: tuple[dict[str, str], dict[str, str]],
) -> dict[str, str]:
    source_rels = _relationships(source, source_slide_part, source_names)
    candidate_rels = _relationships(candidate, candidate_slide_part, candidate_names)
    used_ids = _used_relationship_ids(
        transplanted_element, set(candidate_rels)
    )
    if not used_ids:
        return {}
    mapping: dict[str, str] = {}

    for candidate_id in sorted(used_ids):
        candidate_rel = candidate_rels.get(candidate_id)
        if candidate_rel is None:
            raise TransplantError(
                f"{candidate_slide_part} uses missing relationship {candidate_id!r}"
            )
        if (
            candidate_rel["mode"] != "External"
            and not candidate_rel["type"].endswith(
                SAFE_INTERNAL_RELATIONSHIP_SUFFIXES
            )
        ):
            raise TransplantError(
                f"unsupported slide dependency for minimal transplant: "
                f"{candidate_rel['type']} -> {candidate_rel['target']}"
            )
        matches = [
            source_rel
            for source_rel in source_rels.values()
            if source_rel["type"] == candidate_rel["type"]
            and source_rel["mode"] == candidate_rel["mode"]
            and _payload_match(
                candidate,
                source,
                candidate_rel,
                source_rel,
                candidate_names,
                source_names,
                candidate_content_types,
                source_content_types,
            )
        ]
        if len(matches) != 1:
            detail = "no" if not matches else "ambiguous"
            raise TransplantError(
                f"{detail} source dependency match for {candidate_slide_part} "
                f"{candidate_id!r} ({candidate_rel['type']} -> "
                f"{candidate_rel['target']}); the candidate is not a "
                "slide-XML-only edit"
            )
        mapping[candidate_id] = matches[0]["id"]

    for node in transplanted_element.iter():
        for attr_name, value in list(node.attrib.items()):
            if (
                etree.QName(attr_name).namespace
                in RELATIONSHIP_ATTRIBUTE_NAMESPACES
                and value in mapping
            ):
                node.set(attr_name, mapping[value])
    output_refs = _used_relationship_ids(
        transplanted_element, set(source_rels)
    )
    unresolved = sorted(output_refs - set(source_rels))
    if unresolved:
        raise TransplantError(
            f"transplanted component has unresolved output relationships: "
            + ", ".join(unresolved)
        )
    return mapping


def _parse_slide(data: bytes, part: str) -> etree._Element:
    root = _parse_xml(
        data,
        label=part,
        expected_root=f"{{{P_NS}}}sld",
    )
    shape_ids = [
        node.get("id", "")
        for node in root.findall(".//p:cNvPr", NS)
    ]
    if (
        any(not shape_id.isdigit() for shape_id in shape_ids)
        or len(shape_ids) != len(set(shape_ids))
    ):
        raise TransplantError(
            f"{part} has missing, invalid, or duplicate shape IDs"
        )
    return root


def _replace_component(
    source_root: etree._Element,
    candidate_root: etree._Element,
) -> etree._Element:
    source_node = source_root.find("p:cSld/p:spTree", NS)
    candidate_node = candidate_root.find("p:cSld/p:spTree", NS)
    if source_node is None or candidate_node is None:
        raise TransplantError(
            "missing shape-tree in source or candidate slide"
        )
    parent = source_node.getparent()
    parent.replace(source_node, copy.deepcopy(candidate_node))
    return source_root


def _component_node(root: etree._Element) -> etree._Element:
    node = root.find("p:cSld/p:spTree", NS)
    if node is None:
        raise TransplantError("missing shape-tree in candidate slide")
    return node


def _assert_direct_visual_semantics(
    component_node: etree._Element,
    candidate_slide_part: str,
) -> None:
    dependencies = sorted(
        {
            etree.QName(node).localname
            for node in component_node.iter()
            if node.tag in THEME_DEPENDENT_QNAMES
            or (
                node.tag
                in {
                    f"{{{A_NS}}}latin",
                    f"{{{A_NS}}}ea",
                    f"{{{A_NS}}}cs",
                }
                and node.get("typeface", "").startswith("+")
            )
        }
    )
    if dependencies:
        raise TransplantError(
            f"{candidate_slide_part} shape-tree depends on layout/theme "
            f"semantics ({', '.join(dependencies)}); minimal rebase is unsafe"
        )


def _assert_component_safe(
    source: zipfile.ZipFile,
    source_root: etree._Element,
    source_slide_part: str,
    source_names: set[str],
) -> None:
    if source_root.find("p:timing", NS) is not None:
        raise TransplantError(
            f"{source_slide_part} has slide-local timing tied to shape IDs; "
            "shape-tree rebase is unsafe"
        )
    source_rels = _relationships(source, source_slide_part, source_names)
    coupled = [
        rel["type"]
        for rel in source_rels.values()
        if rel["type"].endswith(SHAPE_ID_COUPLED_RELATIONSHIP_SUFFIXES)
    ]
    if coupled:
        raise TransplantError(
            f"{source_slide_part} has shape-ID-coupled relationships: "
            + ", ".join(sorted(coupled))
        )


def _xml_bytes(root: etree._Element) -> bytes:
    return etree.tostring(
        root,
        encoding="UTF-8",
        xml_declaration=True,
        standalone=True,
        pretty_print=False,
    )


def transplant(
    source_path: Path,
    candidate_path: Path,
    output_path: Path,
    mappings: list[tuple[int, int]],
    *,
    component: str = "shape-tree",
    expected_titles: dict[int, str] | None = None,
    overwrite: bool = False,
    require_equal_counts: bool = False,
) -> dict[str, object]:
    """Transplant selected physical pages and return a validation report."""

    source_path = source_path.expanduser().resolve()
    candidate_path = candidate_path.expanduser().resolve()
    output_path = output_path.expanduser().resolve()
    expected_titles = expected_titles or {}

    if component != "shape-tree":
        raise TransplantError(
            "only --component shape-tree is supported; broader slide "
            "replacement cannot preserve shape-ID-coupled semantics"
        )
    if source_path == output_path or candidate_path == output_path:
        raise TransplantError("OUTPUT must differ from SOURCE and CANDIDATE")
    if (
        source_path.suffix.lower() != ".pptx"
        or candidate_path.suffix.lower() != ".pptx"
    ):
        raise TransplantError("SOURCE and CANDIDATE must be .pptx files")
    if output_path.suffix.lower() != ".pptx":
        raise TransplantError("OUTPUT must use the .pptx extension")
    if output_path.exists() and not overwrite:
        raise TransplantError(f"OUTPUT already exists: {output_path}")
    if not source_path.is_file() or not candidate_path.is_file():
        raise TransplantError("SOURCE and CANDIDATE must both be existing files")
    if not mappings:
        raise TransplantError("select at least one page with --pages or --map")

    source_pages = [source_page for source_page, _ in mappings]
    if len(source_pages) != len(set(source_pages)):
        raise TransplantError("each source physical page may be selected only once")

    try:
        source_manifest = build_manifest(source_path)
        candidate_manifest = build_manifest(candidate_path)
    except AuditError as exc:
        raise TransplantError(str(exc)) from exc
    if not source_manifest["integrity_ok"]:
        raise TransplantError(
            "SOURCE manifest has integrity warnings: "
            + "; ".join(
                str(item) for item in source_manifest["integrity_warnings"]
            )
        )
    if not candidate_manifest["integrity_ok"]:
        raise TransplantError(
            "CANDIDATE manifest has integrity warnings: "
            + "; ".join(
                str(item) for item in candidate_manifest["integrity_warnings"]
            )
        )
    if source_manifest["slide_size"] != candidate_manifest["slide_size"]:
        raise TransplantError("SOURCE and CANDIDATE slide sizes differ")
    if require_equal_counts and (
        source_manifest["slide_count"] != candidate_manifest["slide_count"]
    ):
        raise TransplantError(
            "--pages requires equal SOURCE and CANDIDATE slide counts; "
            "use explicit --map values when physical orders differ"
        )

    source_slides = source_manifest["slides"]
    candidate_slides = candidate_manifest["slides"]
    source_title_counts = Counter(
        str(slide["title"]) for slide in source_slides if slide["title"]
    )
    candidate_title_counts = Counter(
        str(slide["title"]) for slide in candidate_slides if slide["title"]
    )
    replacements: dict[str, bytes] = {}
    mapping_reports: list[dict[str, object]] = []

    with zipfile.ZipFile(source_path, "r") as source, zipfile.ZipFile(
        candidate_path, "r"
    ) as candidate:
        source_names = _assert_package_integrity(source, "SOURCE")
        candidate_names = _assert_package_integrity(candidate, "CANDIDATE")
        source_content_types = _content_types(
            source, source_names, "SOURCE"
        )
        candidate_content_types = _content_types(
            candidate, candidate_names, "CANDIDATE"
        )
        _assert_no_active_content(
            source, source_names, "SOURCE", source_content_types
        )
        _assert_no_active_content(
            candidate,
            candidate_names,
            "CANDIDATE",
            candidate_content_types,
        )

        for source_page, candidate_page in mappings:
            if (
                source_page > len(source_slides)
                or candidate_page > len(candidate_slides)
            ):
                raise TransplantError(
                    f"page mapping {source_page}:{candidate_page} is out of range "
                    f"(source={len(source_slides)}, candidate={len(candidate_slides)})"
                )
            source_slide = source_slides[source_page - 1]
            candidate_slide = candidate_slides[candidate_page - 1]
            expected = expected_titles.get(source_page)
            if expected and (
                source_slide["title"] != expected
                or candidate_slide["title"] != expected
            ):
                raise TransplantError(
                    f"title assertion failed for mapping {source_page}:{candidate_page}: "
                    f"source={source_slide['title']!r}, "
                    f"candidate={candidate_slide['title']!r}, expected={expected!r}"
                )
            source_title = str(source_slide["title"])
            candidate_title = str(candidate_slide["title"])
            stable_id_match = (
                source_slide["slide_id"] == candidate_slide["slide_id"]
            )
            unique_title_match = (
                bool(source_title)
                and source_title == candidate_title
                and source_title_counts[source_title] == 1
                and candidate_title_counts[candidate_title] == 1
            )
            explicit_title_match = bool(expected) and (
                source_title == expected == candidate_title
            )
            if stable_id_match:
                identity_evidence = "stable-slide-id"
            elif unique_title_match:
                identity_evidence = "unique-exact-title"
            elif explicit_title_match:
                identity_evidence = "explicit-title-assertion"
            else:
                raise TransplantError(
                    f"cannot prove page identity for mapping "
                    f"{source_page}:{candidate_page}; stable IDs differ and "
                    "there is no unique exact title match"
                )

            source_part = str(source_slide["part"])
            candidate_part = str(candidate_slide["part"])
            if not source_part or not candidate_part:
                raise TransplantError(
                    f"unresolved slide part for mapping {source_page}:{candidate_page}"
                )
            source_root = _parse_slide(source.read(source_part), source_part)
            candidate_root = _parse_slide(candidate.read(candidate_part), candidate_part)
            _assert_component_safe(
                source,
                source_root,
                source_part,
                source_names,
            )
            candidate_component = copy.deepcopy(
                _component_node(candidate_root)
            )
            _assert_direct_visual_semantics(
                candidate_component, candidate_part
            )
            relationship_map = _map_relationship_ids(
                source,
                candidate,
                source_part,
                candidate_part,
                candidate_component,
                source_names,
                candidate_names,
                source_content_types,
                candidate_content_types,
            )
            replacement_root = _replace_component(
                source_root,
                candidate_root,
            )
            destination = _component_node(replacement_root)
            # _replace_component deep-copies separately; apply the proven
            # relationship-id rewrites to the inserted element.
            for node in destination.iter():
                for attr_name, value in list(node.attrib.items()):
                    if (
                        etree.QName(attr_name).namespace
                        in RELATIONSHIP_ATTRIBUTE_NAMESPACES
                        and value in relationship_map
                    ):
                        node.set(attr_name, relationship_map[value])

            replacement_bytes = _xml_bytes(replacement_root)
            _parse_slide(replacement_bytes, source_part)
            replacements[source_part] = replacement_bytes
            mapping_reports.append(
                {
                    "source_page": source_page,
                    "candidate_page": candidate_page,
                    "source_slide_id": source_slide["slide_id"],
                    "candidate_slide_id": candidate_slide["slide_id"],
                    "source_hidden": source_slide["hidden"],
                    "candidate_hidden": candidate_slide["hidden"],
                    "source_title": source_slide["title"],
                    "candidate_title": candidate_slide["title"],
                    "identity_evidence": identity_evidence,
                    "source_part": source_part,
                    "candidate_part": candidate_part,
                    "relationship_map": relationship_map,
                }
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        source_infos = list(source.infolist())
        source_payloads = {
            info.filename: source.read(info.filename) for info in source_infos
        }
        handle = tempfile.NamedTemporaryFile(
            prefix=f".{output_path.stem}.",
            suffix=".pptx",
            dir=output_path.parent,
            delete=False,
        )
        temporary_path = Path(handle.name)
        handle.close()
        try:
            with zipfile.ZipFile(temporary_path, "w") as output:
                output.comment = source.comment
                for info in source_infos:
                    output.writestr(
                        copy.copy(info),
                        replacements.get(
                            info.filename,
                            source_payloads[info.filename],
                        ),
                    )
            with zipfile.ZipFile(temporary_path, "r") as output:
                output_names = _assert_package_integrity(output, "OUTPUT")
                if output_names != source_names:
                    raise TransplantError("OUTPUT part set differs from SOURCE")
                if output.comment != source.comment:
                    raise TransplantError("OUTPUT ZIP comment differs from SOURCE")
                unexpected = [
                    name
                    for name in sorted(source_names - set(replacements))
                    if _sha256(output.read(name))
                    != _sha256(source_payloads[name])
                ]
                if unexpected:
                    raise TransplantError(
                        "OUTPUT changed unauthorized package parts: "
                        + ", ".join(unexpected)
                    )
            try:
                temporary_manifest = build_manifest(temporary_path)
            except AuditError as exc:
                raise TransplantError(str(exc)) from exc
            if not temporary_manifest["integrity_ok"]:
                raise TransplantError(
                    "OUTPUT manifest has integrity warnings: "
                    + "; ".join(
                        str(item)
                        for item in temporary_manifest[
                            "integrity_warnings"
                        ]
                    )
                )
            invariant_checks = {
                "slide_count": temporary_manifest["slide_count"]
                == source_manifest["slide_count"],
                "slide_size": temporary_manifest["slide_size"]
                == source_manifest["slide_size"],
                "slide_order": temporary_manifest["slide_order"]
                == source_manifest["slide_order"],
                "hidden_state": [
                    slide["hidden"] for slide in temporary_manifest["slides"]
                ]
                == [slide["hidden"] for slide in source_manifest["slides"]],
                "shared_parts": temporary_manifest["shared_parts"]
                == source_manifest["shared_parts"],
            }
            failed = [name for name, passed in invariant_checks.items() if not passed]
            if failed:
                raise TransplantError(
                    "OUTPUT violated baseline package invariants: "
                    + ", ".join(failed)
                )
            if overwrite:
                os.replace(temporary_path, output_path)
            else:
                try:
                    os.link(temporary_path, output_path)
                except FileExistsError as exc:
                    raise TransplantError(
                        f"OUTPUT appeared during validation: {output_path}"
                    ) from exc
                except OSError as exc:
                    raise TransplantError(
                        "could not publish OUTPUT without overwrite; "
                        "hard-link creation failed"
                    ) from exc
                temporary_path.unlink()
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    return {
        "status": "ok",
        "source": str(source_path),
        "candidate": str(candidate_path),
        "output": str(output_path),
        "component": component,
        "mappings": mapping_reports,
        "changed_parts": sorted(replacements),
        "invariants": invariant_checks,
        "source_sha256": _sha256(source_path.read_bytes()),
        "candidate_sha256": _sha256(candidate_path.read_bytes()),
        "output_sha256": _sha256(output_path.read_bytes()),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("output", type=Path)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--pages",
        action="append",
        default=[],
        metavar="RANGE",
        help="same physical pages in SOURCE and CANDIDATE, e.g. 2,4,31,41",
    )
    selection.add_argument(
        "--map",
        action="append",
        default=[],
        metavar="SOURCE:CANDIDATE",
        help="explicit physical-page mapping; repeat as needed",
    )
    parser.add_argument(
        "--component",
        choices=("shape-tree",),
        default="shape-tree",
        help="safe slide-local XML component (only shape-tree is supported)",
    )
    parser.add_argument(
        "--expect-title",
        action="append",
        default=[],
        metavar="SOURCE_PAGE=TITLE",
        help="assert the exact title on both mapped pages",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        mappings: list[tuple[int, int]] = []
        for spec in args.pages:
            mappings.extend((page, page) for page in sorted(_parse_pages(spec)))
        mappings.extend(_parse_mapping(raw) for raw in args.map)
        expected_titles = dict(
            _parse_expected_title(raw) for raw in args.expect_title
        )
        report = transplant(
            args.source,
            args.candidate,
            args.output,
            mappings,
            component=args.component,
            expected_titles=expected_titles,
            overwrite=args.overwrite,
            require_equal_counts=bool(args.pages),
        )
    except (OSError, zipfile.BadZipFile, TransplantError) as exc:
        if args.json:
            print(
                json.dumps(
                    {"status": "FAIL", "error": str(exc)},
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(f"transplant_pptx_slides: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("PPTX SLIDE TRANSPLANT")
        print(f"Source: {report['source']}")
        print(f"Candidate: {report['candidate']}")
        print(f"Output: {report['output']}")
        print(f"Component: {report['component']}")
        for item in report["mappings"]:
            print(
                "  "
                f"{item['source_page']}:{item['candidate_page']} "
                f"{item['source_title']!r} "
                f"rels={item['relationship_map']}"
            )
        print(f"Changed parts: {', '.join(report['changed_parts'])}")
        print("Invariants: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
