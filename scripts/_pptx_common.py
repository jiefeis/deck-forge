#!/usr/bin/env python3
"""Shared OOXML package helpers for the PPTX audit scripts.

Only helpers that were byte-identical across scripts live here. Same-named
helpers that differ in semantics deliberately stay where they are:

* ``transplant_pptx_slides._parse_xml`` is an lxml parser with DOCTYPE and
  expected-root gates that raises ``TransplantError``.
* ``transplant_pptx_slides._resolve_target`` rejects targets that escape the
  package; that is a safety gate, not a path helper.
* ``audit_pptx_page_numbers.parse_xml`` deliberately does not wrap
  ``ET.ParseError``; its CLI reports parse failures through the
  ``cannot audit PPTX`` path instead of ``AuditError``.
* Each script's canonical-tree normalizer answers a different question
  (fingerprint / backup signature / property diff) and must not converge.

This module is imported via the ``sys.path.insert(0, SCRIPT_DIR)`` pattern the
scripts already use, so they stay standalone and cwd-independent.
"""

from __future__ import annotations

import posixpath
import zipfile
import xml.etree.ElementTree as ET


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "cx": "http://schemas.microsoft.com/office/drawing/2014/chartex",
    "x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}

FALSE_VALUES = {"0", "false", "off", "no"}


class AuditError(RuntimeError):
    """Raised for malformed or unsupported PPTX package input."""


def q(prefix: str, tag: str) -> str:
    return f"{{{NS[prefix]}}}{tag}"


def _shown(value: str | None) -> bool:
    return value is None or value.strip().lower() not in FALSE_VALUES


def _parse_xml(data: bytes, part: str) -> ET.Element:
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise AuditError(f"invalid XML in {part}: {exc}") from exc


def _rels_part(part: str) -> str:
    folder = posixpath.dirname(part)
    base = posixpath.basename(part)
    return posixpath.join(folder, "_rels", base + ".rels")


def _resolve_target(source_part: str, target: str) -> str:
    target = target.split("#", 1)[0]
    if target.startswith("/"):
        return posixpath.normpath(target.lstrip("/"))
    return posixpath.normpath(posixpath.join(posixpath.dirname(source_part), target))


def _root_for(
    zf: zipfile.ZipFile, part: str, roots: dict[str, ET.Element] | None,
) -> ET.Element:
    """Read an XML part, reusing an optional per-package cache."""
    if roots is None:
        return _parse_xml(zf.read(part), part)
    if part not in roots:
        roots[part] = _parse_xml(zf.read(part), part)
    return roots[part]


def _relationships(
    zf: zipfile.ZipFile, source_part: str, names: set[str],
    roots: dict[str, ET.Element] | None = None,
) -> list[dict[str, str]]:
    rels_part = _rels_part(source_part)
    if rels_part not in names:
        return []
    result = []
    for rel in _root_for(zf, rels_part, roots).findall("rel:Relationship", NS):
        target = rel.get("Target", "")
        mode = rel.get("TargetMode", "")
        result.append({
            "id": rel.get("Id", ""), "type": rel.get("Type", ""),
            "target": target, "target_mode": mode,
            "resolved": "" if mode.lower() == "external" or not target
            else _resolve_target(source_part, target),
        })
    return result
