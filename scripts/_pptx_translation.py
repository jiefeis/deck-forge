#!/usr/bin/env python3
"""Translation QA for the PPTX structure audit.

``audit_pptx_structure.py`` owns the manifest and the edit-scope comparison;
this module owns what only the ``compare`` translation path needs: the language
heuristics, the text-box matcher, the exceptions-file schema, and the warning
builders. It is split out because ``audit_pptx_backups.py``,
``audit_pptx_properties.py``, and ``transplant_pptx_slides.py`` import
``audit_pptx_structure`` solely for ``AuditError`` and ``build_manifest`` and
never reach any of this code.

``_excerpt`` and ``_slide_mapping_evidence`` live here even though
``audit_pptx_structure`` also uses them: the dependency runs one way only
(``audit_pptx_structure`` imports this module), so shared helpers must sit on
this side of the boundary to keep the import acyclic.

This module is imported via the ``sys.path.insert(0, SCRIPT_DIR)`` pattern the
scripts already use, so they stay standalone and cwd-independent.
"""

from __future__ import annotations

import json
import math
import re
import sys
from fnmatch import fnmatchcase
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _pptx_common import AuditError  # noqa: E402

CJK_RE = re.compile(
    r"[\u2e80-\u2fff\u3040-\u30ff\u31f0-\u31ff\u3400-\u4dbf"
    r"\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]"
)
URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)\S+")
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
LATIN_WORD_RE = re.compile(r"[A-Za-z]+(?:['-][A-Za-z]+)*")
ENGLISH_FUNCTION_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "our",
    "should",
    "that",
    "the",
    "this",
    "to",
    "we",
    "will",
    "with",
    "you",
}
TRANSLATION_EXCEPTIONS_HELP = """
Translation exceptions JSON schema (version 1):
  {
    "version": 1,
    "allow_extra": [
      {"id": "p44-overlays", "target_page": 44, "name": "EN_overlay_*"}
    ],
    "allow_missing": [
      {"id": "p20-rebuilt", "source_page": 20, "key": "id:42"}
    ],
    "box_mappings": [
      {"id": "chart-label", "source_page": 20, "source_key": "id:42",
       "target_page": 44, "target_key": "id:109"}
    ]
  }

allow_extra requires target_page; allow_missing requires source_page. Rules use
case-sensitive fnmatch globs in shape, name, and/or key. "shape" matches either
the shape name or box key; name/key constrain their respective field. Explicit
box_mappings use exact keys and run before automatic shape-id/placeholder/bbox
matching. Wildcard rules with fewer than three literal letters/digits are
rejected as too broad. Invalid, ambiguous, unmatched, conflicting, and unused
rules are reported; --strict-translation makes those issues fail the audit.

Slide mapping safety:
With --map-slides auto, a true-order fallback between different stable slide
IDs is provisional and emits translation-order-fallback during translation
checks; --strict-translation fails on it. Use --map-slides order to explicitly
select true-order mapping when comparing independent deck versions.
"""


def _slide_mapping_evidence(
    source_slide: dict[str, object],
    target_slide: dict[str, object],
    method: str,
    policy: str,
) -> dict[str, object]:
    stable_id_match = source_slide["slide_id"] == target_slide["slide_id"]
    provisional = policy == "auto" and method == "true-order" and not stable_id_match
    if method == "slide-id":
        basis = "matching-stable-slide-id"
    elif policy == "order":
        basis = "user-selected-true-order"
    else:
        basis = "automatic-true-order-fallback"
    return {
        "method": method,
        "policy": policy,
        "basis": basis,
        "source_slide_id": source_slide["slide_id"],
        "target_slide_id": target_slide["slide_id"],
        "stable_slide_id_match": stable_id_match,
        "provisional": provisional,
    }


def _question_title(title: str) -> bool:
    value = title.rstrip()
    closers = "\"')]}\u2019\u201d\u3009\u300b\u300d\u300f\uff09\uff3d\uff5d"
    while value and value[-1] in closers:
        value = value[:-1].rstrip()
    return value.endswith(("?", "\uFF1F"))


def _excerpt(text: str, limit: int = 80) -> str:
    value = " ".join(text.split())
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _obvious_english_prose(text: str) -> str | None:
    for paragraph in re.split(r"[\r\n]+", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        cleaned = URL_RE.sub(" ", EMAIL_RE.sub(" ", paragraph))
        words = LATIN_WORD_RE.findall(cleaned)
        latin_characters = sum(sum(character.isalpha() for character in word) for word in words)
        if len(words) < 7 or latin_characters < 32:
            continue
        lowercase_words = [word for word in words if any(char.islower() for char in word)]
        if len(lowercase_words) < 5:
            continue
        function_word_count = sum(
            word.casefold() in ENGLISH_FUNCTION_WORDS for word in words
        )
        sentence_punctuation = bool(re.search(r"[.!?](?:[\"')\]]*\s*)$", cleaned))
        if function_word_count < 2 and not (sentence_punctuation and len(words) >= 9):
            continue
        cjk_characters = len(CJK_RE.findall(cleaned))
        if cjk_characters and latin_characters < cjk_characters * 4:
            continue
        return paragraph
    return None


def _placeholder_signature(box: dict[str, object]) -> tuple[str, str] | None:
    placeholder_type = str(box.get("placeholder_type", ""))
    placeholder_index = str(box.get("placeholder_index", ""))
    if not placeholder_type and not placeholder_index:
        return None
    return placeholder_type, placeholder_index


def _normalized_bbox(
    box: dict[str, object], slide_size: dict[str, int]
) -> tuple[float, float, float, float] | None:
    bbox = box.get("bbox")
    if not isinstance(bbox, dict):
        return None
    width = int(slide_size.get("cx", 0))
    height = int(slide_size.get("cy", 0))
    if width <= 0 or height <= 0:
        return None
    try:
        box_width = int(bbox["cx"])
        box_height = int(bbox["cy"])
        if box_width <= 0 or box_height <= 0:
            return None
        return (
            (int(bbox["x"]) + box_width / 2) / width,
            (int(bbox["y"]) + box_height / 2) / height,
            box_width / width,
            box_height / height,
        )
    except (KeyError, TypeError, ValueError):
        return None


def _geometry_cost(
    source_box: dict[str, object],
    target_box: dict[str, object],
    source_size: dict[str, int],
    target_size: dict[str, int],
) -> tuple[float, float] | None:
    source_geometry = _normalized_bbox(source_box, source_size)
    target_geometry = _normalized_bbox(target_box, target_size)
    if source_geometry is None or target_geometry is None:
        return None
    source_x, source_y, source_width, source_height = source_geometry
    target_x, target_y, target_width, target_height = target_geometry
    center_distance = math.hypot(source_x - target_x, source_y - target_y)
    width_ratio = min(source_width, target_width) / max(source_width, target_width)
    height_ratio = min(source_height, target_height) / max(source_height, target_height)
    if center_distance > 0.04 or width_ratio < 0.55 or height_ratio < 0.50:
        return None
    size_delta = (1 - width_ratio) + (1 - height_ratio)
    return center_distance + size_delta * 0.02, center_distance


def _map_text_boxes(
    source_boxes: list[dict[str, object]],
    target_boxes: list[dict[str, object]],
    source_size: dict[str, int],
    target_size: dict[str, int],
) -> tuple[
    list[tuple[dict[str, object], dict[str, object], dict[str, object]]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    matches: list[
        tuple[dict[str, object], dict[str, object], dict[str, object]]
    ] = []
    used_source: set[str] = set()
    used_target: set[str] = set()

    def add_match(
        source_box: dict[str, object],
        target_box: dict[str, object],
        method: str,
        **details: object,
    ) -> None:
        source_key = str(source_box["key"])
        target_key = str(target_box["key"])
        used_source.add(source_key)
        used_target.add(target_key)
        record: dict[str, object] = {
            "source_text_box": source_key,
            "target_text_box": target_key,
            "source_shape_id": source_box.get("shape_id", ""),
            "target_shape_id": target_box.get("shape_id", ""),
            "mapping": method,
            **details,
        }
        matches.append((source_box, target_box, record))

    source_by_id: dict[str, list[dict[str, object]]] = {}
    target_by_id: dict[str, list[dict[str, object]]] = {}
    for box in source_boxes:
        if box.get("shape_id"):
            source_by_id.setdefault(str(box["shape_id"]), []).append(box)
    for box in target_boxes:
        if box.get("shape_id"):
            target_by_id.setdefault(str(box["shape_id"]), []).append(box)
    for shape_id in sorted(set(source_by_id) & set(target_by_id)):
        if len(source_by_id[shape_id]) == len(target_by_id[shape_id]) == 1:
            add_match(source_by_id[shape_id][0], target_by_id[shape_id][0], "shape-id")

    remaining_source = [box for box in source_boxes if str(box["key"]) not in used_source]
    remaining_target = [box for box in target_boxes if str(box["key"]) not in used_target]
    source_by_placeholder: dict[tuple[str, str], list[dict[str, object]]] = {}
    target_by_placeholder: dict[tuple[str, str], list[dict[str, object]]] = {}
    for box in remaining_source:
        signature = _placeholder_signature(box)
        if signature:
            source_by_placeholder.setdefault(signature, []).append(box)
    for box in remaining_target:
        signature = _placeholder_signature(box)
        if signature:
            target_by_placeholder.setdefault(signature, []).append(box)
    for signature in sorted(set(source_by_placeholder) & set(target_by_placeholder)):
        if (
            len(source_by_placeholder[signature]) == 1
            and len(target_by_placeholder[signature]) == 1
        ):
            add_match(
                source_by_placeholder[signature][0],
                target_by_placeholder[signature][0],
                "placeholder",
                placeholder_type=signature[0],
                placeholder_index=signature[1],
            )

    remaining_source = [box for box in source_boxes if str(box["key"]) not in used_source]
    remaining_target = [box for box in target_boxes if str(box["key"]) not in used_target]
    candidates: dict[tuple[str, str], tuple[float, float]] = {}
    for source_box in remaining_source:
        for target_box in remaining_target:
            cost = _geometry_cost(source_box, target_box, source_size, target_size)
            if cost is not None:
                candidates[(str(source_box["key"]), str(target_box["key"]))] = cost

    source_rankings: dict[str, list[tuple[float, str, float]]] = {}
    target_rankings: dict[str, list[tuple[float, str, float]]] = {}
    for (source_key, target_key), (cost, distance) in candidates.items():
        source_rankings.setdefault(source_key, []).append((cost, target_key, distance))
        target_rankings.setdefault(target_key, []).append((cost, source_key, distance))
    for ranking in list(source_rankings.values()) + list(target_rankings.values()):
        ranking.sort()

    source_lookup = {str(box["key"]): box for box in remaining_source}
    target_lookup = {str(box["key"]): box for box in remaining_target}

    def unambiguous(ranking: list[tuple[float, str, float]]) -> bool:
        return len(ranking) == 1 or ranking[1][0] - ranking[0][0] >= 0.005

    for source_key in sorted(source_rankings):
        source_ranking = source_rankings[source_key]
        if not unambiguous(source_ranking):
            continue
        cost, target_key, center_distance = source_ranking[0]
        target_ranking = target_rankings[target_key]
        if not unambiguous(target_ranking) or target_ranking[0][1] != source_key:
            continue
        if source_key in used_source or target_key in used_target:
            continue
        add_match(
            source_lookup[source_key],
            target_lookup[target_key],
            "geometry",
            geometry_cost=round(cost, 6),
            center_distance=round(center_distance, 6),
        )

    source_order = {str(box["key"]): index for index, box in enumerate(source_boxes)}
    matches.sort(key=lambda item: source_order[str(item[0]["key"])])
    unmatched_source = [box for box in source_boxes if str(box["key"]) not in used_source]
    unmatched_target = [box for box in target_boxes if str(box["key"]) not in used_target]
    return matches, unmatched_source, unmatched_target


def _exception_issue(
    code: str,
    message: str,
    *,
    rule_id: str | None = None,
    rule_type: str | None = None,
    **details: object,
) -> dict[str, object]:
    issue: dict[str, object] = {
        "code": code,
        "severity": "warning",
        "message": message,
        **details,
    }
    if rule_id is not None:
        issue["rule_id"] = rule_id
    if rule_type is not None:
        issue["rule_type"] = rule_type
    return issue


def _valid_exception_page(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _glob_rule_too_broad(patterns: dict[str, str]) -> bool:
    combined = " ".join(patterns.values())
    if not any(character in combined for character in "*?["):
        return False
    without_classes = re.sub(r"\[[^\]]*\]", "", combined)
    literal_alphanumeric = re.sub(r"[^A-Za-z0-9]", "", without_classes)
    return len(literal_alphanumeric) < 3


def _load_translation_exceptions(
    value: str | Path | dict[str, object] | None,
) -> dict[str, object]:
    config: dict[str, object] = {
        "source": None,
        "allow_extra": [],
        "allow_missing": [],
        "box_mappings": [],
        "issues": [],
    }
    if value is None:
        return config

    if isinstance(value, dict):
        raw = value
        config["source"] = "inline"
    else:
        path = Path(value).expanduser().resolve()
        config["source"] = str(path)
        try:
            raw_value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AuditError(f"invalid translation exceptions JSON in {path}: {exc}") from exc
        if not isinstance(raw_value, dict):
            config["issues"].append(
                _exception_issue(
                    "translation-exception-schema",
                    "translation exceptions root must be a JSON object",
                )
            )
            return config
        raw = raw_value

    allowed_top_level = {"version", "allow_extra", "allow_missing", "box_mappings"}
    unknown_top_level = sorted(set(raw) - allowed_top_level)
    if unknown_top_level:
        config["issues"].append(
            _exception_issue(
                "translation-exception-schema",
                "unknown translation exceptions keys: " + ", ".join(unknown_top_level),
            )
        )
    if "version" in raw and raw["version"] != 1:
        config["issues"].append(
            _exception_issue(
                "translation-exception-schema",
                "translation exceptions version must be 1",
            )
        )

    seen_ids: set[str] = set()

    def normalize_allow_rules(rule_type: str, page_field: str) -> None:
        raw_rules = raw.get(rule_type, [])
        if not isinstance(raw_rules, list):
            config["issues"].append(
                _exception_issue(
                    "translation-exception-schema",
                    f"{rule_type} must be an array",
                    rule_type=rule_type,
                )
            )
            return
        destination: list[dict[str, object]] = config[rule_type]
        allowed_fields = {"id", page_field, "shape", "name", "key"}
        for index, raw_rule in enumerate(raw_rules):
            token = f"{rule_type}[{index}]"
            if not isinstance(raw_rule, dict):
                config["issues"].append(
                    _exception_issue(
                        "translation-exception-schema",
                        f"{token} must be an object",
                        rule_id=token,
                        rule_type=rule_type,
                    )
                )
                continue
            rule_id = str(raw_rule.get("id") or token)
            problems: list[str] = []
            unknown_fields = sorted(set(raw_rule) - allowed_fields)
            if unknown_fields:
                problems.append("unknown fields: " + ", ".join(unknown_fields))
            page = raw_rule.get(page_field)
            if not _valid_exception_page(page):
                problems.append(f"{page_field} must be a positive integer")
            patterns: dict[str, str] = {}
            for field in ("shape", "name", "key"):
                if field not in raw_rule:
                    continue
                pattern = raw_rule[field]
                if not isinstance(pattern, str) or not pattern:
                    problems.append(f"{field} must be a non-empty fnmatch glob")
                else:
                    patterns[field] = pattern
            if not patterns:
                problems.append("one of shape, name, or key is required")
            if rule_id in seen_ids:
                problems.append(f"duplicate rule id {rule_id!r}")
            if problems:
                config["issues"].append(
                    _exception_issue(
                        "translation-exception-schema",
                        f"{token}: " + "; ".join(problems),
                        rule_id=rule_id,
                        rule_type=rule_type,
                    )
                )
                continue
            seen_ids.add(rule_id)
            if _glob_rule_too_broad(patterns):
                config["issues"].append(
                    _exception_issue(
                        "translation-exception-too-broad",
                        (
                            f"{rule_id}: wildcard rule needs at least three literal "
                            "letters or digits"
                        ),
                        rule_id=rule_id,
                        rule_type=rule_type,
                        page=page,
                        patterns=patterns,
                    )
                )
                continue
            destination.append(
                {
                    "_token": token,
                    "id": rule_id,
                    page_field: page,
                    "patterns": patterns,
                }
            )

    normalize_allow_rules("allow_extra", "target_page")
    normalize_allow_rules("allow_missing", "source_page")

    raw_mappings = raw.get("box_mappings", [])
    if not isinstance(raw_mappings, list):
        config["issues"].append(
            _exception_issue(
                "translation-exception-schema",
                "box_mappings must be an array",
                rule_type="box_mappings",
            )
        )
    else:
        allowed_mapping_fields = {
            "id",
            "source_page",
            "source_key",
            "target_page",
            "target_key",
        }
        destination_mappings: list[dict[str, object]] = config["box_mappings"]
        for index, raw_rule in enumerate(raw_mappings):
            token = f"box_mappings[{index}]"
            if not isinstance(raw_rule, dict):
                config["issues"].append(
                    _exception_issue(
                        "translation-exception-schema",
                        f"{token} must be an object",
                        rule_id=token,
                        rule_type="box_mappings",
                    )
                )
                continue
            rule_id = str(raw_rule.get("id") or token)
            problems = []
            unknown_fields = sorted(set(raw_rule) - allowed_mapping_fields)
            if unknown_fields:
                problems.append("unknown fields: " + ", ".join(unknown_fields))
            for field in ("source_page", "target_page"):
                if not _valid_exception_page(raw_rule.get(field)):
                    problems.append(f"{field} must be a positive integer")
            for field in ("source_key", "target_key"):
                key = raw_rule.get(field)
                if not isinstance(key, str) or not key:
                    problems.append(f"{field} must be a non-empty exact box key")
                elif any(character in key for character in "*?["):
                    problems.append(f"{field} must be exact, not a glob")
            if rule_id in seen_ids:
                problems.append(f"duplicate rule id {rule_id!r}")
            if problems:
                config["issues"].append(
                    _exception_issue(
                        "translation-exception-schema",
                        f"{token}: " + "; ".join(problems),
                        rule_id=rule_id,
                        rule_type="box_mappings",
                    )
                )
                continue
            seen_ids.add(rule_id)
            destination_mappings.append(
                {
                    "_token": token,
                    "id": rule_id,
                    "source_page": raw_rule["source_page"],
                    "source_key": raw_rule["source_key"],
                    "target_page": raw_rule["target_page"],
                    "target_key": raw_rule["target_key"],
                }
            )
    return config


def _allow_rule_matches_box(
    rule: dict[str, object],
    box: dict[str, object],
) -> bool:
    patterns: dict[str, str] = rule["patterns"]
    name = str(box.get("name", ""))
    key = str(box.get("key", ""))
    if "shape" in patterns and not (
        fnmatchcase(name, patterns["shape"]) or fnmatchcase(key, patterns["shape"])
    ):
        return False
    if "name" in patterns and not fnmatchcase(name, patterns["name"]):
        return False
    if "key" in patterns and not fnmatchcase(key, patterns["key"]):
        return False
    return True


def _explicit_box_mappings(
    pairs: list[tuple[dict[str, object], dict[str, object], str]],
    exceptions: dict[str, object],
    used_rule_tokens: set[str],
) -> tuple[
    dict[
        tuple[int, int],
        list[tuple[dict[str, object], dict[str, object], dict[str, object]]],
    ],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    """Resolve ``box_mappings`` rules into per-pair explicit text-box matches.

    Runs before automatic matching so an operator-reviewed pairing always wins.
    Adds the tokens it consumed to ``used_rule_tokens``.
    """

    exceptions_applied: list[dict[str, object]] = []
    exception_issues: list[dict[str, object]] = []
    pair_lookup = {
        (int(source_slide["page"]), int(target_slide["page"])): (
            source_slide,
            target_slide,
            slide_mapping,
        )
        for source_slide, target_slide, slide_mapping in pairs
    }
    explicit_by_pair: dict[
        tuple[int, int],
        list[tuple[dict[str, object], dict[str, object], dict[str, object]]],
    ] = {}
    explicitly_used_source: set[tuple[int, str]] = set()
    explicitly_used_target: set[tuple[int, str]] = set()
    for rule in exceptions["box_mappings"]:
        source_page = int(rule["source_page"])
        target_page = int(rule["target_page"])
        pair_key = (source_page, target_page)
        rule_id = str(rule["id"])
        token = str(rule["_token"])
        pair = pair_lookup.get(pair_key)
        if pair is None:
            exception_issues.append(
                _exception_issue(
                    "translation-exception-mapping-no-match",
                    (
                        f"{rule_id}: source page {source_page} is not mapped to "
                        f"target page {target_page}"
                    ),
                    rule_id=rule_id,
                    rule_type="box_mappings",
                    source_page=source_page,
                    target_page=target_page,
                )
            )
            continue
        source_slide, target_slide, _ = pair
        source_boxes = {
            str(box["key"]): box for box in source_slide["text_boxes"]
        }
        target_boxes = {
            str(box["key"]): box for box in target_slide["text_boxes"]
        }
        source_key = str(rule["source_key"])
        target_key = str(rule["target_key"])
        source_box = source_boxes.get(source_key)
        target_box = target_boxes.get(target_key)
        if source_box is None or target_box is None:
            missing_endpoints = []
            if source_box is None:
                missing_endpoints.append(f"source {source_page}/{source_key}")
            if target_box is None:
                missing_endpoints.append(f"target {target_page}/{target_key}")
            exception_issues.append(
                _exception_issue(
                    "translation-exception-mapping-no-match",
                    f"{rule_id}: box mapping endpoint not found: " + ", ".join(missing_endpoints),
                    rule_id=rule_id,
                    rule_type="box_mappings",
                    source_page=source_page,
                    target_page=target_page,
                    source_key=source_key,
                    target_key=target_key,
                )
            )
            continue
        source_endpoint = (source_page, source_key)
        target_endpoint = (target_page, target_key)
        if (
            source_endpoint in explicitly_used_source
            or target_endpoint in explicitly_used_target
        ):
            exception_issues.append(
                _exception_issue(
                    "translation-exception-mapping-conflict",
                    f"{rule_id}: source or target box is already explicitly mapped",
                    rule_id=rule_id,
                    rule_type="box_mappings",
                    source_page=source_page,
                    target_page=target_page,
                    source_key=source_key,
                    target_key=target_key,
                )
            )
            continue
        explicitly_used_source.add(source_endpoint)
        explicitly_used_target.add(target_endpoint)
        used_rule_tokens.add(token)
        mapping_record = {
            "source_text_box": source_key,
            "target_text_box": target_key,
            "source_shape_id": source_box.get("shape_id", ""),
            "target_shape_id": target_box.get("shape_id", ""),
            "mapping": "exception-explicit",
            "exception_rule_id": rule_id,
        }
        explicit_by_pair.setdefault(pair_key, []).append(
            (source_box, target_box, mapping_record)
        )
        exceptions_applied.append(
            {
                "kind": "box_mapping",
                "rule_id": rule_id,
                "source_page": source_page,
                "source_key": source_key,
                "target_page": target_page,
                "target_key": target_key,
            }
        )
    return explicit_by_pair, exceptions_applied, exception_issues


def _slide_pair_warnings(
    pairs: list[tuple[dict[str, object], dict[str, object], str]],
    unmatched_source: list[dict[str, object]],
    unmatched_target: list[dict[str, object]],
    mapping_policy: str,
) -> list[dict[str, object]]:
    """Slide-level findings: unpaired slides and provisional order fallbacks."""

    warnings: list[dict[str, object]] = []
    for source_slide in unmatched_source:
        warnings.append(
            {
                "code": "translation-slide-missing",
                "severity": "warning",
                "source_page": source_slide["page"],
                "slide_id": source_slide["slide_id"],
                "message": f"source slide {source_slide['page']} has no target mapping",
            }
        )
    for target_slide in unmatched_target:
        warnings.append(
            {
                "code": "translation-slide-extra",
                "severity": "warning",
                "target_page": target_slide["page"],
                "slide_id": target_slide["slide_id"],
                "message": f"target slide {target_slide['page']} has no source mapping",
            }
        )

    for source_slide, target_slide, slide_mapping in pairs:
        evidence = _slide_mapping_evidence(
            source_slide,
            target_slide,
            slide_mapping,
            mapping_policy,
        )
        if evidence["provisional"]:
            warnings.append(
                {
                    "code": "translation-order-fallback",
                    "severity": "warning",
                    "source_page": source_slide["page"],
                    "target_page": target_slide["page"],
                    "source_slide_id": source_slide["slide_id"],
                    "target_slide_id": target_slide["slide_id"],
                    "mapping": slide_mapping,
                    "evidence": evidence,
                    "message": (
                        f"auto mapping provisionally paired source page "
                        f"{source_slide['page']} (id {source_slide['slide_id']}) with "
                        f"target page {target_slide['page']} (id {target_slide['slide_id']}) "
                        "by true order"
                    ),
                }
            )
    return warnings


def _text_box_warnings(
    pairs: list[tuple[dict[str, object], dict[str, object], str]],
    explicit_by_pair: dict[
        tuple[int, int],
        list[tuple[dict[str, object], dict[str, object], dict[str, object]]],
    ],
    source_size: dict[str, int],
    target_size: dict[str, int],
    exceptions: dict[str, object],
    used_rule_tokens: set[str],
    matched_rule_tokens: set[str],
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    """Per-pair findings: unmatched text boxes and title question-mark drift.

    Records every accepted box pairing, applies the allow_missing/allow_extra
    rules, and reports the tokens it touched through the two token sets.
    """

    warnings: list[dict[str, object]] = []
    box_mappings: list[dict[str, object]] = []
    exceptions_applied: list[dict[str, object]] = []
    exception_issues: list[dict[str, object]] = []
    for source_slide, target_slide, slide_mapping in pairs:
        source_page = int(source_slide["page"])
        target_page = int(target_slide["page"])
        explicit_matches = explicit_by_pair.get((source_page, target_page), [])
        explicit_source_keys = {str(item[0]["key"]) for item in explicit_matches}
        explicit_target_keys = {str(item[1]["key"]) for item in explicit_matches}
        automatic_matches, missing_boxes, extra_boxes = _map_text_boxes(
            [
                box
                for box in source_slide["text_boxes"]
                if str(box["key"]) not in explicit_source_keys
            ],
            [
                box
                for box in target_slide["text_boxes"]
                if str(box["key"]) not in explicit_target_keys
            ],
            source_size,
            target_size,
        )
        for _, _, record in explicit_matches + automatic_matches:
            box_mappings.append(
                {
                    "source_page": source_page,
                    "target_page": target_page,
                    "slide_id": source_slide["slide_id"],
                    "slide_mapping": slide_mapping,
                    **record,
                }
            )
        for box in missing_boxes:
            key = str(box["key"])
            matching_rules = [
                rule
                for rule in exceptions["allow_missing"]
                if int(rule["source_page"]) == source_page
                and _allow_rule_matches_box(rule, box)
            ]
            matched_rule_tokens.update(str(rule["_token"]) for rule in matching_rules)
            if len(matching_rules) == 1:
                rule = matching_rules[0]
                used_rule_tokens.add(str(rule["_token"]))
                exceptions_applied.append(
                    {
                        "kind": "allow_missing",
                        "rule_id": rule["id"],
                        "source_page": source_page,
                        "target_page": target_page,
                        "shape_key": key,
                        "shape_name": box.get("name", ""),
                        "patterns": rule["patterns"],
                    }
                )
                continue
            if len(matching_rules) > 1:
                exception_issues.append(
                    _exception_issue(
                        "translation-exception-ambiguous",
                        (
                            f"source {source_page}/{key} matches multiple allow_missing "
                            "rules"
                        ),
                        rule_type="allow_missing",
                        source_page=source_page,
                        target_page=target_page,
                        text_box=key,
                        rule_ids=[rule["id"] for rule in matching_rules],
                    )
                )
            warnings.append(
                {
                    "code": "translation-text-box-missing",
                    "severity": "warning",
                    "source_page": source_slide["page"],
                    "target_page": target_slide["page"],
                    "slide_id": source_slide["slide_id"],
                    "slide_mapping": slide_mapping,
                    "mapping": "unmatched-after-shape-id-placeholder-geometry",
                    "text_box": key,
                    "shape_key": key,
                    "shape_name": box.get("name", ""),
                    "message": (
                        f"target slide {target_slide['page']} is missing text box "
                        f"{key} ({box['name']!r})"
                    ),
                }
            )
        for box in extra_boxes:
            key = str(box["key"])
            matching_rules = [
                rule
                for rule in exceptions["allow_extra"]
                if int(rule["target_page"]) == target_page
                and _allow_rule_matches_box(rule, box)
            ]
            matched_rule_tokens.update(str(rule["_token"]) for rule in matching_rules)
            if len(matching_rules) == 1:
                rule = matching_rules[0]
                used_rule_tokens.add(str(rule["_token"]))
                exceptions_applied.append(
                    {
                        "kind": "allow_extra",
                        "rule_id": rule["id"],
                        "source_page": source_page,
                        "target_page": target_page,
                        "shape_key": key,
                        "shape_name": box.get("name", ""),
                        "patterns": rule["patterns"],
                    }
                )
                continue
            if len(matching_rules) > 1:
                exception_issues.append(
                    _exception_issue(
                        "translation-exception-ambiguous",
                        (
                            f"target {target_page}/{key} matches multiple allow_extra rules"
                        ),
                        rule_type="allow_extra",
                        source_page=source_page,
                        target_page=target_page,
                        text_box=key,
                        rule_ids=[rule["id"] for rule in matching_rules],
                    )
                )
            warnings.append(
                {
                    "code": "translation-text-box-extra",
                    "severity": "warning",
                    "source_page": source_slide["page"],
                    "target_page": target_slide["page"],
                    "slide_id": source_slide["slide_id"],
                    "slide_mapping": slide_mapping,
                    "mapping": "unmatched-after-shape-id-placeholder-geometry",
                    "text_box": key,
                    "shape_key": key,
                    "shape_name": box.get("name", ""),
                    "message": (
                        f"target slide {target_slide['page']} has extra text box "
                        f"{key} ({box['name']!r})"
                    ),
                }
            )
        source_question = _question_title(str(source_slide["title"]))
        target_question = _question_title(str(target_slide["title"]))
        if source_question != target_question:
            warnings.append(
                {
                    "code": "translation-title-question-mismatch",
                    "severity": "warning",
                    "source_page": source_slide["page"],
                    "target_page": target_slide["page"],
                    "slide_id": source_slide["slide_id"],
                    "mapping": slide_mapping,
                    "mapping_scope": "slide",
                    "message": (
                        f"title question-mark logic differs on source slide "
                        f"{source_slide['page']} and target slide {target_slide['page']}"
                    ),
                }
            )
    return warnings, box_mappings, exceptions_applied, exception_issues


def _language_residue_warnings(
    target_slides: list[dict[str, object]],
    target_language: str | None,
) -> list[dict[str, object]]:
    """Untranslated-residue scan over the target deck only."""

    warnings: list[dict[str, object]] = []
    if target_language == "en":
        for target_slide in target_slides:
            for box in target_slide["text_boxes"]:
                text = str(box["text"])
                if not CJK_RE.search(text):
                    continue
                warnings.append(
                    {
                        "code": "translation-cjk-in-english",
                        "severity": "warning",
                        "target_page": target_slide["page"],
                        "slide_id": target_slide["slide_id"],
                        "text_box": box["key"],
                        "mapping": "target-language-scan",
                        "target_language": target_language,
                        "excerpt": _excerpt(text),
                        "message": (
                            f"target English slide {target_slide['page']} retains CJK text "
                            f"in {box['key']}: {_excerpt(text)!r}"
                        ),
                    }
                )
    elif target_language == "zh":
        for target_slide in target_slides:
            for box in target_slide["text_boxes"]:
                prose = _obvious_english_prose(str(box["text"]))
                if prose is None:
                    continue
                warnings.append(
                    {
                        "code": "translation-english-prose-in-chinese",
                        "severity": "warning",
                        "target_page": target_slide["page"],
                        "slide_id": target_slide["slide_id"],
                        "text_box": box["key"],
                        "mapping": "target-language-scan",
                        "target_language": target_language,
                        "excerpt": _excerpt(prose),
                        "message": (
                            f"target Chinese slide {target_slide['page']} retains obvious "
                            f"English prose in {box['key']}: {_excerpt(prose)!r}"
                        ),
                    }
                )
    return warnings


def _translation_warnings(
    pairs: list[tuple[dict[str, object], dict[str, object], str]],
    unmatched_source: list[dict[str, object]],
    unmatched_target: list[dict[str, object]],
    target_slides: list[dict[str, object]],
    source_size: dict[str, int],
    target_size: dict[str, int],
    mapping_policy: str,
    target_language: str | None,
    exceptions: dict[str, object],
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    used_rule_tokens: set[str] = set()
    matched_rule_tokens: set[str] = set()

    explicit_by_pair, explicit_applied, explicit_issues = _explicit_box_mappings(
        pairs, exceptions, used_rule_tokens
    )
    warnings = _slide_pair_warnings(
        pairs, unmatched_source, unmatched_target, mapping_policy
    )
    box_warnings, box_mappings, box_applied, box_issues = _text_box_warnings(
        pairs,
        explicit_by_pair,
        source_size,
        target_size,
        exceptions,
        used_rule_tokens,
        matched_rule_tokens,
    )
    warnings += box_warnings
    warnings += _language_residue_warnings(target_slides, target_language)

    unused_issues: list[dict[str, object]] = []
    for rule_type in ("allow_missing", "allow_extra"):
        for rule in exceptions[rule_type]:
            token = str(rule["_token"])
            if token in used_rule_tokens or token in matched_rule_tokens:
                continue
            page_field = "source_page" if rule_type == "allow_missing" else "target_page"
            unused_issues.append(
                _exception_issue(
                    "translation-exception-unused",
                    f"{rule['id']}: rule matched no pending {rule_type} box",
                    rule_id=str(rule["id"]),
                    rule_type=rule_type,
                    page=rule[page_field],
                    patterns=rule["patterns"],
                )
            )
    return (
        warnings,
        box_mappings,
        explicit_applied + box_applied,
        list(exceptions["issues"]) + explicit_issues + box_issues + unused_issues,
    )
