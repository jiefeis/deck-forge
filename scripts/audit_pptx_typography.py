#!/usr/bin/env python3
"""Read-only, inheritance-aware typography inventory for native PPTX files.

The audit reports OOXML text properties. It deliberately does not claim to
detect application font substitution, glyph fallback, clipping, or overflow;
those require rendering in the target presentation application.
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Sequence


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}

FALSE_VALUES = {"0", "false", "off", "no"}
TRUE_VALUES = {"1", "true", "on", "yes"}
ROLE_ORDER = (
    "title",
    "subtitle",
    "body",
    "caption",
    "footer",
    "page-number",
    "other",
)
ROLE_ALIASES = {
    "page_number": "page-number",
    "pagenumber": "page-number",
    "slide-number": "page-number",
    "slide_number": "page-number",
    "slidenumber": "page-number",
    "sub-title": "subtitle",
}
TEXT_BODY_TAGS: set[str] = set()
SHAPE_TAGS: set[str] = set()
THEME_TOKEN_RE = re.compile(r"^\+(mj|mn)-(lt|ea|cs)$", re.IGNORECASE)
CJK_RE = re.compile(
    r"[\u2e80-\u2fff\u3040-\u30ff\u31f0-\u31ff\u3400-\u4dbf"
    r"\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]"
)
JAPANESE_RE = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff]")
KOREAN_RE = re.compile(r"[\uac00-\ud7af]")
MOJIBAKE_TYPEFACE_RE = re.compile(r"^[\s?？\ufffd]+$")

LIMITATIONS = (
    "This is an OOXML source audit; it cannot determine rendered font "
    "substitution or glyph fallback in PowerPoint, WPS, or LibreOffice.",
    "OOXML text properties do not prove visual overflow, clipping, wrapping, "
    "or copy fit; render every relevant slide in the target application.",
)


class AuditError(RuntimeError):
    """Raised when a PPTX package cannot be audited reliably."""


def q(prefix: str, tag: str) -> str:
    return f"{{{NS[prefix]}}}{tag}"


TEXT_BODY_TAGS.update({q("p", "txBody"), q("a", "txBody")})
SHAPE_TAGS.update(
    {
        q("p", "sp"),
        q("p", "graphicFrame"),
        q("p", "cxnSp"),
        q("p", "contentPart"),
    }
)


@dataclass(frozen=True)
class Candidate:
    props: ET.Element | None
    font_ref: str | None
    level: str
    part: str
    path: str
    explicit: bool
    inherited: bool


@dataclass(frozen=True)
class ThemeCollection:
    latin: str
    east_asia: str
    complex_script: str
    supplemental: tuple[tuple[str, str], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "latin": self.latin or None,
            "eastAsia": self.east_asia or None,
            "complexScript": self.complex_script or None,
            "supplemental": [
                {"script": script, "typeface": typeface}
                for script, typeface in self.supplemental
            ],
        }


@dataclass(frozen=True)
class ThemeInfo:
    part: str
    name: str
    scheme_name: str
    major: ThemeCollection
    minor: ThemeCollection

    def as_dict(self) -> dict[str, object]:
        return {
            "part": self.part,
            "name": self.name,
            "font_scheme": self.scheme_name,
            "major": self.major.as_dict(),
            "minor": self.minor.as_dict(),
        }

    def resolve(
        self,
        reference: str,
        *,
        language: str,
        text: str,
    ) -> tuple[str | None, str | None, str | None]:
        match = THEME_TOKEN_RE.match(reference)
        if not match:
            return None, f"unsupported theme reference {reference!r}", None

        collection = self.major if match.group(1).lower() == "mj" else self.minor
        channel = match.group(2).lower()
        if channel == "lt":
            if collection.latin:
                return collection.latin, None, None
            return None, f"{reference} points to an empty theme Latin typeface", None
        if channel == "cs":
            if collection.complex_script:
                return collection.complex_script, None, None
            return None, f"{reference} points to an empty complex-script typeface", None

        if collection.east_asia:
            return collection.east_asia, None, None
        script = _east_asia_script(language, text)
        supplemental = dict(collection.supplemental)
        if script and supplemental.get(script):
            return supplemental[script], None, script
        if script:
            return (
                None,
                f"{reference} has no eastAsia typeface or {script} supplemental font",
                script,
            )
        return (
            None,
            f"{reference} has an empty eastAsia typeface and the script is ambiguous",
            None,
        )


def _parse_xml(data: bytes, part: str) -> ET.Element:
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise AuditError(f"invalid XML in {part}: {exc}") from exc


def _shown(value: str | None) -> bool:
    return value is None or value.strip().lower() not in FALSE_VALUES


def _rels_part(part: str) -> str:
    folder = posixpath.dirname(part)
    return posixpath.join(folder, "_rels", posixpath.basename(part) + ".rels")


def _resolve_target(source_part: str, target: str) -> str:
    target = target.split("#", 1)[0]
    if target.startswith("/"):
        return posixpath.normpath(target.lstrip("/"))
    return posixpath.normpath(posixpath.join(posixpath.dirname(source_part), target))


def _relationships(
    zf: zipfile.ZipFile,
    source_part: str,
    names: set[str],
) -> list[dict[str, str]]:
    rels_part = _rels_part(source_part)
    if rels_part not in names:
        return []
    root = _parse_xml(zf.read(rels_part), rels_part)
    result: list[dict[str, str]] = []
    for rel in root.findall("rel:Relationship", NS):
        mode = rel.get("TargetMode", "")
        target = rel.get("Target", "")
        result.append(
            {
                "id": rel.get("Id", ""),
                "type": rel.get("Type", ""),
                "target": ""
                if mode.lower() == "external" or not target
                else _resolve_target(source_part, target),
            }
        )
    return result


def _related_part(
    zf: zipfile.ZipFile,
    names: set[str],
    source_part: str,
    relationship_suffix: str,
) -> str:
    for rel in _relationships(zf, source_part, names):
        if rel["type"].endswith(relationship_suffix):
            return rel["target"]
    return ""


def _ordered_slides(
    zf: zipfile.ZipFile,
    names: set[str],
    presentation: ET.Element,
) -> list[dict[str, object]]:
    rel_map = {
        rel["id"]: rel["target"]
        for rel in _relationships(zf, "ppt/presentation.xml", names)
        if rel["type"].endswith("/slide") and rel["id"] and rel["target"]
    }
    slides: list[dict[str, object]] = []
    for page, node in enumerate(
        presentation.findall("./p:sldIdLst/p:sldId", NS), 1
    ):
        rel_id = node.get(q("r", "id"), "")
        part = rel_map.get(rel_id, "")
        if not part:
            raise AuditError(f"slide relationship {rel_id!r} is missing")
        if part not in names:
            raise AuditError(f"slide part is missing: {part}")
        raw_id = node.get("id", "")
        try:
            slide_id: int | str = int(raw_id)
        except ValueError:
            slide_id = raw_id
        slides.append(
            {
                "page": page,
                "slide_id": slide_id,
                "part": part,
                "shown_in_presentation": _shown(node.get("show")),
            }
        )
    return slides


def _theme_collection(font_scheme: ET.Element, tag: str) -> ThemeCollection:
    collection = font_scheme.find(f"a:{tag}", NS)
    if collection is None:
        return ThemeCollection("", "", "", ())

    def typeface(child_tag: str) -> str:
        child = collection.find(f"a:{child_tag}", NS)
        return child.get("typeface", "") if child is not None else ""

    supplemental = tuple(
        (font.get("script", ""), font.get("typeface", ""))
        for font in collection.findall("a:font", NS)
        if font.get("script")
    )
    return ThemeCollection(
        latin=typeface("latin"),
        east_asia=typeface("ea"),
        complex_script=typeface("cs"),
        supplemental=supplemental,
    )


def _read_theme(root: ET.Element, part: str) -> ThemeInfo:
    font_scheme = root.find(".//a:fontScheme", NS)
    if font_scheme is None:
        empty = ThemeCollection("", "", "", ())
        return ThemeInfo(part, root.get("name", ""), "", empty, empty)
    return ThemeInfo(
        part=part,
        name=root.get("name", ""),
        scheme_name=font_scheme.get("name", ""),
        major=_theme_collection(font_scheme, "majorFont"),
        minor=_theme_collection(font_scheme, "minorFont"),
    )


def _east_asia_script(language: str, text: str) -> str | None:
    language = language.replace("_", "-").lower()
    if language.startswith("ja") or JAPANESE_RE.search(text):
        return "Jpan"
    if language.startswith("ko") or KOREAN_RE.search(text):
        return "Hang"
    if language.startswith("zh"):
        region = language.split("-", 1)[1] if "-" in language else ""
        return "Hant" if region in {"tw", "hk", "mo", "hant"} else "Hans"
    return None


def _shape_parts(shape: ET.Element) -> tuple[ET.Element | None, ET.Element | None]:
    paths = {
        q("p", "sp"): ("./p:nvSpPr/p:cNvPr", "./p:nvSpPr/p:nvPr/p:ph"),
        q("p", "graphicFrame"): (
            "./p:nvGraphicFramePr/p:cNvPr",
            "./p:nvGraphicFramePr/p:nvPr/p:ph",
        ),
        q("p", "cxnSp"): (
            "./p:nvCxnSpPr/p:cNvPr",
            "./p:nvCxnSpPr/p:nvPr/p:ph",
        ),
        q("p", "contentPart"): (
            "./p:nvContentPartPr/p:cNvPr",
            "./p:nvContentPartPr/p:nvPr/p:ph",
        ),
    }
    nv_path, ph_path = paths.get(shape.tag, ("", ""))
    return (
        shape.find(nv_path, NS) if nv_path else None,
        shape.find(ph_path, NS) if ph_path else None,
    )


def _shape_metadata(shape: ET.Element | None) -> dict[str, str]:
    if shape is None:
        return {"id": "", "name": "", "placeholder_type": "", "placeholder_index": ""}
    non_visual, placeholder = _shape_parts(shape)
    return {
        "id": non_visual.get("id", "") if non_visual is not None else "",
        "name": non_visual.get("name", "") if non_visual is not None else "",
        "placeholder_type": placeholder.get("type", "") if placeholder is not None else "",
        "placeholder_index": placeholder.get("idx", "") if placeholder is not None else "",
    }


def _shape_font_ref(shape: ET.Element | None) -> str | None:
    if shape is None:
        return None
    font_ref = shape.find("./p:style/a:fontRef", NS)
    if font_ref is None:
        return None
    value = font_ref.get("idx", "")
    return value if value in {"major", "minor"} else None


def _iter_shapes(root: ET.Element) -> Iterable[ET.Element]:
    for element in root.iter():
        if element.tag in SHAPE_TAGS:
            yield element


def _iter_text_bodies(root: ET.Element) -> Iterable[tuple[ET.Element | None, ET.Element]]:
    parents = {child: parent for parent in root.iter() for child in parent}
    for text_body in root.iter():
        if text_body.tag not in TEXT_BODY_TAGS:
            continue
        parent = parents.get(text_body)
        while parent is not None and parent.tag not in SHAPE_TAGS:
            parent = parents.get(parent)
        yield parent, text_body


def _placeholder_key(shape: ET.Element | None) -> tuple[str, str] | None:
    if shape is None:
        return None
    _, placeholder = _shape_parts(shape)
    if placeholder is None:
        return None
    return placeholder.get("type", ""), placeholder.get("idx", "")


def _placeholder_family(value: str) -> str:
    if value in {"title", "ctrTitle"}:
        return "title"
    if value in {"body", "obj"}:
        return "body"
    return value


def _find_placeholder(root: ET.Element | None, source: ET.Element | None) -> ET.Element | None:
    if root is None:
        return None
    key = _placeholder_key(source)
    if key is None:
        return None
    source_type, source_index = key
    candidates = [shape for shape in _iter_shapes(root) if _placeholder_key(shape)]
    if source_index:
        for shape in candidates:
            if _placeholder_key(shape)[1] == source_index:
                return shape
    if source_type:
        for shape in candidates:
            if _placeholder_key(shape)[0] == source_type:
                return shape
        family = _placeholder_family(source_type)
        for shape in candidates:
            if _placeholder_family(_placeholder_key(shape)[0]) == family:
                return shape
    if not source_type and source_index == "":
        for shape in candidates:
            if _placeholder_key(shape)[0] in {"body", "obj", ""}:
                return shape
    return None


def _direct_text_body(shape: ET.Element | None) -> ET.Element | None:
    if shape is None:
        return None
    for child in shape:
        if child.tag in TEXT_BODY_TAGS:
            return child
    return None


def _effective_placeholder_type(
    shape: ET.Element | None,
    layout_shape: ET.Element | None,
    master_shape: ET.Element | None,
) -> str:
    for candidate in (shape, layout_shape, master_shape):
        key = _placeholder_key(candidate)
        if key and key[0]:
            return key[0]
    return "obj" if _placeholder_key(shape) is not None else ""


def _role_for(
    placeholder_type: str,
    field_type: str,
    shape_name: str,
) -> tuple[str, str]:
    field_key = re.sub(r"[^a-z0-9]", "", field_type.casefold())
    if "slidenum" in field_key or "pagenum" in field_key:
        return "page-number", "field"
    if any(token in field_key for token in ("datetime", "footer", "header")):
        return "footer", "field"

    role_map = {
        "title": "title",
        "ctrTitle": "title",
        "subTitle": "subtitle",
        "body": "body",
        "obj": "body",
        "caption": "caption",
        "ftr": "footer",
        "dt": "footer",
        "hdr": "footer",
        "sldNum": "page-number",
    }
    if placeholder_type in role_map:
        return role_map[placeholder_type], "placeholder"

    name = shape_name.casefold().replace("_", " ").replace("-", " ")
    if ("page" in name or "slide" in name) and "number" in name:
        return "page-number", "shape-name"
    if name.startswith("subtitle") or name.startswith("sub title"):
        return "subtitle", "shape-name"
    if name.startswith("title"):
        return "title", "shape-name"
    if "caption" in name:
        return "caption", "shape-name"
    if "footer" in name:
        return "footer", "shape-name"
    if name.startswith("body") or name.startswith("content"):
        return "body", "shape-name"
    return "other", "unclassified"


def _candidate(
    props: ET.Element | None,
    font_ref: str | None,
    *,
    level: str,
    part: str,
    path: str,
    explicit: bool,
) -> Candidate | None:
    if props is None and font_ref is None:
        return None
    return Candidate(
        props=props,
        font_ref=font_ref,
        level=level,
        part=part,
        path=path,
        explicit=explicit,
        inherited=level != "slide" or not explicit,
    )


def _append_candidate(target: list[Candidate], item: Candidate | None) -> None:
    if item is not None:
        target.append(item)


def _paragraph_default(paragraph: ET.Element | None) -> ET.Element | None:
    if paragraph is None:
        return None
    return paragraph.find("./a:pPr/a:defRPr", NS)


def _paragraph_for(text_body: ET.Element | None, index: int) -> ET.Element | None:
    if text_body is None:
        return None
    paragraphs = text_body.findall("./a:p", NS)
    if not paragraphs:
        return None
    return paragraphs[index] if index < len(paragraphs) else paragraphs[0]


def _append_body_defaults(
    target: list[Candidate],
    *,
    text_body: ET.Element | None,
    paragraph_index: int,
    paragraph_level: int,
    level: str,
    part: str,
    path_prefix: str,
) -> None:
    paragraph = _paragraph_for(text_body, paragraph_index)
    _append_candidate(
        target,
        _candidate(
            _paragraph_default(paragraph),
            None,
            level=level,
            part=part,
            path=f"{path_prefix}/paragraph[{paragraph_index + 1}]/defRPr",
            explicit=False,
        ),
    )
    if text_body is None:
        return
    list_style = text_body.find("./a:lstStyle", NS)
    if list_style is None:
        return
    for tag, label in (
        (f"lvl{paragraph_level + 1}pPr", f"level-{paragraph_level + 1}"),
        ("defPPr", "default-level"),
    ):
        props = list_style.find(f"./a:{tag}/a:defRPr", NS)
        _append_candidate(
            target,
            _candidate(
                props,
                None,
                level=level,
                part=part,
                path=f"{path_prefix}/lstStyle/{label}/defRPr",
                explicit=False,
            ),
        )


def _append_text_style(
    target: list[Candidate],
    *,
    style: ET.Element | None,
    paragraph_level: int,
    level: str,
    part: str,
    path_prefix: str,
) -> None:
    if style is None:
        return
    for tag, label in (
        (f"lvl{paragraph_level + 1}pPr", f"level-{paragraph_level + 1}"),
        ("defPPr", "default-level"),
    ):
        props = style.find(f"./a:{tag}/a:defRPr", NS)
        _append_candidate(
            target,
            _candidate(
                props,
                None,
                level=level,
                part=part,
                path=f"{path_prefix}/{label}/defRPr",
                explicit=False,
            ),
        )


def _master_style(master: ET.Element | None, role: str) -> ET.Element | None:
    if master is None:
        return None
    tag = "titleStyle" if role == "title" else "bodyStyle" if role == "body" else "otherStyle"
    return master.find(f"./p:txStyles/p:{tag}", NS)


def _build_candidates(
    *,
    run_props: ET.Element | None,
    paragraph: ET.Element,
    text_body: ET.Element,
    paragraph_index: int,
    paragraph_level: int,
    origin_level: str,
    origin_part: str,
    shape: ET.Element | None,
    layout_shape: ET.Element | None,
    layout_part: str,
    master_shape: ET.Element | None,
    master_root: ET.Element | None,
    master_part: str,
    role: str,
    presentation: ET.Element,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    _append_candidate(
        candidates,
        _candidate(
            run_props,
            None,
            level=origin_level,
            part=origin_part,
            path="run",
            explicit=True,
        ),
    )
    _append_body_defaults(
        candidates,
        text_body=text_body,
        paragraph_index=paragraph_index,
        paragraph_level=paragraph_level,
        level=origin_level,
        part=origin_part,
        path_prefix="text-body",
    )
    _append_candidate(
        candidates,
        _candidate(
            None,
            _shape_font_ref(shape),
            level=origin_level,
            part=origin_part,
            path="shape-style/fontRef",
            explicit=False,
        ),
    )

    if origin_level == "slide" and layout_shape is not None:
        _append_body_defaults(
            candidates,
            text_body=_direct_text_body(layout_shape),
            paragraph_index=paragraph_index,
            paragraph_level=paragraph_level,
            level="layout",
            part=layout_part,
            path_prefix="placeholder/text-body",
        )
        _append_candidate(
            candidates,
            _candidate(
                None,
                _shape_font_ref(layout_shape),
                level="layout",
                part=layout_part,
                path="placeholder/shape-style/fontRef",
                explicit=False,
            ),
        )

    if origin_level in {"slide", "layout"} and master_shape is not None:
        _append_body_defaults(
            candidates,
            text_body=_direct_text_body(master_shape),
            paragraph_index=paragraph_index,
            paragraph_level=paragraph_level,
            level="master",
            part=master_part,
            path_prefix="placeholder/text-body",
        )
        _append_candidate(
            candidates,
            _candidate(
                None,
                _shape_font_ref(master_shape),
                level="master",
                part=master_part,
                path="placeholder/shape-style/fontRef",
                explicit=False,
            ),
        )

    if master_root is not None:
        _append_text_style(
            candidates,
            style=_master_style(master_root, role),
            paragraph_level=paragraph_level,
            level="master",
            part=master_part,
            path_prefix=f"txStyles/{'titleStyle' if role == 'title' else 'bodyStyle' if role == 'body' else 'otherStyle'}",
        )
    _append_text_style(
        candidates,
        style=presentation.find("./p:defaultTextStyle", NS),
        paragraph_level=paragraph_level,
        level="presentation",
        part="ppt/presentation.xml",
        path_prefix="defaultTextStyle",
    )
    return candidates


def _source_fields(candidate: Candidate) -> dict[str, object]:
    return {
        "source_level": candidate.level,
        "source_part": candidate.part,
        "source_path": candidate.path,
        "explicit": candidate.explicit,
        "inherited": candidate.inherited,
    }


def _language(candidates: Sequence[Candidate]) -> str:
    for candidate in candidates:
        if candidate.props is not None and candidate.props.get("lang"):
            return candidate.props.get("lang", "")
    return ""


def _font_value(
    raw: str,
    candidate: Candidate,
    theme: ThemeInfo | None,
    *,
    language: str,
    text: str,
) -> dict[str, object]:
    theme_reference = raw if raw.startswith("+") else None
    value: str | None = raw or None
    reason: str | None = None
    theme_script: str | None = None
    if not raw:
        reason = "empty typeface value"
    elif theme_reference:
        if theme is None:
            value = None
            reason = f"theme reference {raw} has no related theme part"
        else:
            value, reason, theme_script = theme.resolve(
                raw, language=language, text=text
            )
    if value is not None and (
        "\ufffd" in value or MOJIBAKE_TYPEFACE_RE.fullmatch(value)
    ):
        reason = f"suspect mojibake typeface {value!r}"
        value = None
    return {
        "value": value,
        "raw": raw or None,
        "theme_reference": theme_reference,
        "theme_part": theme.part if theme_reference and theme is not None else None,
        "theme_script": theme_script,
        "resolved": value is not None,
        "unresolved_reason": reason,
        **_source_fields(candidate),
    }


def _resolve_font(
    channel: str,
    candidates: Sequence[Candidate],
    theme: ThemeInfo | None,
    *,
    language: str,
    text: str,
) -> dict[str, object]:
    child_tag = "latin" if channel == "latin" else "ea"
    entries: list[dict[str, object]] = []
    for candidate in candidates:
        raw: str | None = None
        if candidate.props is not None:
            font = candidate.props.find(f"./a:{child_tag}", NS)
            if font is not None and "typeface" in font.attrib:
                raw = font.get("typeface", "")
        if raw is None and candidate.font_ref:
            prefix = "mj" if candidate.font_ref == "major" else "mn"
            suffix = "lt" if channel == "latin" else "ea"
            raw = f"+{prefix}-{suffix}"
        if raw is not None:
            entries.append(
                _font_value(
                    raw,
                    candidate,
                    theme,
                    language=language,
                    text=text,
                )
            )

    if entries:
        selected = dict(entries[0])
        selected["chain"] = [
            {**entry, "selected": index == 0}
            for index, entry in enumerate(entries)
        ]
        return selected
    return {
        "value": None,
        "raw": None,
        "theme_reference": None,
        "theme_part": None,
        "theme_script": None,
        "resolved": False,
        "unresolved_reason": "not specified in the slide/layout/master/default chain",
        "source_level": None,
        "source_part": None,
        "source_path": None,
        "explicit": False,
        "inherited": True,
        "chain": [],
    }


def _resolve_size(candidates: Sequence[Candidate]) -> dict[str, object]:
    entries: list[dict[str, object]] = []
    for candidate in candidates:
        if candidate.props is None or "sz" not in candidate.props.attrib:
            continue
        raw = candidate.props.get("sz", "")
        try:
            value = int(raw)
            if value <= 0:
                raise ValueError
            reason = None
        except ValueError:
            value = None
            reason = f"invalid OOXML size {raw!r}"
        entries.append(
            {
                "value": value,
                "points": value / 100 if value is not None else None,
                "raw": raw,
                "resolved": value is not None,
                "unresolved_reason": reason,
                **_source_fields(candidate),
            }
        )
    if entries:
        selected = dict(entries[0])
        selected["chain"] = [
            {**entry, "selected": index == 0}
            for index, entry in enumerate(entries)
        ]
        return selected
    return {
        "value": None,
        "points": None,
        "raw": None,
        "resolved": False,
        "unresolved_reason": "not specified in the slide/layout/master/default chain",
        "source_level": None,
        "source_part": None,
        "source_path": None,
        "explicit": False,
        "inherited": True,
        "chain": [],
    }


def _parse_on_off(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    return None


def _resolve_bold(candidates: Sequence[Candidate]) -> dict[str, object]:
    entries: list[dict[str, object]] = []
    for candidate in candidates:
        if candidate.props is None or "b" not in candidate.props.attrib:
            continue
        raw = candidate.props.get("b", "")
        value = _parse_on_off(raw)
        entries.append(
            {
                "value": value,
                "raw": raw,
                "resolved": value is not None,
                "unresolved_reason": None if value is not None else f"invalid bold value {raw!r}",
                **_source_fields(candidate),
            }
        )
    if entries:
        selected = dict(entries[0])
        selected["chain"] = [
            {**entry, "selected": index == 0}
            for index, entry in enumerate(entries)
        ]
        return selected
    default = {
        "value": False,
        "raw": None,
        "resolved": True,
        "unresolved_reason": None,
        "source_level": "default",
        "source_part": None,
        "source_path": "OOXML default",
        "explicit": False,
        "inherited": True,
    }
    default["chain"] = [{**default, "selected": True}]
    return default


def _paragraph_level(paragraph: ET.Element) -> int:
    ppr = paragraph.find("./a:pPr", NS)
    raw = ppr.get("lvl", "0") if ppr is not None else "0"
    try:
        return min(8, max(0, int(raw)))
    except ValueError:
        return 0


def _placeholder_enabled(root: ET.Element | None, placeholder_type: str) -> bool:
    if root is None or placeholder_type not in {"sldNum", "ftr", "hdr", "dt"}:
        return True
    header_footer = root.find("./p:hf", NS)
    if header_footer is None:
        return True
    return _shown(header_footer.get(placeholder_type))


def _include_inherited_node(
    placeholder_type: str,
    field_type: str,
) -> bool:
    if not placeholder_type:
        return True
    if field_type:
        return True
    return placeholder_type in {"sldNum", "ftr", "hdr", "dt"}


def _collect_origin_runs(
    *,
    page: int,
    hidden: bool,
    origin_level: str,
    origin_part: str,
    origin_root: ET.Element,
    layout_root: ET.Element | None,
    layout_part: str,
    master_root: ET.Element | None,
    master_part: str,
    theme: ThemeInfo | None,
    presentation: ET.Element,
) -> list[dict[str, object]]:
    runs: list[dict[str, object]] = []
    for text_body_index, (shape, text_body) in enumerate(_iter_text_bodies(origin_root), 1):
        if origin_level == "slide":
            layout_shape = _find_placeholder(layout_root, shape)
            master_source = layout_shape if layout_shape is not None else shape
            master_shape = _find_placeholder(master_root, master_source)
        elif origin_level == "layout":
            layout_shape = None
            master_shape = _find_placeholder(master_root, shape)
        else:
            layout_shape = None
            master_shape = None

        placeholder_type = _effective_placeholder_type(
            shape, layout_shape, master_shape
        )
        shape_meta = _shape_metadata(shape)
        shape_meta["placeholder_type"] = placeholder_type
        paragraphs = text_body.findall("./a:p", NS)
        for paragraph_index, paragraph in enumerate(paragraphs):
            level = _paragraph_level(paragraph)
            run_index = 0
            for node in paragraph:
                if node.tag not in {q("a", "r"), q("a", "fld")}:
                    continue
                run_index += 1
                field_type = node.get("type", "") if node.tag == q("a", "fld") else ""
                text = "".join(child.text or "" for child in node.findall(".//a:t", NS))
                if not text and not field_type:
                    continue
                if origin_level != "slide" and not _include_inherited_node(
                    placeholder_type, field_type
                ):
                    continue
                if origin_level != "slide" and not _placeholder_enabled(
                    origin_root, placeholder_type
                ):
                    continue
                role, role_basis = _role_for(
                    placeholder_type, field_type, shape_meta["name"]
                )
                run_props = node.find("./a:rPr", NS)
                candidates = _build_candidates(
                    run_props=run_props,
                    paragraph=paragraph,
                    text_body=text_body,
                    paragraph_index=paragraph_index,
                    paragraph_level=level,
                    origin_level=origin_level,
                    origin_part=origin_part,
                    shape=shape,
                    layout_shape=layout_shape,
                    layout_part=layout_part,
                    master_shape=master_shape,
                    master_root=master_root,
                    master_part=master_part,
                    role=role,
                    presentation=presentation,
                )
                language = _language(candidates)
                runs.append(
                    {
                        "page": page,
                        "hidden": hidden,
                        "role": role,
                        "role_basis": role_basis,
                        "text": text,
                        "field_type": field_type or None,
                        "language": language or None,
                        "contains_cjk": bool(CJK_RE.search(text)),
                        "origin_level": origin_level,
                        "origin_part": origin_part,
                        "inherited_content": origin_level != "slide",
                        "shape": dict(shape_meta),
                        "text_body": text_body_index,
                        "paragraph": paragraph_index + 1,
                        "run": run_index,
                        "font": {
                            "latin": _resolve_font(
                                "latin",
                                candidates,
                                theme,
                                language=language,
                                text=text,
                            ),
                            "eastAsia": _resolve_font(
                                "eastAsia",
                                candidates,
                                theme,
                                language=language,
                                text=text,
                            ),
                        },
                        "size": _resolve_size(candidates),
                        "bold": _resolve_bold(candidates),
                    }
                )
    return runs


def _font_signature(font: dict[str, object]) -> tuple[str, str]:
    if font["resolved"]:
        return "resolved", str(font["value"]).casefold()
    raw = font.get("raw")
    return "unresolved", str(raw).casefold() if raw is not None else "<absent>"


def _property_source(prop: dict[str, object]) -> str:
    level = prop.get("source_level") or "unresolved"
    part = prop.get("source_part") or ""
    path = prop.get("source_path") or ""
    return ":".join(value for value in (str(level), str(part), str(path)) if value)


def _group_fonts(runs: Sequence[dict[str, object]], channel: str) -> list[dict[str, object]]:
    groups: dict[tuple[str, str], dict[str, object]] = {}
    for run in runs:
        font = run["font"][channel]
        key = _font_signature(font)
        group = groups.setdefault(
            key,
            {
                "value": font.get("value"),
                "resolved": font["resolved"],
                "count": 0,
                "slides": set(),
                "raw_values": set(),
                "theme_references": set(),
                "sources": set(),
                "unresolved_reasons": set(),
            },
        )
        group["count"] += 1
        group["slides"].add(run["page"])
        if font.get("raw") is not None:
            group["raw_values"].add(font["raw"])
        if font.get("theme_reference"):
            group["theme_references"].add(font["theme_reference"])
        group["sources"].add(_property_source(font))
        if font.get("unresolved_reason"):
            group["unresolved_reasons"].add(font["unresolved_reason"])

    result: list[dict[str, object]] = []
    for group in groups.values():
        result.append(
            {
                **{key: value for key, value in group.items() if not isinstance(value, set)},
                "slides": sorted(group["slides"]),
                "raw_values": sorted(group["raw_values"]),
                "theme_references": sorted(group["theme_references"]),
                "sources": sorted(group["sources"]),
                "unresolved_reasons": sorted(group["unresolved_reasons"]),
            }
        )
    return sorted(result, key=lambda item: (not item["resolved"], str(item["value"] or "")))


def _group_scalar(
    runs: Sequence[dict[str, object]],
    property_name: str,
) -> list[dict[str, object]]:
    groups: dict[tuple[bool, object], dict[str, object]] = {}
    for run in runs:
        prop = run[property_name]
        key = (bool(prop["resolved"]), prop.get("value") if prop["resolved"] else prop.get("raw"))
        group = groups.setdefault(
            key,
            {
                "value": prop.get("value"),
                "resolved": prop["resolved"],
                "count": 0,
                "slides": set(),
                "raw_values": set(),
                "sources": set(),
                "unresolved_reasons": set(),
            },
        )
        group["count"] += 1
        group["slides"].add(run["page"])
        if prop.get("raw") is not None:
            group["raw_values"].add(prop["raw"])
        group["sources"].add(_property_source(prop))
        if prop.get("unresolved_reason"):
            group["unresolved_reasons"].add(prop["unresolved_reason"])
    result: list[dict[str, object]] = []
    for group in groups.values():
        item = {
            **{key: value for key, value in group.items() if not isinstance(value, set)},
            "slides": sorted(group["slides"]),
            "raw_values": sorted(str(value) for value in group["raw_values"]),
            "sources": sorted(group["sources"]),
            "unresolved_reasons": sorted(group["unresolved_reasons"]),
        }
        if property_name == "size":
            item["points"] = item["value"] / 100 if item["value"] is not None else None
        result.append(item)
    return sorted(result, key=lambda item: (not item["resolved"], str(item["value"])))


def _build_inventory(runs: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    role_runs: dict[str, list[dict[str, object]]] = defaultdict(list)
    for run in runs:
        role_runs[str(run["role"])].append(run)
    roles = [role for role in ROLE_ORDER if role in role_runs]
    roles.extend(sorted(set(role_runs) - set(roles)))
    inventory: list[dict[str, object]] = []
    for role in roles:
        selected = role_runs[role]
        inventory.append(
            {
                "role": role,
                "runs": len(selected),
                "slides": sorted({int(run["page"]) for run in selected}),
                "hidden_runs": sum(bool(run["hidden"]) for run in selected),
                "fonts": {
                    "latin": _group_fonts(selected, "latin"),
                    "eastAsia": _group_fonts(selected, "eastAsia"),
                },
                "sizes": _group_scalar(selected, "size"),
                "bold": _group_scalar(selected, "bold"),
            }
        )
    return inventory


def _unresolved(runs: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for run in runs:
        properties = {
            "font.latin": run["font"]["latin"],
            "font.eastAsia": run["font"]["eastAsia"],
            "size": run["size"],
            "bold": run["bold"],
        }
        for name, prop in properties.items():
            if prop["resolved"]:
                continue
            result.append(
                {
                    "page": run["page"],
                    "hidden": run["hidden"],
                    "role": run["role"],
                    "text": run["text"],
                    "property": name,
                    "raw": prop.get("raw"),
                    "reason": prop.get("unresolved_reason"),
                    "source_level": prop.get("source_level"),
                    "source_part": prop.get("source_part"),
                    "source_path": prop.get("source_path"),
                }
            )
    return result


def normalize_role(value: str) -> str:
    role = value.strip().casefold().replace(" ", "-")
    return ROLE_ALIASES.get(role, role)


def parse_slide_ranges(specs: Sequence[str] | str) -> set[int]:
    """Parse repeatable physical-page ranges such as ``1,3-5``."""

    values = (specs,) if isinstance(specs, str) else tuple(specs)
    pages: set[int] = set()
    for spec in values:
        if not spec.strip():
            raise ValueError("--slides range cannot be empty")
        for token in spec.split(","):
            token = token.strip()
            match = re.fullmatch(r"([0-9]+)(?:-([0-9]+))?", token)
            if not match:
                raise ValueError(
                    f"invalid --slides token {token!r}; use physical pages such as 1,3-5"
                )
            start = int(match.group(1))
            end = int(match.group(2) or start)
            if start < 1 or end < 1:
                raise ValueError("--slides page numbers must be greater than zero")
            if end < start:
                raise ValueError(f"invalid descending --slides range {token!r}")
            pages.update(range(start, end + 1))
    return pages


def _parse_size_expectation(value: str) -> tuple[int, ...] | None:
    token = value.strip().casefold()
    if token == "*":
        return None
    raw_units = False
    for suffix in ("ooxml", "hpt"):
        if token.endswith(suffix):
            token = token[: -len(suffix)].strip()
            raw_units = True
            break
    if token.endswith("pt"):
        token = token[:-2].strip()
    try:
        number = Decimal(token)
    except InvalidOperation as exc:
        raise ValueError(f"invalid expected size {value!r}") from exc
    if number <= 0:
        raise ValueError("expected size must be greater than zero")
    if raw_units:
        if number != number.to_integral_value():
            raise ValueError("OOXML hundredths size must be an integer")
        return (int(number),)
    points = number * 100
    if points != points.to_integral_value():
        raise ValueError("point size must resolve to OOXML hundredths")
    accepted = {int(points)}
    if number == number.to_integral_value() and number >= 500:
        accepted.add(int(number))
    return tuple(sorted(accepted))


def _parse_font_expectation(value: str) -> dict[str, str]:
    token = value.strip()
    if token == "*":
        return {}
    pieces = re.split(r"[|;]", token)
    if len(pieces) == 1 and ":" not in pieces[0]:
        if not pieces[0].strip():
            raise ValueError("expected font cannot be empty")
        return {"latin": pieces[0].strip()}
    aliases = {
        "latin": "latin",
        "lt": "latin",
        "eastasia": "eastAsia",
        "east-asia": "eastAsia",
        "ea": "eastAsia",
        "cjk": "eastAsia",
    }
    result: dict[str, str] = {}
    for piece in pieces:
        if ":" not in piece:
            raise ValueError(
                "channel-specific font must use latin:FONT or eastAsia:FONT"
            )
        channel, font = piece.split(":", 1)
        normalized = aliases.get(channel.strip().casefold())
        if normalized is None or not font.strip():
            raise ValueError(f"invalid expected font component {piece!r}")
        result[normalized] = font.strip()
    return result


def parse_expectation(spec: str) -> dict[str, object]:
    if "=" not in spec:
        raise ValueError("expectation must be role=font,size,bold")
    role, payload = spec.split("=", 1)
    fields = [field.strip() for field in payload.split(",")]
    if len(fields) != 3:
        raise ValueError("expectation must contain exactly font,size,bold")
    normalized_role = normalize_role(role)
    if not normalized_role:
        raise ValueError("expected role cannot be empty")
    bold_token = fields[2].casefold()
    if bold_token == "*":
        bold: bool | None = None
    else:
        bold = _parse_on_off(bold_token)
        if bold is None:
            raise ValueError(f"invalid expected bold value {fields[2]!r}")
    return {
        "spec": spec,
        "role": normalized_role,
        "fonts": _parse_font_expectation(fields[0]),
        "size_hundredths": _parse_size_expectation(fields[1]),
        "bold": bold,
    }


def _font_matches(actual: dict[str, object], expected: str) -> bool:
    target = expected.casefold()
    return any(
        str(value).casefold() == target
        for value in (
            actual.get("value"),
            actual.get("raw"),
            actual.get("theme_reference"),
        )
        if value is not None
    )


def _expectation_matches(run: dict[str, object], expectation: dict[str, object]) -> bool:
    for channel, font in expectation["fonts"].items():
        if not _font_matches(run["font"][channel], font):
            return False
    sizes = expectation["size_hundredths"]
    if sizes is not None and run["size"].get("value") not in sizes:
        return False
    expected_bold = expectation["bold"]
    if expected_bold is not None and run["bold"].get("value") is not expected_bold:
        return False
    return True


def _variant_text(run: dict[str, object]) -> str:
    latin = run["font"]["latin"].get("value") or run["font"]["latin"].get("raw") or "<unresolved>"
    east_asia = run["font"]["eastAsia"].get("value") or run["font"]["eastAsia"].get("raw") or "<unresolved>"
    size = run["size"].get("points")
    size_text = f"{size:g}pt" if size is not None else "<unresolved>"
    bold = run["bold"].get("value")
    return f"latin={latin}, eastAsia={east_asia}, size={size_text}, bold={bold}"


def _validate(
    runs: Sequence[dict[str, object]],
    expectations: Sequence[dict[str, object]],
    fail_inconsistent_role: bool,
) -> list[dict[str, object]]:
    failures: list[dict[str, object]] = []
    role_runs: dict[str, list[dict[str, object]]] = defaultdict(list)
    role_expectations: dict[str, list[dict[str, object]]] = defaultdict(list)
    for run in runs:
        role_runs[str(run["role"])].append(run)
    for expectation in expectations:
        role_expectations[str(expectation["role"])].append(expectation)

    for role, allowed in role_expectations.items():
        if not role_runs.get(role):
            failures.append(
                {
                    "code": "expected-role-missing",
                    "role": role,
                    "message": f"expected role {role!r} was not found",
                }
            )
            continue
        for run in role_runs[role]:
            if any(_expectation_matches(run, expectation) for expectation in allowed):
                continue
            failures.append(
                {
                    "code": "expectation-mismatch",
                    "role": role,
                    "page": run["page"],
                    "message": (
                        f"slide {run['page']} role {role}: unauthorized typography "
                        f"({_variant_text(run)})"
                    ),
                }
            )

    if not fail_inconsistent_role:
        return failures

    for role, selected in role_runs.items():
        allowed = role_expectations.get(role, [])
        constrained_fonts = {
            channel for item in allowed for channel in item["fonts"]
        }
        size_constrained = any(item["size_hundredths"] is not None for item in allowed)
        bold_constrained = any(item["bold"] is not None for item in allowed)

        for channel in ("latin", "eastAsia"):
            if channel in constrained_fonts:
                continue
            variants = {_font_signature(run["font"][channel]) for run in selected}
            if len(variants) > 1:
                failures.append(
                    {
                        "code": "inconsistent-role-font",
                        "role": role,
                        "channel": channel,
                        "message": (
                            f"role {role}: inconsistent {channel} fonts across "
                            f"{len(selected)} runs"
                        ),
                    }
                )

        if not size_constrained:
            sizes = {
                (run["size"]["resolved"], run["size"].get("value") if run["size"]["resolved"] else run["size"].get("raw"))
                for run in selected
            }
            if len(sizes) > 1:
                failures.append(
                    {
                        "code": "inconsistent-role-size",
                        "role": role,
                        "message": f"role {role}: inconsistent sizes across {len(selected)} runs",
                    }
                )
        if not bold_constrained:
            weights = {
                (run["bold"]["resolved"], run["bold"].get("value") if run["bold"]["resolved"] else run["bold"].get("raw"))
                for run in selected
            }
            if len(weights) > 1:
                failures.append(
                    {
                        "code": "inconsistent-role-bold",
                        "role": role,
                        "message": f"role {role}: inconsistent bold values across {len(selected)} runs",
                    }
                )
    return failures


def audit_pptx(
    path: str | Path,
    *,
    expectations: Sequence[dict[str, object]] = (),
    fail_inconsistent_role: bool = False,
    slide_ranges: Sequence[str] | str = (),
    include_hidden: bool = False,
) -> dict[str, object]:
    """Return a scoped, JSON-serializable typography audit for ``path``."""

    pptx = Path(path).expanduser().resolve()
    if not pptx.is_file():
        raise AuditError(f"PPTX not found: {pptx}")
    raw_slide_ranges = (
        (slide_ranges,) if isinstance(slide_ranges, str) else tuple(slide_ranges)
    )
    try:
        requested_pages = parse_slide_ranges(raw_slide_ranges)
    except ValueError as exc:
        raise AuditError(str(exc)) from exc
    slides_specified = bool(raw_slide_ranges)

    warnings: list[str] = []
    all_runs: list[dict[str, object]] = []
    slide_reports: list[dict[str, object]] = []
    themes: dict[str, ThemeInfo] = {}
    try:
        with zipfile.ZipFile(pptx, "r") as zf:
            names_list = zf.namelist()
            names = set(names_list)
            duplicates = sorted(
                name for name, count in Counter(names_list).items() if count > 1
            )
            if duplicates:
                warnings.append("duplicate ZIP parts: " + ", ".join(duplicates[:10]))
            bad_part = zf.testzip()
            if bad_part:
                raise AuditError(f"ZIP integrity failed at {bad_part}")
            if "ppt/presentation.xml" not in names:
                raise AuditError("ppt/presentation.xml is missing")

            presentation = _parse_xml(
                zf.read("ppt/presentation.xml"), "ppt/presentation.xml"
            )
            ordered = _ordered_slides(zf, names, presentation)
            invalid_pages = sorted(
                page for page in requested_pages if page > len(ordered)
            )
            if invalid_pages:
                raise AuditError(
                    "--slides selects physical page(s) beyond the deck: "
                    + ", ".join(map(str, invalid_pages))
                )
            root_cache: dict[str, ET.Element] = {
                "ppt/presentation.xml": presentation
            }

            def root_for(part: str) -> ET.Element | None:
                if not part:
                    return None
                if part not in names:
                    warnings.append(f"related XML part is missing: {part}")
                    return None
                if part not in root_cache:
                    root_cache[part] = _parse_xml(zf.read(part), part)
                return root_cache[part]

            for slide_meta in ordered:
                page = int(slide_meta["page"])
                slide_part = str(slide_meta["part"])
                slide_root = root_for(slide_part)
                assert slide_root is not None
                hidden = not (
                    bool(slide_meta["shown_in_presentation"])
                    and _shown(slide_root.get("show"))
                )
                selected_by_range = (
                    page in requested_pages if slides_specified else True
                )
                in_scope = selected_by_range and (include_hidden or not hidden)
                if not selected_by_range:
                    scope_exclusion = "not-selected"
                elif hidden and not include_hidden:
                    scope_exclusion = "hidden"
                else:
                    scope_exclusion = None

                if not in_scope:
                    slide_reports.append(
                        {
                            **slide_meta,
                            "hidden": hidden,
                            "selected_by_slides": selected_by_range,
                            "in_scope": False,
                            "scope_exclusion": scope_exclusion,
                            "layout_part": None,
                            "master_part": None,
                            "theme_part": None,
                            "runs": [],
                        }
                    )
                    continue

                layout_part = _related_part(
                    zf, names, slide_part, "/slideLayout"
                )
                layout_root = root_for(layout_part)
                master_part = (
                    _related_part(zf, names, layout_part, "/slideMaster")
                    if layout_part
                    else ""
                )
                master_root = root_for(master_part)
                theme_part = (
                    _related_part(zf, names, master_part, "/theme")
                    if master_part
                    else ""
                )
                theme_root = root_for(theme_part)
                theme = None
                if theme_part and theme_root is not None:
                    if theme_part not in themes:
                        themes[theme_part] = _read_theme(theme_root, theme_part)
                    theme = themes[theme_part]

                runs = _collect_origin_runs(
                    page=page,
                    hidden=hidden,
                    origin_level="slide",
                    origin_part=slide_part,
                    origin_root=slide_root,
                    layout_root=layout_root,
                    layout_part=layout_part,
                    master_root=master_root,
                    master_part=master_part,
                    theme=theme,
                    presentation=presentation,
                )
                if layout_root is not None:
                    runs.extend(
                        _collect_origin_runs(
                            page=page,
                            hidden=hidden,
                            origin_level="layout",
                            origin_part=layout_part,
                            origin_root=layout_root,
                            layout_root=None,
                            layout_part="",
                            master_root=master_root,
                            master_part=master_part,
                            theme=theme,
                            presentation=presentation,
                        )
                    )
                master_shown = _shown(slide_root.get("showMasterSp"))
                if layout_root is not None:
                    master_shown = master_shown and _shown(
                        layout_root.get("showMasterSp")
                    )
                if master_root is not None and master_shown:
                    runs.extend(
                        _collect_origin_runs(
                            page=page,
                            hidden=hidden,
                            origin_level="master",
                            origin_part=master_part,
                            origin_root=master_root,
                            layout_root=None,
                            layout_part="",
                            master_root=master_root,
                            master_part=master_part,
                            theme=theme,
                            presentation=presentation,
                        )
                    )
                all_runs.extend(runs)
                slide_reports.append(
                    {
                        **slide_meta,
                        "hidden": hidden,
                        "selected_by_slides": selected_by_range,
                        "in_scope": True,
                        "scope_exclusion": None,
                        "layout_part": layout_part or None,
                        "master_part": master_part or None,
                        "theme_part": theme_part or None,
                        "runs": runs,
                    }
                )
    except zipfile.BadZipFile as exc:
        raise AuditError(f"invalid PPTX ZIP package: {exc}") from exc
    except OSError as exc:
        raise AuditError(f"cannot read PPTX: {exc}") from exc

    failures = _validate(all_runs, expectations, fail_inconsistent_role)
    validation_enabled = bool(expectations or fail_inconsistent_role)
    audited_pages = [
        int(slide["page"]) for slide in slide_reports if slide["in_scope"]
    ]
    excluded_hidden_pages = [
        int(slide["page"])
        for slide in slide_reports
        if slide["scope_exclusion"] == "hidden"
    ]
    excluded_unselected_pages = [
        int(slide["page"])
        for slide in slide_reports
        if slide["scope_exclusion"] == "not-selected"
    ]
    if slides_specified:
        policy = "selected-including-hidden" if include_hidden else "selected-visible"
        description = (
            "requested physical pages; hidden pages are included"
            if include_hidden
            else "requested physical pages; hidden pages are excluded"
        )
    else:
        policy = "all-including-hidden" if include_hidden else "all-visible"
        description = (
            "all physical pages, including hidden pages"
            if include_hidden
            else "all visible physical pages; hidden pages are excluded"
        )
    scope: dict[str, object] = {
        "policy": policy,
        "description": description,
        "physical_order_source": "ppt/presentation.xml relationship order",
        "slides_specified": slides_specified,
        "slide_ranges": list(raw_slide_ranges),
        "requested_pages": sorted(requested_pages) if slides_specified else None,
        "include_hidden": include_hidden,
        "audited_pages": audited_pages,
        "excluded_hidden_pages": excluded_hidden_pages,
        "excluded_unselected_pages": excluded_unselected_pages,
        "applies_to": ["inventory", "unresolved", "validation"],
        "summary_counts_all_slides": True,
    }
    report: dict[str, object] = {
        "path": str(pptx),
        "ok": not failures,
        "status": "fail" if failures else "ok" if validation_enabled else "report",
        "limitations": list(LIMITATIONS),
        "scope": scope,
        "summary": {
            "slides": len(slide_reports),
            "visible": sum(not slide["hidden"] for slide in slide_reports),
            "hidden": sum(bool(slide["hidden"]) for slide in slide_reports),
            "audited_slides": len(audited_pages),
            "audited_visible": sum(
                bool(slide["in_scope"]) and not bool(slide["hidden"])
                for slide in slide_reports
            ),
            "audited_hidden": sum(
                bool(slide["in_scope"]) and bool(slide["hidden"])
                for slide in slide_reports
            ),
            "runs": len(all_runs),
            "roles": len({run["role"] for run in all_runs}),
            "unresolved_values": 0,
        },
        "themes": [theme.as_dict() for theme in themes.values()],
        "inventory": _build_inventory(all_runs),
        "slides": slide_reports,
        "unresolved": _unresolved(all_runs),
        "warnings": list(dict.fromkeys(warnings)),
        "validation": {
            "enabled": validation_enabled,
            "fail_inconsistent_role": fail_inconsistent_role,
            "audited_pages": audited_pages,
            "expectations": list(expectations),
            "failures": failures,
        },
    }
    report["summary"]["unresolved_values"] = len(report["unresolved"])
    return report


def _font_group_text(groups: Sequence[dict[str, object]]) -> str:
    values: list[str] = []
    for group in groups:
        value = group["value"] if group["resolved"] else "<unresolved>"
        detail = f"{value} x{group['count']}"
        if group.get("theme_references"):
            detail += " refs=" + "/".join(group["theme_references"])
        values.append(detail)
    return "; ".join(values) if values else "none"


def _scalar_group_text(
    groups: Sequence[dict[str, object]],
    *,
    size: bool = False,
) -> str:
    values: list[str] = []
    for group in groups:
        if not group["resolved"]:
            value = "<unresolved>"
        elif size:
            value = f"{group['points']:g}pt ({group['value']})"
        else:
            value = str(group["value"]).lower()
        values.append(f"{value} x{group['count']}")
    return "; ".join(values) if values else "none"


def _property_text(prop: dict[str, object]) -> str:
    value = prop.get("value")
    shown = str(value) if value is not None else "<unresolved>"
    if prop.get("theme_reference"):
        shown += f" [{prop['theme_reference']}]"
    source = prop.get("source_level") or "unresolved"
    if prop.get("inherited"):
        source += "/inherited"
    return f"{shown} <- {source}"


def report_to_text(report: dict[str, object]) -> str:
    summary = report["summary"]
    scope = report["scope"]
    audited_pages = ",".join(map(str, scope["audited_pages"])) or "none"
    lines = [
        f"PPTX typography audit: {report['path']}",
        (
            f"Slides: {summary['slides']} (visible {summary['visible']}, "
            f"hidden {summary['hidden']}); audited {summary['audited_slides']} "
            f"slide(s), {summary['runs']} text run(s)"
        ),
        f"Audit scope: {scope['policy']} ({scope['description']})",
        f"Audited physical pages: {audited_pages}",
        (
            "Excluded hidden physical pages: "
            + (",".join(map(str, scope["excluded_hidden_pages"])) or "none")
        ),
        "Limitations: " + report["limitations"][0],
        "             " + report["limitations"][1],
        "Themes:",
    ]
    if report["themes"]:
        for theme in report["themes"]:
            lines.append(
                "  - "
                f"{theme['part']}: major latin={theme['major']['latin'] or '<empty>'}, "
                f"eastAsia={theme['major']['eastAsia'] or '<empty>'}; "
                f"minor latin={theme['minor']['latin'] or '<empty>'}, "
                f"eastAsia={theme['minor']['eastAsia'] or '<empty>'}"
            )
    else:
        lines.append("  - none related")

    lines.append("Role inventory:")
    if not report["inventory"]:
        lines.append("  - no DrawingML text runs found")
    for item in report["inventory"]:
        lines.extend(
            [
                f"  [{item['role']}] runs={item['runs']} slides={','.join(map(str, item['slides']))}",
                "    Latin: " + _font_group_text(item["fonts"]["latin"]),
                "    East Asia: " + _font_group_text(item["fonts"]["eastAsia"]),
                "    Size: " + _scalar_group_text(item["sizes"], size=True),
                "    Bold: " + _scalar_group_text(item["bold"]),
            ]
        )

    lines.append("Run inventory (audited physical pages in true slide order):")
    for slide in report["slides"]:
        state = "hidden" if slide["hidden"] else "visible"
        if not slide["in_scope"]:
            lines.append(
                f"  slide {slide['page']} [{state}]: outside audit scope "
                f"({slide['scope_exclusion']})"
            )
            continue
        if not slide["runs"]:
            lines.append(f"  slide {slide['page']} [{state}]: no text runs")
            continue
        for run in slide["runs"]:
            excerpt = str(run["text"]).replace("\n", " ")
            if len(excerpt) > 60:
                excerpt = excerpt[:57] + "..."
            lines.append(
                f"  slide {slide['page']} [{state}] {run['role']} "
                f"{run['origin_level']} {excerpt!r}"
            )
            lines.append(
                "    "
                f"latin={_property_text(run['font']['latin'])}; "
                f"eastAsia={_property_text(run['font']['eastAsia'])}; "
                f"size={run['size'].get('points') if run['size']['resolved'] else '<unresolved>'}pt "
                f"<- {run['size'].get('source_level') or 'unresolved'}; "
                f"bold={run['bold'].get('value')} <- {run['bold'].get('source_level')}"
            )

    lines.append(f"Unresolved effective values: {len(report['unresolved'])}")
    for item in report["unresolved"][:30]:
        lines.append(
            f"  - slide {item['page']} {item['role']} {item['property']}: "
            f"{item['reason']}"
        )
    if len(report["unresolved"]) > 30:
        lines.append(f"  - ... {len(report['unresolved']) - 30} more")
    for warning in report["warnings"]:
        lines.append(f"Warning: {warning}")
    validation = report["validation"]
    status = str(report["status"]).upper()
    lines.append(f"Status: {status}")
    for failure in validation["failures"]:
        lines.append(f"  - [{failure['code']}] {failure['message']}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory effective and inherited PPTX fonts, sizes, and bold "
            "values by text role without modifying the deck."
        ),
        epilog=(
            "Scope policy: inventory and validation use all visible physical "
            "pages by default. --slides limits that scope in true presentation "
            "order; hidden pages enter scope only with --include-hidden."
        ),
    )
    parser.add_argument("pptx", type=Path)
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the complete machine-readable audit as JSON",
    )
    parser.add_argument(
        "--slides",
        action="append",
        default=[],
        metavar="RANGE",
        help=(
            "limit inventory and validation to physical true-order pages such "
            "as 1,3-5; repeat this option to take the union"
        ),
    )
    parser.add_argument(
        "--include-hidden",
        action="store_true",
        help=(
            "include hidden pages selected by the default/all-page scope or by "
            "--slides; hidden counts are always reported"
        ),
    )
    parser.add_argument(
        "--expect",
        action="append",
        default=[],
        metavar="ROLE=FONT,SIZE,BOLD",
        help=(
            "authorize typography for a role; repeat for alternatives. FONT "
            "defaults to Latin, or use latin:FONT|eastAsia:FONT; SIZE is points "
            "(18 or 18pt), with 1800hpt for raw OOXML hundredths; * is a wildcard"
        ),
    )
    parser.add_argument(
        "--fail-inconsistent-role",
        action="store_true",
        help=(
            "fail when an unconstrained role has multiple font, size, or bold "
            "variants; repeated --expect values authorize alternatives"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        expectations = [parse_expectation(spec) for spec in args.expect]
    except ValueError as exc:
        parser.error(str(exc))
    try:
        report = audit_pptx(
            args.pptx,
            expectations=expectations,
            fail_inconsistent_role=args.fail_inconsistent_role,
            slide_ranges=args.slides,
            include_hidden=args.include_hidden,
        )
    except AuditError as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "path": str(args.pptx.resolve()),
                        "ok": False,
                        "status": "fail",
                        "error": str(exc),
                        "limitations": list(LIMITATIONS),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(f"PPTX typography audit: {args.pptx}")
            print(f"Status: FAIL\n  - {exc}")
        return 1

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(report_to_text(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
