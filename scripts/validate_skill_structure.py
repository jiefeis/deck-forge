#!/usr/bin/env python3
"""Validate deck-forge's progressive-disclosure and UI metadata contracts."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


LINK_RE = re.compile(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)")
YAML_STRING_RE = re.compile(r'^\s*([a-z_]+):\s*"([^"]*)"\s*$', re.MULTILINE)


def frontmatter_keys(text: str) -> set[str]:
    if not text.startswith("---"):
        return set()
    parts = text.split("---", 2)
    if len(parts) < 3:
        return set()
    return {
        match.group(1)
        for match in re.finditer(r"^([A-Za-z0-9_-]+):", parts[1], re.MULTILINE)
    }


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    skill = root / "SKILL.md"
    if not skill.is_file():
        return [f"missing SKILL.md: {skill}"]
    skill_text = skill.read_text(encoding="utf-8")
    keys = frontmatter_keys(skill_text)
    if keys != {"name", "description"}:
        errors.append(f"SKILL.md frontmatter keys must be name/description only: {sorted(keys)}")
    if len(skill_text.splitlines()) >= 500:
        errors.append("SKILL.md must stay under 500 lines")

    readmes = [
        path
        for path in root.rglob("README.md")
        if ".github" not in path.relative_to(root).parts
    ]
    if readmes:
        errors.append("runtime skill contains README files: "
                      + ", ".join(str(path.relative_to(root)) for path in readmes))

    markdown_files = list(root.rglob("*.md"))
    for path in markdown_files:
        text = path.read_text(encoding="utf-8")
        if path.name != "SKILL.md" and len(text.splitlines()) > 100:
            if not re.search(r"(?m)^## (Contents|目录)\s*$", text):
                errors.append(f"long Markdown file lacks Contents/目录: {path.relative_to(root)}")
        for raw_target in LINK_RE.findall(text):
            if re.match(r"^(?:https?://|mailto:|#)", raw_target):
                continue
            target = (path.parent / raw_target.replace("/", str(Path('/')))).resolve()
            if not target.exists():
                errors.append(
                    f"broken relative link: {path.relative_to(root)} -> {raw_target}"
                )

    for reference in sorted((root / "references").glob("*")):
        if reference.is_file() and reference.name not in skill_text:
            errors.append(f"reference is not routed from SKILL.md: {reference.name}")
    for script in sorted((root / "scripts").glob("*")):
        # Leading underscore marks a shared helper module that scripts import
        # but no one invokes; only entry points need a SKILL.md route.
        if script.name.startswith("_"):
            continue
        if script.is_file() and script.name not in skill_text:
            errors.append(f"script is not routed from SKILL.md: {script.name}")

    openai_yaml = root / "agents" / "openai.yaml"
    if not openai_yaml.is_file():
        errors.append("missing agents/openai.yaml")
    else:
        values = dict(YAML_STRING_RE.findall(openai_yaml.read_text(encoding="utf-8")))
        short = values.get("short_description", "")
        prompt = values.get("default_prompt", "")
        if not 25 <= len(short) <= 64:
            errors.append(f"short_description length must be 25-64, found {len(short)}")
        if "$deck-forge" not in prompt:
            errors.append("default_prompt must mention $deck-forge")
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
        print(f"skill structure: {'FAIL' if errors else 'OK'}")
        for error in errors:
            print(f"  - {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
