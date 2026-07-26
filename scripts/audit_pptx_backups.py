#!/usr/bin/env python3
"""Verify hidden PPTX backup slides against their source originals.

Each explicit SOURCE_PAGE:BACKUP_PAGE pair is compared semantically. Slide-part
identity, relationship ids, and the target slide's hidden flag are normalized;
text, styles, geometry, shape order, relationships, and dependent content are
not. Inputs are read-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Iterable, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from audit_pptx_structure import AuditError, build_manifest  # noqa: E402


R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
STOP_RELATIONSHIP_SUFFIXES = ("/slide",)
SHARED_IDENTITY_SUFFIXES = ("/slideLayout", "/slideMaster", "/theme", "/notesMaster")


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_maps(values: Iterable[str]) -> list[tuple[int, int]]:
    mappings: list[tuple[int, int]] = []
    sources: set[int] = set()
    targets: set[int] = set()
    for raw in values:
        match = re.fullmatch(r"\s*(\d+)\s*:\s*(\d+)\s*", raw)
        if not match:
            raise AuditError(f"invalid backup map {raw!r}; expected SOURCE_PAGE:BACKUP_PAGE")
        source, target = map(int, match.groups())
        if source < 1 or target < 1:
            raise AuditError("backup-map page numbers must be positive")
        if source in sources:
            raise AuditError(f"source page {source} is mapped more than once")
        if target in targets:
            raise AuditError(f"backup page {target} is mapped more than once")
        sources.add(source)
        targets.add(target)
        mappings.append((source, target))
    if not mappings:
        raise AuditError("at least one --map SOURCE_PAGE:BACKUP_PAGE is required")
    return mappings


def _parse_xml(data: bytes, part: str) -> ET.Element:
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise AuditError(f"invalid XML in {part}: {exc}") from exc


def _rels_part(part: str) -> str:
    return posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")


def _resolve_target(source_part: str, target: str) -> str:
    target = target.split("#", 1)[0]
    if target.startswith("/"):
        return posixpath.normpath(target.lstrip("/"))
    return posixpath.normpath(posixpath.join(posixpath.dirname(source_part), target))


def _content_type(zf: zipfile.ZipFile, part: str) -> str:
    content_types_part = "[Content_Types].xml"
    if content_types_part not in zf.namelist():
        raise AuditError("PPTX package is missing [Content_Types].xml")
    root = _parse_xml(zf.read(content_types_part), content_types_part)
    normalized = "/" + part.lstrip("/")
    for override in root.findall(f"{{{CT_NS}}}Override"):
        if override.get("PartName", "") == normalized:
            return override.get("ContentType", "")
    extension = posixpath.splitext(part)[1].lstrip(".").casefold()
    for default in root.findall(f"{{{CT_NS}}}Default"):
        if default.get("Extension", "").casefold() == extension:
            return default.get("ContentType", "")
    return ""


def _canonical_tree(
    element: ET.Element,
    relationship_tokens: dict[str, str],
    *,
    strip_hidden: bool,
    root: bool = True,
) -> object:
    attrs: list[list[str]] = []
    for key, value in sorted(element.attrib.items()):
        local = key.rsplit("}", 1)[-1]
        namespace = key[1:].split("}", 1)[0] if key.startswith("{") else ""
        if strip_hidden and root and local == "show":
            continue
        if namespace == R_NS:
            token = relationship_tokens.get(value)
            if token is None:
                raise AuditError(f"XML references missing relationship id {value!r}")
            value = token
        attrs.append([key, value])
    text = element.text or ""
    if text.isspace():
        text = ""
    children = [
        _canonical_tree(
            child,
            relationship_tokens,
            strip_hidden=False,
            root=False,
        )
        for child in list(element)
    ]
    return [element.tag, attrs, text, children]


def _part_signature(
    zf: zipfile.ZipFile,
    part: str,
    stack: tuple[str, ...],
) -> str:
    names = set(zf.namelist())
    if part not in names:
        raise AuditError(f"relationship target is missing: {part}")
    if part in stack:
        return "cycle:" + posixpath.splitext(part)[1].lower()
    data = zf.read(part)
    content_type = _content_type(zf, part)
    if not part.endswith((".xml", ".rels")):
        return "bin:" + _sha256_bytes(
            json.dumps(
                [content_type, posixpath.splitext(part)[1].casefold(), _sha256_bytes(data)],
                separators=(",", ":"),
            ).encode("utf-8")
        )
    if part.endswith(".rels"):
        raise AuditError(f"relationship part cannot be a direct content target: {part}")
    tokens, descriptors = _relationship_tokens(zf, part, (*stack, part))
    root = _parse_xml(data, part)
    payload = {
        "content_type": content_type,
        "xml": _canonical_tree(root, tokens, strip_hidden=False),
        "relationships": sorted(descriptors),
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "xml:" + _sha256_bytes(encoded)


def _relationship_tokens(
    zf: zipfile.ZipFile,
    source_part: str,
    stack: tuple[str, ...],
) -> tuple[dict[str, str], list[str]]:
    rels_part = _rels_part(source_part)
    if rels_part not in zf.namelist():
        return {}, []
    root = _parse_xml(zf.read(rels_part), rels_part)
    tokens: dict[str, str] = {}
    descriptors: list[str] = []
    for rel in root.findall(f"{{{REL_NS}}}Relationship"):
        rel_id = rel.get("Id", "")
        if not rel_id or rel_id in tokens:
            raise AuditError(f"duplicate or empty relationship id in {rels_part}: {rel_id!r}")
        rel_type = rel.get("Type", "")
        mode = rel.get("TargetMode", "")
        target = rel.get("Target", "")
        if mode.lower() == "external":
            target_signature = "external:" + target
        elif rel_type.endswith(STOP_RELATIONSHIP_SUFFIXES):
            target_signature = "identity-reference:" + rel_type.rsplit("/", 1)[-1]
        elif source_part.startswith("ppt/slideMasters/") and rel_type.endswith("/slideLayout"):
            target_signature = "master-layout-backlink"
        else:
            if not target:
                raise AuditError(f"empty relationship target for {rel_id} in {rels_part}")
            resolved = _resolve_target(source_part, target)
            target_signature = _part_signature(zf, resolved, stack)
            if rel_type.endswith(SHARED_IDENTITY_SUFFIXES):
                target_signature = "shared-path:" + resolved + ":" + target_signature
        descriptor = json.dumps(
            [rel_type, mode.lower(), target_signature],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        token = "rel:" + _sha256_bytes(descriptor.encode("utf-8"))
        tokens[rel_id] = token
        descriptors.append(token)
    return tokens, descriptors


def _slide_signature(zf: zipfile.ZipFile, slide_part: str) -> tuple[str, list[str]]:
    data = zf.read(slide_part)
    tokens, descriptors = _relationship_tokens(zf, slide_part, (slide_part,))
    root = _parse_xml(data, slide_part)
    payload = {
        "slide": _canonical_tree(root, tokens, strip_hidden=True),
        "relationships": sorted(descriptors),
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(encoded), sorted(descriptors)


def audit_backups(
    source: Path,
    target: Path,
    mappings: Sequence[tuple[int, int]],
) -> dict[str, object]:
    source = source.expanduser().resolve()
    target = target.expanduser().resolve()
    if not source.is_file() or not target.is_file():
        raise AuditError("source and target PPTX files must exist")
    if not mappings:
        raise AuditError("at least one backup mapping is required")
    if any(source_page < 1 or backup_page < 1 for source_page, backup_page in mappings):
        raise AuditError("backup-map page numbers must be positive")
    if len({pair[0] for pair in mappings}) != len(mappings):
        raise AuditError("source pages in backup mappings must be unique")
    if len({pair[1] for pair in mappings}) != len(mappings):
        raise AuditError("backup pages in backup mappings must be unique")

    source_hash = _sha256_path(source)
    target_hash = _sha256_path(target)
    source_manifest = build_manifest(source)
    target_manifest = build_manifest(target)
    violations: list[dict[str, object]] = []
    pairs: list[dict[str, object]] = []
    for side, manifest in (("source", source_manifest), ("target", target_manifest)):
        if not manifest["integrity_ok"]:
            for warning in manifest["integrity_warnings"]:
                violations.append({"code": f"{side}-integrity-warning", **warning})

    source_slides = {int(slide["page"]): slide for slide in source_manifest["slides"]}
    target_slides = {int(slide["page"]): slide for slide in target_manifest["slides"]}
    with zipfile.ZipFile(source, "r") as source_zip, zipfile.ZipFile(target, "r") as target_zip:
        for source_page, backup_page in mappings:
            original = source_slides.get(source_page)
            backup = target_slides.get(backup_page)
            if original is None or backup is None:
                code = "missing-source-page" if original is None else "missing-backup-page"
                item = {
                    "source_page": source_page,
                    "backup_page": backup_page,
                    "code": code,
                    "identical": False,
                    "hidden": bool(backup["hidden"]) if backup else None,
                }
                pairs.append(item)
                violations.append(item.copy())
                continue

            pair_violations: list[str] = []
            if not bool(backup["hidden"]):
                pair_violations.append("backup-not-hidden")
            source_signature, source_relationships = _slide_signature(
                source_zip, str(original["part"])
            )
            backup_signature, backup_relationships = _slide_signature(
                target_zip, str(backup["part"])
            )
            if source_signature != backup_signature:
                pair_violations.append("backup-content-mismatch")
            if Counter(source_relationships) != Counter(backup_relationships):
                pair_violations.append("backup-dependency-mismatch")
            item = {
                "source_page": source_page,
                "backup_page": backup_page,
                "source_slide_id": original["slide_id"],
                "backup_slide_id": backup["slide_id"],
                "hidden": bool(backup["hidden"]),
                "source_signature": source_signature,
                "backup_signature": backup_signature,
                "identical": not pair_violations,
                "violations": pair_violations,
            }
            pairs.append(item)
            for code in pair_violations:
                violations.append(
                    {
                        "code": code,
                        "source_page": source_page,
                        "backup_page": backup_page,
                    }
                )

    if source_hash != _sha256_path(source) or target_hash != _sha256_path(target):
        raise AuditError("an input PPTX changed while the read-only audit was running")
    ok = not violations
    return {
        "schema_version": 1,
        "kind": "pptx-hidden-backup-audit",
        "source": {"path": str(source), "sha256": source_hash},
        "target": {"path": str(target), "sha256": target_hash},
        "pairs": pairs,
        "violations": violations,
        "summary": {
            "mapping_count": len(mappings),
            "identical_hidden_backup_count": sum(bool(item["identical"]) for item in pairs),
            "violation_count": len(violations),
        },
        "inputs_unchanged": True,
        "ok": ok,
        "exit_code": 0 if ok else 1,
    }


def report_to_text(report: dict[str, object]) -> str:
    lines = [
        "PPTX HIDDEN BACKUP AUDIT",
        f"Source: {report['source']['path']}",
        f"Target: {report['target']['path']}",
        "",
    ]
    for item in report["pairs"]:
        marker = "PASS" if item["identical"] else "FAIL"
        lines.append(
            f"  [{marker}] source {item['source_page']} -> backup {item['backup_page']} "
            f"(hidden={item.get('hidden')})"
        )
        for code in item.get("violations", []):
            lines.append(f"    - {code}")
    lines.append(f"Result: {'PASS' if report['ok'] else 'FAIL'}")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument(
        "--map",
        action="append",
        default=[],
        metavar="SOURCE:BACKUP",
        help="physical true-order source/hidden-backup page pair; repeatable",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    try:
        report = audit_backups(args.source, args.target, parse_maps(args.map))
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            sys.stdout.write(report_to_text(report))
        return int(report["exit_code"])
    except (AuditError, OSError, zipfile.BadZipFile) as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "pptx-hidden-backup-audit",
                        "ok": False,
                        "exit_code": 2,
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(f"audit_pptx_backups: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
