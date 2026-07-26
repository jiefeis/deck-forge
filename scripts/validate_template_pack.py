#!/usr/bin/env python3
"""Validate deck-forge's bold-template index and required runtime contracts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REQUIRED_DESIGN_MARKERS = (
    "## Contents",
    "## deck-forge Fixed-Stage Policy",
    "## CJK & International Content",
)


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
        for key in ("preview_md", "design_md"):
            raw = entry.get(key)
            if not raw:
                errors.append(f"{slug}: missing {key}")
                continue
            path = skill_root / raw
            if not path.is_file():
                errors.append(f"{slug}: missing path {raw}")
        design_raw = entry.get("design_md")
        if design_raw and (skill_root / design_raw).is_file():
            text = (skill_root / design_raw).read_text(encoding="utf-8")
            for marker in REQUIRED_DESIGN_MARKERS:
                if marker not in text:
                    errors.append(f"{slug}: missing marker {marker!r}")

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
