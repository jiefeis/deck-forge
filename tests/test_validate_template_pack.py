#!/usr/bin/env python3
"""Regression test for the bundled bold-template pack."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "validate_template_pack", ROOT / "scripts" / "validate_template_pack.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_template_pack_contract() -> None:
    assert MODULE.validate(ROOT) == []


if __name__ == "__main__":
    test_template_pack_contract()
    print("RESULT: all passed")
