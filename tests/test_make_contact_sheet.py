#!/usr/bin/env python3
"""Regression test for scripts/make_contact_sheet.py (standalone or pytest)."""

from __future__ import annotations

import importlib.util
import shutil
import tempfile
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "make_contact_sheet", ROOT / "scripts" / "make_contact_sheet.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_aligned_contact_sheet() -> None:
    temp = Path(tempfile.mkdtemp(prefix="deckforge-contact-test-"))
    try:
        source = temp / "source"
        target = temp / "target"
        source.mkdir()
        target.mkdir()
        Image.new("RGB", (1920, 1080), "white").save(source / "slide-001.png")
        Image.new("RGB", (1920, 1080), "red").save(source / "slide-003.png")
        Image.new("RGB", (1920, 1080), "blue").save(target / "slide-001.png")
        Image.new("RGB", (1920, 1080), "green").save(target / "slide-002.png")
        Image.new("RGB", (1920, 1080), "yellow").save(target / "slide-003.png")

        output = temp / "contact.png"
        MODULE.build([("源文件", source), ("target", target)], output,
                     columns=2, thumb_width=160)
        assert output.is_file()
        with Image.open(output) as sheet:
            assert sheet.width > 320
            assert sheet.height > 180
        # Physical indices are unioned (1,2,3), so missing source slide 2 does
        # not shift source slide 3 under the wrong target page.
        assert sorted(MODULE.indexed_images(source)) == [1, 3]
        assert sorted(MODULE.indexed_images(target)) == [1, 2, 3]
    finally:
        shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    test_aligned_contact_sheet()
    print("RESULT: all passed")
