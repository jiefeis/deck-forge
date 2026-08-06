#!/usr/bin/env python3
"""Regression tests for the bundled bold-template pack and its validator."""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "validate_template_pack", ROOT / "scripts" / "validate_template_pack.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

MARKERS = (
    "## Contents\n"
    "## deck-forge Fixed-Stage Policy\n"
    "## CJK & International Content\n"
)


def design_md(tokens: str = "  fontSize: 48px\n", prose: str = "") -> str:
    """Build a design.md: YAML token frontmatter, then the prose sections."""
    return f"---\ntypography:\n  body:\n{tokens}---\n\n{MARKERS}{prose}"


DESIGN_OK = design_md()


def make_pack(
    root: Path,
    slugs: tuple[str, ...] = ("alpha",),
    template_count: int | None = None,
    design_text: str = DESIGN_OK,
    skip_dirs: tuple[str, ...] = (),
) -> None:
    """Build a minimal template pack under root."""
    templates_dir = root / "bold-template-pack" / "templates"
    templates_dir.mkdir(parents=True)
    index = {
        "template_count": len(slugs) if template_count is None else template_count,
        "templates": [{"slug": slug} for slug in slugs],
    }
    (root / "bold-template-pack" / "selection-index.json").write_text(
        json.dumps(index), encoding="utf-8"
    )
    for slug in slugs:
        if slug in skip_dirs:
            continue
        template_dir = templates_dir / slug
        template_dir.mkdir()
        (template_dir / "preview.md").write_text("preview", encoding="utf-8")
        (template_dir / "design.md").write_text(design_text, encoding="utf-8")


def assert_error_containing(errors: list[str], needle: str) -> None:
    assert any(needle in error for error in errors), (
        f"expected an error containing {needle!r}, got: {errors}"
    )


def test_template_pack_contract() -> None:
    errors = MODULE.validate(ROOT)
    assert errors == [], f"template pack validation failed: {errors}"


def test_minimal_pack_passes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_pack(root)
        assert MODULE.validate(root) == []


def test_template_count_mismatch() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_pack(root, template_count=2)
        assert_error_containing(MODULE.validate(root), "template_count=2 but entries=1")


def test_missing_fixed_stage_marker() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_pack(root, design_text="---\ntypography:\n---\n\n## Contents\n")
        assert_error_containing(
            MODULE.validate(root), "missing marker '## deck-forge Fixed-Stage Policy'"
        )


def test_design_md_tokens_with_clamp() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_pack(root, design_text=design_md(tokens='  fontSize: "clamp(28px, 3vw, 44px)"\n'))
        assert_error_containing(MODULE.validate(root), "tokens use clamp()")


def test_design_md_tokens_with_viewport_units() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_pack(root, design_text=design_md(tokens="  fontSize: 4.5vw\n  height: 10vh\n"))
        assert_error_containing(MODULE.validate(root), "viewport units vw/vh")


def test_design_md_font_size_must_be_single_px() -> None:
    """Bare numbers, ranges and relative units all slip past a clamp()-only check."""
    for bad in ('48', '"35-42px"', '"0.85rem"', '"2em"'):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_pack(root, design_text=design_md(tokens=f"  fontSize: {bad}\n"))
            assert_error_containing(MODULE.validate(root), "is not a single")


def test_design_md_font_size_accepts_px_and_references() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_pack(root, design_text=design_md(
            tokens='  fontSize: "28px"\n  a: 1\n  b: 2\n'
        ))
        assert MODULE.validate(root) == []


def test_prose_may_quote_viewport_units() -> None:
    """The policy section and source-history prose quote vw/vh/clamp() on purpose."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_pack(root, design_text=design_md(prose=(
            "This policy applies even if the source template used `100vw`, `vh`, "
            "or `clamp()`. Treat those as design proportions.\n"
            "The system targets `100vw x 100vh` and uses `clamp()` throughout.\n"
        )))
        assert MODULE.validate(root) == []


def test_missing_template_directory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_pack(root, slugs=("alpha", "beta"), skip_dirs=("beta",))
        assert_error_containing(MODULE.validate(root), "index/directories differ")


NEGATIVE_TESTS = (
    test_minimal_pack_passes,
    test_template_count_mismatch,
    test_missing_fixed_stage_marker,
    test_design_md_tokens_with_clamp,
    test_design_md_tokens_with_viewport_units,
    test_design_md_font_size_must_be_single_px,
    test_design_md_font_size_accepts_px_and_references,
    test_prose_may_quote_viewport_units,
    test_missing_template_directory,
)


if __name__ == "__main__":
    for test in NEGATIVE_TESTS:
        test()
        print(f"PASS {test.__name__}")
    # run last: the real pack may transiently fail while templates are re-baked
    test_template_pack_contract()
    print("PASS test_template_pack_contract")
    print("RESULT: all passed")
