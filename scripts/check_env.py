#!/usr/bin/env python3
"""
check_env.py - verify deck-forge's runtime dependencies in THIS Python.

Run it with the SAME `python` you'll use for export_pdf.py / edit_texts.py,
because deps live per-interpreter and multi-Python setups are a common footgun:

    python check_env.py

Reports playwright / img2pdf / lxml + the Chromium browser binary, with the
exact install command for anything missing. Exit code 0 = all good. Labels are
ASCII, but paths and error details may not be, so stdout/stderr are
reconfigured with errors="replace" to stay safe on a non-UTF-8 Windows console.
"""
from __future__ import annotations

import importlib
import importlib.metadata as _md
import os
import sys
from pathlib import Path


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
    if sys.version_info < (3, 9):
        sys.exit("check_env: deck-forge scripts require Python 3.9+ "
                 f"(this is {sys.version.split()[0]}: {sys.executable}).")
    # sys.executable and error details may contain non-ASCII paths; never let
    # a cp1252/cp936 console pipe kill the check with UnicodeEncodeError.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--browser-executable", metavar="PATH",
                    help="use an existing Chromium/Chrome executable for the "
                         "launch check")
    args = ap.parse_args()
    raw_browser = (args.browser_executable
                   or os.environ.get("DECK_FORGE_BROWSER_EXECUTABLE"))
    browser_executable = (Path(raw_browser).expanduser().resolve()
                          if raw_browser else None)
    if browser_executable is not None and not browser_executable.is_file():
        sys.exit("check_env: --browser-executable is not a file "
                 "(or DECK_FORGE_BROWSER_EXECUTABLE): "
                 f"{browser_executable}")

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

    try:
        import PIL  # noqa: F401
        print("  OK    Pillow (optional, image/contact-sheet tools)")
    except Exception:
        print("  ----  Pillow (optional, image/contact-sheet tools) "
              "-> pip install Pillow")

    # Chromium browser binary: surest check is a quick headless launch.
    if ok:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                if browser_executable is not None:
                    b = p.chromium.launch(
                        executable_path=str(browser_executable))
                else:
                    # Same fallback order as export_pdf.launch_chromium:
                    # managed Chromium, then system Chrome/Edge channels.
                    try:
                        b = p.chromium.launch()
                    except Exception:
                        for channel in ("chrome", "msedge"):
                            try:
                                b = p.chromium.launch(channel=channel)
                                break
                            except Exception:
                                continue
                        else:
                            raise
                b.close()
            print("  OK    chromium browser")
        except Exception as e:
            ok = False
            print("  MISS  chromium browser "
                  "-> python -m playwright install chromium, or pass "
                  "--browser-executable / set DECK_FORGE_BROWSER_EXECUTABLE "
                  "to an existing Chrome/Edge/Chromium binary")
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
