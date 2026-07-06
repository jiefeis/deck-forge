#!/usr/bin/env python3
"""
check_env.py - verify deck-forge's runtime dependencies in THIS Python.

Run it with the SAME `python` you'll use for export_pdf.py / edit_texts.py,
because deps live per-interpreter and multi-Python setups are a common footgun:

    python check_env.py

Reports playwright / img2pdf / lxml + the Chromium browser binary, with the
exact install command for anything missing. Exit code 0 = all good. ASCII-only
output so it is safe on a non-UTF-8 Windows console.
"""
from __future__ import annotations

import importlib
import importlib.metadata as _md
import sys


def _check_module(mod: str, pip_name: str) -> bool:
    try:
        importlib.import_module(mod)
    except Exception:
        print(f"  MISS  {mod}   -> pip install {pip_name}")
        return False
    try:
        ver = _md.version(pip_name)                       # accurate dist version
    except Exception:
        ver = getattr(importlib.import_module(mod), "__version__", "?")
    print(f"  OK    {mod} {ver}")
    return True


def main() -> None:
    print(f"deck-forge env check  (python: {sys.executable})")
    ok = True
    for mod, pip_name in (("playwright", "playwright"),
                          ("img2pdf", "img2pdf"),
                          ("lxml", "lxml")):
        ok &= _check_module(mod, pip_name)

    # python-pptx is optional (only for .pptx INPUT) - report but don't fail.
    try:
        import pptx  # noqa: F401
        print(f"  OK    python-pptx (optional)")
    except Exception:
        print("  ----  python-pptx (optional, only for .pptx input) "
              "-> pip install python-pptx")

    # Chromium browser binary: surest check is a quick headless launch.
    if ok:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                b = p.chromium.launch()
                b.close()
            print("  OK    chromium browser")
        except Exception as e:
            ok = False
            print("  MISS  chromium browser "
                  "-> python -m playwright install chromium")
            print(f"        ({str(e)[:110]})")

    print()
    if ok:
        print("deck-forge: environment OK - ready to export.")
    else:
        print("deck-forge: missing deps above. Install them with THIS python, "
              "then re-run check_env.py.")
        sys.exit(1)


if __name__ == "__main__":
    main()
