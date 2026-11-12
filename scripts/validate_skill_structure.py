#!/usr/bin/env python3
"""Validate the deck-forge entry point, tracks, resource links and UI metadata."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit


TRACKS = {"html-build.md", "pptx-native.md", "translate-and-qa.md"}
ROOT_DOCS = {"SKILL.md", "THIRD_PARTY_NOTICES.md"}
RUNTIME_DIRS = {"assets", "tracks", "agents", "scripts"}
LINK_RE = re.compile(r"\[[^\]\n]+\]\((<[^>\n]+>|[^\s)]+)\)")
SCRIPT_RE = re.compile(r"\bscripts/([a-zA-Z_][\w.-]*\.(?:py|ps1))\b")
YAML_STRING_RE = re.compile(r'^\s*([a-z_]+):\s*"([^"]*)"\s*$', re.MULTILINE)


def _longpath(path: Path) -> Path:
    """Support deeply nested installed skills on Windows."""
    value = str(path.resolve())
    if os.name == "nt" and not value.startswith("\\\\?\\"):
        if value.startswith("\\\\"):
            return Path("\\\\?\\UNC\\" + value[2:])
        return Path("\\\\?\\" + value)
    return Path(value)


def frontmatter_keys(text: str) -> set[str]:
    if not text.startswith("---"):
        return set()
    parts = text.split("---", 2)
    if len(parts) < 3:
        return set()
    return set(re.findall(r"^([A-Za-z0-9_-]+):", parts[1], re.MULTILINE))


def in_runtime(relative: Path) -> bool:
    """Runtime docs must resolve even after checkout-only material is excluded."""
    if relative.as_posix() == "scripts/run_self_checks.py":
        return False
    return relative.parts[0] in ROOT_DOCS | RUNTIME_DIRS | {"LICENSE"}


def validate(root: Path) -> list[str]:
    root = _longpath(root)
    errors: list[str] = []
    skill = root / "SKILL.md"
    if not skill.is_file():
        return ["missing SKILL.md"]
    skill_text = skill.read_text(encoding="utf-8")
    keys = frontmatter_keys(skill_text)
    if keys != {"name", "description"}:
        errors.append(f"SKILL.md frontmatter keys must be name/description only: {sorted(keys)}")
    if len(skill_text.splitlines()) > 80:
        errors.append("SKILL.md must stay within 80 lines")

    tracks = {path.name for path in (root / "tracks").glob("*.md")}
    for name in sorted(TRACKS - tracks):
        errors.append(f"missing track: tracks/{name}")
    for name in sorted(tracks - TRACKS):
        errors.append(f"unexpected track: tracks/{name}")
    for path in sorted(root.glob("*.md")):
        if path.name not in ROOT_DOCS:
            errors.append(f"unexpected root guide: {path.name}")
    if any((root / "references").rglob("*.md")):
        errors.append("legacy references/ guides remain alongside the tracks")

    routed = set()
    documents = list(root.glob("*.md"))
    for folder in ("tracks", "assets", ".github", "evals", "examples"):
        documents.extend((root / folder).rglob("*.md"))
    for doc in sorted(documents):
        relative = doc.relative_to(root)
        runtime = in_runtime(relative)
        content = doc.read_text(encoding="utf-8")
        if not content.strip():
            errors.append(f"empty guide: {relative}")
        if doc != skill and len(content.splitlines()) > 100:
            if not re.search(r"(?m)^## (Contents|目录)\s*$", content):
                errors.append(f"long Markdown file lacks Contents/目录: {relative}")

        for link in LINK_RE.findall(content):
            url = urlsplit(link.strip("<>"))
            if url.scheme or url.netloc or not url.path:
                continue
            destination = (doc.parent / unquote(url.path)).resolve()
            if not destination.is_relative_to(root) or destination == root:
                errors.append(f"local link outside skill tree: {relative} -> {link}")
                continue
            target = destination.relative_to(root)
            if runtime and not in_runtime(target):
                errors.append(f"runtime link to checkout-only content: {relative} -> {link}")
            elif not destination.exists():
                errors.append(f"broken relative link: {relative} -> {link}")
            if doc == skill and target.parent == Path("tracks"):
                routed.add(target.name)

        if runtime:
            for name in sorted(set(SCRIPT_RE.findall(content))):
                command = Path("scripts") / name
                if not in_runtime(command) or not (root / command).is_file():
                    errors.append(f"missing runtime command: {relative} -> {command}")

    for name in sorted(TRACKS - routed):
        errors.append(f"track is not linked from SKILL.md: tracks/{name}")

    openai_yaml = root / "agents" / "openai.yaml"
    if not openai_yaml.is_file():
        errors.append("missing agents/openai.yaml")
    else:
        values = dict(YAML_STRING_RE.findall(openai_yaml.read_text(encoding="utf-8")))
        short = values.get("short_description", "")
        if not 25 <= len(short) <= 64:
            errors.append(f"short_description length must be 25-64, found {len(short)}")
        if "$deck-forge" not in values.get("default_prompt", ""):
            errors.append("default_prompt must mention $deck-forge")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_root", nargs="?", type=Path,
                        default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    errors = validate(args.skill_root)
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
