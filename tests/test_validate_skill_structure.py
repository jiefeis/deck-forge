#!/usr/bin/env python3
"""Regression test for deck-forge skill structure."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "validate_skill_structure", ROOT / "scripts" / "validate_skill_structure.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_skill_structure_contract() -> None:
    assert MODULE.validate(ROOT) == []


if __name__ == "__main__":
    test_skill_structure_contract()
    print("RESULT: all passed")
