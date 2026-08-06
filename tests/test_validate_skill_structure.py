#!/usr/bin/env python3
"""Regression test for deck-forge skill structure."""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "validate_skill_structure", ROOT / "scripts" / "validate_skill_structure.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _build_min_skill(root: Path) -> None:
    """Smallest tree that validate() accepts; negative tests mutate it."""
    (root / "references").mkdir()
    (root / "scripts").mkdir()
    (root / "agents").mkdir()
    (root / "SKILL.md").write_text(
        "---\n"
        'name: "deck-forge"\n'
        'description: "test skill"\n'
        "---\n"
        "\n"
        "# Test\n"
        "\n"
        "Read [guide](references/guide.md) and run scripts/tool.py.\n",
        encoding="utf-8",
    )
    (root / "references" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (root / "scripts" / "tool.py").write_text("print('ok')\n", encoding="utf-8")
    (root / "agents" / "openai.yaml").write_text(
        'short_description: "Build a polished HTML slide deck"\n'
        'default_prompt: "Use $deck-forge to build a deck"\n',
        encoding="utf-8",
    )


def _errors_after(mutate: Callable[[Path], None]) -> list[str]:
    with tempfile.TemporaryDirectory(prefix="deckforge-skill-") as temp:
        root = Path(temp)
        _build_min_skill(root)
        clean = MODULE.validate(root)
        assert clean == [], f"minimal tree must validate clean, got: {clean}"
        mutate(root)
        return MODULE.validate(root)


def _rewrite(path: Path, old: str, new: str) -> None:
    path.write_text(
        path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8"
    )


def test_skill_structure_contract() -> None:
    errs = MODULE.validate(ROOT)
    assert errs == [], errs


def test_broken_relative_link_detected() -> None:
    def mutate(root: Path) -> None:
        skill = root / "SKILL.md"
        skill.write_text(
            skill.read_text(encoding="utf-8")
            + "\nSee [bad](references/missing.md).\n",
            encoding="utf-8",
        )

    errs = _errors_after(mutate)
    assert any("broken relative link" in e for e in errs), errs


def test_unrouted_script_detected() -> None:
    errs = _errors_after(
        lambda root: (root / "scripts" / "orphan.py").write_text(
            "pass\n", encoding="utf-8"
        )
    )
    assert any(
        "script is not routed from SKILL.md: orphan.py" in e for e in errs
    ), errs


def test_illegal_frontmatter_key_detected() -> None:
    errs = _errors_after(
        lambda root: _rewrite(
            root / "SKILL.md",
            'description: "test skill"\n',
            'description: "test skill"\nlicense: "MIT"\n',
        )
    )
    assert any(
        "frontmatter keys must be name/description only" in e for e in errs
    ), errs


def test_oversized_skill_md_detected() -> None:
    def mutate(root: Path) -> None:
        skill = root / "SKILL.md"
        skill.write_text(
            skill.read_text(encoding="utf-8") + "filler\n" * 500,
            encoding="utf-8",
        )

    errs = _errors_after(mutate)
    assert any("SKILL.md must stay under 500 lines" in e for e in errs), errs


if __name__ == "__main__":
    test_skill_structure_contract()
    test_broken_relative_link_detected()
    test_unrouted_script_detected()
    test_illegal_frontmatter_key_detected()
    test_oversized_skill_md_detected()
    print("RESULT: all passed")
