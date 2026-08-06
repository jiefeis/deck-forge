#!/usr/bin/env python3
"""Read-only full-pixel audit for source/target PPTX page renders.

Inputs are directories produced by ``render_pptx.ps1`` and are aligned by the
physical index in ``slide-NNN.png``. ``--page-map`` can instead compare explicit
source/target physical-page pairs such as an original slide and an appended
hidden backup. The audit never resizes, saves, or otherwise modifies an input
image.

Exit codes:
    0  audit passed
    1  audit completed and found policy violations
    2  invalid arguments, inputs, or unreadable images
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Iterable, Sequence

try:
    from PIL import Image, ImageChops, ImageStat, UnidentifiedImageError
except ImportError:
    print("audit_rendered_pages: Pillow required. Run: pip install Pillow", file=sys.stderr)
    raise SystemExit(2)


SLIDE_RE = re.compile(r"^slide-(\d+)\.png$", re.IGNORECASE)
DEFAULT_PIXEL_TOLERANCE = 2
DEFAULT_MAX_CHANGED_RATIO = 0.0001
DEFAULT_WHITE_LEVEL = 250
DEFAULT_BLACK_LEVEL = 5
DEFAULT_SOLID_PIXEL_RATIO = 0.985
DEFAULT_LOW_VARIANCE = 4.0
DEFAULT_BRIGHTNESS_JUMP = 64.0
DEFAULT_VARIANCE_DROP_RATIO = 0.10


class AuditError(RuntimeError):
    """Raised when rendered-page inputs cannot be audited reliably."""


def parse_slide_ranges(spec: str) -> set[int]:
    """Parse one-based physical slide ranges such as ``1-3,5,8``."""

    result: set[int] = set()
    if not spec.strip():
        return result
    for raw_token in spec.split(","):
        token = raw_token.strip()
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", token)
        if not match:
            raise AuditError(f"invalid slide range token: {token!r}")
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if start < 1 or end < start:
            raise AuditError(f"invalid slide range: {token!r}")
        if end - start > 100000:
            raise AuditError(f"slide range is too large: {token!r}")
        result.update(range(start, end + 1))
    return result


def _coerce_slides(value: Iterable[int] | str | None) -> set[int]:
    if value is None:
        return set()
    if isinstance(value, str):
        return parse_slide_ranges(value)
    result = {int(index) for index in value}
    if any(index < 1 for index in result):
        raise AuditError("physical slide indices must be positive")
    return result


def parse_page_maps(specs: Iterable[str] | None) -> dict[int, int]:
    """Parse repeatable ``SOURCE:TARGET`` physical-page mappings."""

    mappings: dict[int, int] = {}
    used_targets: set[int] = set()
    for raw_spec in specs or []:
        spec = str(raw_spec).strip()
        match = re.fullmatch(r"(\d+)\s*:\s*(\d+)", spec)
        if not match:
            raise AuditError(
                f"invalid page map {raw_spec!r}; expected SOURCE_PAGE:TARGET_PAGE"
            )
        source_index, target_index = map(int, match.groups())
        if source_index < 1 or target_index < 1:
            raise AuditError("page-map indices must be positive")
        if source_index in mappings:
            raise AuditError(f"source page {source_index} is mapped more than once")
        if target_index in used_targets:
            raise AuditError(f"target page {target_index} is mapped more than once")
        mappings[source_index] = target_index
        used_targets.add(target_index)
    return mappings


def indexed_images(directory: Path) -> dict[int, Path]:
    """Return slide PNGs keyed by physical index without changing the directory."""

    resolved = directory.expanduser().resolve()
    if not resolved.is_dir():
        raise AuditError(f"render directory not found: {resolved}")

    pages: dict[int, Path] = {}
    for path in resolved.iterdir():
        if not path.is_file():
            continue
        match = SLIDE_RE.fullmatch(path.name)
        if not match:
            continue
        index = int(match.group(1))
        if index < 1:
            raise AuditError(f"physical slide index must be positive: {path.name}")
        previous = pages.get(index)
        if previous is not None:
            raise AuditError(
                f"duplicate physical slide index {index}: {previous.name}, {path.name}"
            )
        pages[index] = path
    return pages


def _load_rgba(path: Path) -> Image.Image:
    try:
        with Image.open(path) as image:
            image.load()
            return image.convert("RGBA")
    except (OSError, ValueError, UnidentifiedImageError) as exc:
        raise AuditError(f"cannot read rendered page {path}: {exc}") from exc


def _visible_rgb(image: Image.Image) -> Image.Image:
    """Flatten transparency over white for visible luminance measurements."""

    alpha = image.getchannel("A")
    try:
        if alpha.getextrema() == (255, 255):
            return image.convert("RGB")
    finally:
        alpha.close()

    background = Image.new("RGBA", image.size, (255, 255, 255, 255))
    try:
        composite = Image.alpha_composite(background, image)
        try:
            return composite.convert("RGB")
        finally:
            composite.close()
    finally:
        background.close()


def image_metrics(
    image: Image.Image,
    *,
    white_level: int,
    black_level: int,
) -> dict[str, object]:
    """Calculate full-image luminance and extreme-color coverage statistics."""

    rgb = _visible_rgb(image)
    try:
        luminance = rgb.convert("L")
        try:
            histogram = luminance.histogram()
        finally:
            luminance.close()
    finally:
        rgb.close()

    pixel_count = image.width * image.height
    mean = sum(level * count for level, count in enumerate(histogram)) / pixel_count
    variance = (
        sum(((level - mean) ** 2) * count for level, count in enumerate(histogram))
        / pixel_count
    )
    black_pixels = sum(histogram[: black_level + 1])
    white_pixels = sum(histogram[white_level:])
    return {
        "width": image.width,
        "height": image.height,
        "pixel_count": pixel_count,
        "brightness_mean": round(mean, 6),
        "luminance_variance": round(variance, 6),
        "luminance_stddev": round(math.sqrt(variance), 6),
        "black_pixel_ratio": round(black_pixels / pixel_count, 9),
        "white_pixel_ratio": round(white_pixels / pixel_count, 9),
    }


def pixel_difference(
    source: Image.Image,
    target: Image.Image,
    *,
    pixel_tolerance: int,
    max_changed_ratio: float,
) -> dict[str, object]:
    """Compare every RGBA pixel without resizing either image."""

    source_size = [source.width, source.height]
    target_size = [target.width, target.height]
    if source.size != target.size:
        return {
            "dimensions_match": False,
            "source_size": source_size,
            "target_size": target_size,
            "pixel_count": None,
            "raw_changed_pixel_count": None,
            "raw_changed_pixel_ratio": None,
            "changed_pixel_count": None,
            "changed_pixel_ratio": None,
            "mean_absolute_error": None,
            "maximum_channel_delta": None,
            "different": True,
            "exceeds_tolerance": True,
        }

    difference = ImageChops.difference(source, target)
    channels = difference.split()
    maximum = channels[0].copy()
    try:
        for channel in channels[1:]:
            combined = ImageChops.lighter(maximum, channel)
            maximum.close()
            maximum = combined
        histogram = maximum.histogram()
        pixel_count = source.width * source.height
        raw_changed = pixel_count - histogram[0]
        changed = pixel_count - sum(histogram[: pixel_tolerance + 1])
        raw_ratio = raw_changed / pixel_count
        changed_ratio = changed / pixel_count
        max_delta = next(
            (level for level in range(255, -1, -1) if histogram[level]),
            0,
        )
        stats = ImageStat.Stat(difference)
        mean_absolute_error = sum(stats.mean) / (len(stats.mean) * 255.0)
    finally:
        maximum.close()
        for channel in channels:
            channel.close()
        difference.close()

    return {
        "dimensions_match": True,
        "source_size": source_size,
        "target_size": target_size,
        "pixel_count": pixel_count,
        "raw_changed_pixel_count": raw_changed,
        "raw_changed_pixel_ratio": round(raw_ratio, 9),
        "changed_pixel_count": changed,
        "changed_pixel_ratio": round(changed_ratio, 9),
        "mean_absolute_error": round(mean_absolute_error, 9),
        "maximum_channel_delta": max_delta,
        "different": raw_changed > 0,
        "exceeds_tolerance": changed_ratio > max_changed_ratio,
    }


def detect_solid_risks(
    source_metrics: dict[str, object] | None,
    target_metrics: dict[str, object],
    *,
    solid_pixel_ratio: float,
    low_variance: float,
    brightness_jump: float,
    variance_drop_ratio: float,
) -> list[dict[str, object]]:
    """Detect likely white/black/flat overlays and abrupt source-to-target shifts."""

    risks: list[dict[str, object]] = []
    white_ratio = float(target_metrics["white_pixel_ratio"])
    black_ratio = float(target_metrics["black_pixel_ratio"])
    target_variance = float(target_metrics["luminance_variance"])

    if white_ratio >= solid_pixel_ratio:
        risks.append(
            {
                "code": "near-white-coverage",
                "message": f"target is {white_ratio:.3%} near-white pixels",
                "value": white_ratio,
                "threshold": solid_pixel_ratio,
            }
        )
    if black_ratio >= solid_pixel_ratio:
        risks.append(
            {
                "code": "near-black-coverage",
                "message": f"target is {black_ratio:.3%} near-black pixels",
                "value": black_ratio,
                "threshold": solid_pixel_ratio,
            }
        )
    if target_variance <= low_variance:
        risks.append(
            {
                "code": "low-variance-coverage",
                "message": (
                    f"target luminance variance {target_variance:.3f} is at or below "
                    f"{low_variance:.3f}"
                ),
                "value": target_variance,
                "threshold": low_variance,
            }
        )

    if source_metrics is None:
        return risks

    source_brightness = float(source_metrics["brightness_mean"])
    target_brightness = float(target_metrics["brightness_mean"])
    brightness_delta = abs(target_brightness - source_brightness)
    if brightness_delta >= brightness_jump:
        risks.append(
            {
                "code": "brightness-jump",
                "message": (
                    f"mean brightness changed by {brightness_delta:.3f} "
                    f"({source_brightness:.3f} -> {target_brightness:.3f})"
                ),
                "value": round(brightness_delta, 6),
                "threshold": brightness_jump,
            }
        )

    source_variance = float(source_metrics["luminance_variance"])
    minimum_baseline = max(25.0, low_variance * 4.0)
    if source_variance >= minimum_baseline:
        ratio = target_variance / source_variance
        if ratio <= variance_drop_ratio:
            risks.append(
                {
                    "code": "variance-collapse",
                    "message": (
                        f"luminance variance fell to {ratio:.3%} of source "
                        f"({source_variance:.3f} -> {target_variance:.3f})"
                    ),
                    "value": round(ratio, 9),
                    "threshold": variance_drop_ratio,
                }
            )
    return risks


def _validate_policy(
    *,
    pixel_tolerance: int,
    max_changed_ratio: float,
    white_level: int,
    black_level: int,
    solid_pixel_ratio: float,
    low_variance: float,
    brightness_jump: float,
    variance_drop_ratio: float,
) -> None:
    if not 0 <= pixel_tolerance <= 255:
        raise AuditError("pixel tolerance must be between 0 and 255")
    if not 0.0 <= max_changed_ratio <= 1.0:
        raise AuditError("maximum changed-pixel ratio must be between 0 and 1")
    if not 0 <= black_level < white_level <= 255:
        raise AuditError("require 0 <= black level < white level <= 255")
    if not 0.0 < solid_pixel_ratio <= 1.0:
        raise AuditError("solid-pixel ratio must be greater than 0 and at most 1")
    if low_variance < 0.0:
        raise AuditError("low-variance threshold cannot be negative")
    if brightness_jump <= 0.0:
        raise AuditError("brightness-jump threshold must be positive")
    if not 0.0 <= variance_drop_ratio <= 1.0:
        raise AuditError("variance-drop ratio must be between 0 and 1")


def audit_rendered_pages(
    source_dir: Path,
    target_dir: Path,
    *,
    allow_slides: Iterable[int] | str | None = None,
    allow_solid_slides: Iterable[int] | str | None = None,
    page_map: dict[int, int] | None = None,
    pixel_tolerance: int = DEFAULT_PIXEL_TOLERANCE,
    max_changed_ratio: float = DEFAULT_MAX_CHANGED_RATIO,
    white_level: int = DEFAULT_WHITE_LEVEL,
    black_level: int = DEFAULT_BLACK_LEVEL,
    solid_pixel_ratio: float = DEFAULT_SOLID_PIXEL_RATIO,
    low_variance: float = DEFAULT_LOW_VARIANCE,
    brightness_jump: float = DEFAULT_BRIGHTNESS_JUMP,
    variance_drop_ratio: float = DEFAULT_VARIANCE_DROP_RATIO,
) -> dict[str, object]:
    """Audit two render directories and return a JSON-serializable report."""

    _validate_policy(
        pixel_tolerance=pixel_tolerance,
        max_changed_ratio=max_changed_ratio,
        white_level=white_level,
        black_level=black_level,
        solid_pixel_ratio=solid_pixel_ratio,
        low_variance=low_variance,
        brightness_jump=brightness_jump,
        variance_drop_ratio=variance_drop_ratio,
    )
    allowed = _coerce_slides(allow_slides)
    allowed_solid = _coerce_slides(allow_solid_slides)
    source_path = source_dir.expanduser().resolve()
    target_path = target_dir.expanduser().resolve()
    source_pages = indexed_images(source_path)
    target_pages = indexed_images(target_path)
    explicit_map = dict(page_map or {})
    if explicit_map:
        if any(index < 1 for index in explicit_map):
            raise AuditError("page-map source indices must be positive")
        if any(index < 1 for index in explicit_map.values()):
            raise AuditError("page-map target indices must be positive")
        if len(set(explicit_map.values())) != len(explicit_map):
            raise AuditError("page-map target indices must be unique")
        page_pairs = sorted(explicit_map.items())
    else:
        all_indices = sorted(set(source_pages) | set(target_pages))
        page_pairs = [(index, index) for index in all_indices]
    if not page_pairs:
        raise AuditError(
            f"no slide-*.png images found in {source_path} or {target_path}"
        )

    page_reports: list[dict[str, object]] = []
    differences: list[dict[str, object]] = []
    risks: list[dict[str, object]] = []
    violations: list[dict[str, object]] = []

    for source_index, target_index in page_pairs:
        source_file = source_pages.get(source_index)
        target_file = target_pages.get(target_index)
        source_image = _load_rgba(source_file) if source_file else None
        target_image = _load_rgba(target_file) if target_file else None
        try:
            source_metrics = (
                image_metrics(
                    source_image,
                    white_level=white_level,
                    black_level=black_level,
                )
                if source_image is not None
                else None
            )
            target_metrics = (
                image_metrics(
                    target_image,
                    white_level=white_level,
                    black_level=black_level,
                )
                if target_image is not None
                else None
            )

            page: dict[str, object] = {
                "physical_index": target_index,
                "source_physical_index": source_index,
                "target_physical_index": target_index,
                "source_file": source_file.name if source_file else None,
                "target_file": target_file.name if target_file else None,
                "authorized_change": target_index in allowed,
                "solid_risk_allowed": target_index in allowed_solid,
                "source_metrics": source_metrics,
                "target_metrics": target_metrics,
                "difference": None,
                "risks": [],
                "status": "identical",
            }

            if source_file is None or target_file is None:
                code = "missing-source-page" if source_file is None else "missing-target-page"
                missing_side = "source" if source_file is None else "target"
                item = {
                    "physical_index": target_index,
                    "source_physical_index": source_index,
                    "target_physical_index": target_index,
                    "category": "missing-page",
                    "code": code,
                    "message": (
                        f"mapped slide {source_index}:{target_index} is missing "
                        f"from {missing_side}"
                    ),
                    "authorized": False,
                }
                differences.append(item)
                violations.append(item.copy())
                page["status"] = "missing"
            else:
                comparison = pixel_difference(
                    source_image,
                    target_image,
                    pixel_tolerance=pixel_tolerance,
                    max_changed_ratio=max_changed_ratio,
                )
                page["difference"] = comparison
                if bool(comparison["different"]):
                    if not bool(comparison["dimensions_match"]):
                        code = "dimension-change"
                        message = (
                            f"mapped slide {source_index}:{target_index} dimensions changed from "
                            f"{comparison['source_size']} to {comparison['target_size']}"
                        )
                    else:
                        code = "pixel-change"
                        message = (
                            f"mapped slide {source_index}:{target_index} has "
                            f"{comparison['raw_changed_pixel_count']} differing pixels; "
                            f"{comparison['changed_pixel_count']} "
                            f"({float(comparison['changed_pixel_ratio']):.6%}) exceed "
                            f"the per-channel tolerance"
                        )

                    exceeds = bool(comparison["exceeds_tolerance"])
                    authorized = target_index in allowed
                    if not exceeds:
                        disposition = "tolerated"
                        page["status"] = "changed-tolerated"
                    elif authorized:
                        disposition = "allowed"
                        page["status"] = "changed-authorized"
                    else:
                        disposition = "failed"
                        page["status"] = "changed-failed"
                    difference_item = {
                        "physical_index": target_index,
                        "source_physical_index": source_index,
                        "target_physical_index": target_index,
                        "category": "pixel-change",
                        "code": code,
                        "message": message,
                        "authorized": authorized,
                        "exceeds_tolerance": exceeds,
                        "disposition": disposition,
                        "details": comparison,
                    }
                    differences.append(difference_item)
                    if exceeds and not authorized:
                        violations.append(
                            {
                                **difference_item,
                                "code": "unauthorized-pixel-change",
                            }
                        )

            if target_metrics is not None:
                page_risks = detect_solid_risks(
                    source_metrics,
                    target_metrics,
                    solid_pixel_ratio=solid_pixel_ratio,
                    low_variance=low_variance,
                    brightness_jump=brightness_jump,
                    variance_drop_ratio=variance_drop_ratio,
                )
                for risk in page_risks:
                    risk_item = {
                        "physical_index": target_index,
                        "source_physical_index": source_index,
                        "target_physical_index": target_index,
                        "category": "solid-risk",
                        **risk,
                        "authorized": target_index in allowed_solid,
                    }
                    risks.append(risk_item)
                    page["risks"].append(risk_item)
                    if target_index not in allowed_solid:
                        violations.append(risk_item.copy())
                        if page["status"] == "identical":
                            page["status"] = "risk-failed"

            page_reports.append(page)
        finally:
            if source_image is not None:
                source_image.close()
            if target_image is not None:
                target_image.close()

    materially_changed = [
        item
        for item in differences
        if item.get("category") == "pixel-change" and item.get("exceeds_tolerance")
    ]
    ok = not violations
    return {
        "schema_version": 1,
        "kind": "rendered-page-pixel-audit",
        "source": {
            "path": str(source_path),
            "slide_count": len(source_pages),
            "physical_indices": sorted(source_pages),
        },
        "target": {
            "path": str(target_path),
            "slide_count": len(target_pages),
            "physical_indices": sorted(target_pages),
        },
        "policy": {
            "allow_slides": sorted(allowed),
            "allow_solid_slides": sorted(allowed_solid),
            "page_map": [
                {"source": source_index, "target": target_index}
                for source_index, target_index in page_pairs
            ] if explicit_map else [],
            "pixel_tolerance": pixel_tolerance,
            "max_changed_pixel_ratio": max_changed_ratio,
            "black_level": black_level,
            "white_level": white_level,
            "solid_pixel_ratio": solid_pixel_ratio,
            "low_luminance_variance": low_variance,
            "brightness_jump": brightness_jump,
            "variance_drop_ratio": variance_drop_ratio,
        },
        "slides": page_reports,
        "differences": differences,
        "risks": risks,
        "violations": violations,
        "summary": {
            "audited_physical_page_count": len(page_pairs),
            "audited_page_pair_count": len(page_pairs),
            "difference_count": len(differences),
            "materially_changed_page_count": len(materially_changed),
            "authorized_changed_page_count": sum(
                1 for item in materially_changed if item.get("authorized")
            ),
            "tolerated_difference_count": sum(
                1 for item in differences if item.get("disposition") == "tolerated"
            ),
            "missing_page_count": sum(
                1 for item in differences if item.get("category") == "missing-page"
            ),
            "solid_risk_count": len(risks),
            "allowed_solid_risk_count": sum(
                1 for item in risks if item.get("authorized")
            ),
            "violation_count": len(violations),
        },
        "ok": ok,
        "exit_code": 0 if ok else 1,
    }


def report_to_text(report: dict[str, object]) -> str:
    policy = report["policy"]
    lines = [
        "RENDERED PAGE PIXEL AUDIT",
        f"Source: {report['source']['path']} ({report['source']['slide_count']} pages)",
        f"Target: {report['target']['path']} ({report['target']['slide_count']} pages)",
        (
            "Policy: allowed changes="
            + (",".join(str(index) for index in policy["allow_slides"]) or "none")
            + "; allowed solid risks="
            + (",".join(str(index) for index in policy["allow_solid_slides"]) or "none")
        ),
        (
            f"Tolerance: channel delta <= {policy['pixel_tolerance']}; "
            f"changed pixels <= {float(policy['max_changed_pixel_ratio']):.6%}"
        ),
        "",
        "Pages:",
    ]
    if policy.get("page_map"):
        lines.insert(
            4,
            "Page map: "
            + ", ".join(
                f"{item['source']}->{item['target']}" for item in policy["page_map"]
            ),
        )

    for page in report["slides"]:
        index = page["physical_index"]
        source_index = page.get("source_physical_index", index)
        target_index = page.get("target_physical_index", index)
        status = str(page["status"]).upper().replace("-", " ")
        label = (
            f"Slide {source_index:03d}->{target_index:03d}"
            if source_index != target_index
            else f"Slide {index:03d}"
        )
        lines.append(f"  {label}: {status}")
        difference = page["difference"]
        if difference and bool(difference["different"]):
            if bool(difference["dimensions_match"]):
                lines.append(
                    "    Pixels: "
                    f"{difference['raw_changed_pixel_count']} raw; "
                    f"{difference['changed_pixel_count']} "
                    f"({float(difference['changed_pixel_ratio']):.6%}) above channel tolerance"
                )
            else:
                lines.append(
                    f"    Dimensions: {difference['source_size']} -> {difference['target_size']}"
                )
        for risk in page["risks"]:
            marker = "ALLOWED" if risk["authorized"] else "FAIL"
            lines.append(f"    [{marker}] {risk['code']}: {risk['message']}")

    if not report["slides"]:
        lines.append("  (none)")
    lines.extend(
        [
            "",
            f"Result: {'PASS' if report['ok'] else 'FAIL'}",
            f"Differences: {report['summary']['difference_count']}",
            f"Solid/coverage risks: {report['summary']['solid_risk_count']}",
            f"Violations: {report['summary']['violation_count']}",
        ]
    )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="source render directory")
    parser.add_argument("target", type=Path, help="target render directory")
    parser.add_argument(
        "--allow-slides",
        action="append",
        default=[],
        metavar="RANGE",
        help="authorize visual changes on physical pages, e.g. 2-4,7 (repeatable)",
    )
    parser.add_argument(
        "--allow-solid-slides",
        action="append",
        default=[],
        metavar="RANGE",
        help="allow solid/brightness/variance risks on physical pages (repeatable)",
    )
    parser.add_argument(
        "--page-map",
        action="append",
        default=[],
        metavar="SOURCE:TARGET",
        help=(
            "compare only an explicit physical-page pair, e.g. 3:50; "
            "repeatable, with unique source and target pages"
        ),
    )
    parser.add_argument(
        "--pixel-tolerance",
        "--channel-tolerance",
        type=int,
        default=DEFAULT_PIXEL_TOLERANCE,
        help=f"ignore per-channel deltas at or below this value (default: {DEFAULT_PIXEL_TOLERANCE})",
    )
    parser.add_argument(
        "--max-changed-ratio",
        "--change-tolerance",
        "--tolerance",
        type=float,
        default=DEFAULT_MAX_CHANGED_RATIO,
        help=(
            "maximum fraction of pixels above channel tolerance "
            f"(default: {DEFAULT_MAX_CHANGED_RATIO})"
        ),
    )
    parser.add_argument("--white-level", type=int, default=DEFAULT_WHITE_LEVEL)
    parser.add_argument("--black-level", type=int, default=DEFAULT_BLACK_LEVEL)
    parser.add_argument(
        "--solid-pixel-ratio", type=float, default=DEFAULT_SOLID_PIXEL_RATIO
    )
    parser.add_argument("--low-variance", type=float, default=DEFAULT_LOW_VARIANCE)
    parser.add_argument(
        "--brightness-jump", type=float, default=DEFAULT_BRIGHTNESS_JUMP
    )
    parser.add_argument(
        "--variance-drop-ratio", type=float, default=DEFAULT_VARIANCE_DROP_RATIO
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    return parser


def _error_json(message: str) -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "kind": "rendered-page-pixel-audit",
            "ok": False,
            "exit_code": 2,
            "error": message,
        },
        ensure_ascii=False,
        indent=2,
    ) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        allowed: set[int] = set()
        for spec in args.allow_slides:
            allowed.update(parse_slide_ranges(spec))
        allowed_solid: set[int] = set()
        for spec in args.allow_solid_slides:
            allowed_solid.update(parse_slide_ranges(spec))

        report = audit_rendered_pages(
            args.source,
            args.target,
            allow_slides=allowed,
            allow_solid_slides=allowed_solid,
            page_map=parse_page_maps(args.page_map),
            pixel_tolerance=args.pixel_tolerance,
            max_changed_ratio=args.max_changed_ratio,
            white_level=args.white_level,
            black_level=args.black_level,
            solid_pixel_ratio=args.solid_pixel_ratio,
            low_variance=args.low_variance,
            brightness_jump=args.brightness_jump,
            variance_drop_ratio=args.variance_drop_ratio,
        )
        if args.json:
            sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        else:
            sys.stdout.write(report_to_text(report))
        return int(report["exit_code"])
    except (AuditError, OSError) as exc:
        if args.json:
            sys.stdout.write(_error_json(str(exc)))
        else:
            print(f"audit_rendered_pages: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
