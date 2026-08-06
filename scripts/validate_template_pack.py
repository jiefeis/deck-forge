#!/usr/bin/env python3
"""Validate deck-forge's bold-template index and required runtime contracts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


REQUIRED_DESIGN_MARKERS = (
    "## Contents",
    "## deck-forge Fixed-Stage Policy",
    "## CJK & International Content",
)

# fixed-stage policy: 1920x1080 px only — no fluid viewport units or clamp()
# Checked against the YAML token frontmatter only. The prose below it quotes
# vw/vh/clamp() on purpose: the Fixed-Stage Policy section explains the rule,
# and the source-history sections describe the original viewport-fluid template.
VIEWPORT_UNIT_RE = re.compile(r"\d(?:\.\d+)?\s*v[wh]\b")

# Every fontSize token must be one resolved stage value. Catches the shapes that
# slipped through a clamp()-only check: bare numbers (48), ranges ("35-42px"),
# and leftover relative units ("0.85rem").
FONT_SIZE_RE = re.compile(r'^\s*fontSize:\s*"?([^"\n]+?)"?\s*$', re.M)
VALID_FONT_SIZE_RE = re.compile(r"^(?:\d+(?:\.\d+)?px|inherit|\{[^}]+\})$")


def token_frontmatter(text: str) -> str:
    """Return the leading '---' YAML block that carries the design tokens."""
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    return text[:end] if end > 0 else ""


def validate(skill_root: Path) -> list[str]:
    errors: list[str] = []
    pack = skill_root / "bold-template-pack"
    index_path = pack / "selection-index.json"
    templates_dir = pack / "templates"
    if not index_path.is_file():
        return [f"missing index: {index_path}"]
    if not templates_dir.is_dir():
        return [f"missing templates directory: {templates_dir}"]

    index = json.loads(index_path.read_text(encoding="utf-8"))
    entries = index.get("templates", [])
    dirs = {path.name for path in templates_dir.iterdir() if path.is_dir()}
    slugs = {entry.get("slug") for entry in entries}
    if index.get("template_count") != len(entries):
        errors.append(
            f"template_count={index.get('template_count')} but entries={len(entries)}"
        )
    if slugs != dirs:
        errors.append(f"index/directories differ: index-only={sorted(slugs - dirs)}, "
                      f"dir-only={sorted(dirs - slugs)}")

    for entry in entries:
        slug = entry.get("slug", "<missing-slug>")
        # paths are derived from slug by convention: templates/<slug>/{preview,design}.md
        template_dir = templates_dir / slug
        for name in ("preview.md", "design.md"):
            if not (template_dir / name).is_file():
                errors.append(f"{slug}: missing templates/{slug}/{name}")
        design_path = template_dir / "design.md"
        if design_path.is_file():
            text = design_path.read_text(encoding="utf-8")
            for marker in REQUIRED_DESIGN_MARKERS:
                if marker not in text:
                    errors.append(f"{slug}: missing marker {marker!r}")
            tokens = token_frontmatter(text)
            if "clamp(" in tokens:
                errors.append(f"{slug}: design.md tokens use clamp() (fixed-stage px only)")
            if VIEWPORT_UNIT_RE.search(tokens):
                errors.append(f"{slug}: design.md tokens use viewport units vw/vh (fixed-stage px only)")
            for value in FONT_SIZE_RE.findall(tokens):
                if not VALID_FONT_SIZE_RE.match(value.strip()):
                    errors.append(
                        f"{slug}: design.md fontSize {value.strip()!r} is not a single "
                        f"stage px value (expected e.g. \"28px\")"
                    )

    readmes = list(pack.rglob("README.md"))
    if readmes:
        errors.append("runtime pack contains maintenance README files: "
                      + ", ".join(str(p.relative_to(skill_root)) for p in readmes))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "skill_root", nargs="?", type=Path,
        default=Path(__file__).resolve().parent.parent,
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    errors = validate(args.skill_root.resolve())
    if args.json:
        print(json.dumps({"status": "FAIL" if errors else "OK", "errors": errors},
                         ensure_ascii=False, indent=2))
    else:
        print(f"template pack: {'FAIL' if errors else 'OK'}")
        for error in errors:
            print(f"  - {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
