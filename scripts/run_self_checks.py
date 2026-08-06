#!/usr/bin/env python3
"""Run deck-forge validation and every standalone regression test."""

from __future__ import annotations

import ast
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

REQUIRED_MODULES = (
    ("playwright", "playwright"),
    ("img2pdf", "img2pdf"),
    ("lxml", "lxml"),
    ("pptx", "python-pptx"),
    ("PIL", "Pillow"),
)

# unittest summary lines: "OK (skipped=3)", "FAILED (failures=1, skipped=2)".
SKIPPED_RE = re.compile(r"\bskipped=(\d+)")


def run(command: list[str], env: dict[str, str]) -> tuple[int, int]:
    """Run a command, echo its output, and return (returncode, skipped)."""
    print("\n$ " + " ".join(command), flush=True)
    result = subprocess.run(
        command, env=env, check=False, capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    output = result.stdout + result.stderr
    print(output, end="", flush=True)
    return result.returncode, sum(int(n) for n in SKIPPED_RE.findall(output))


def validate_python_syntax(root: Path) -> list[str]:
    """Parse every maintained Python file without importing or writing bytecode."""

    errors: list[str] = []
    paths = sorted((root / "scripts").glob("*.py"))
    paths.extend(sorted((root / "tests").glob("*.py")))
    for path in paths:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeError) as exc:
            errors.append(f"{path.relative_to(root)}: {exc}")
    return errors


def main() -> int:
    # A wrong interpreter (deps live per-Python) must fail as ONE clear
    # environment error, not as a cascade of unrelated test failures.
    print(f"python: {sys.executable}")
    missing = [
        pip_name
        for module, pip_name in REQUIRED_MODULES
        if importlib.util.find_spec(module) is None
    ]
    if missing:
        print(
            "RESULT: ENV-FAIL - this interpreter is missing "
            + ", ".join(missing)
            + ". Install them for THIS python (pip install "
            + " ".join(missing)
            + ") or rerun with the interpreter check_env.py reports as OK."
        )
        return 1

    root = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    python = sys.executable
    failures = 0

    syntax_errors = validate_python_syntax(root)
    print(f"Python syntax: {'FAIL' if syntax_errors else 'OK'}")
    for error in syntax_errors:
        print(f"  - {error}")
    failures += bool(syntax_errors)

    validator = (
        root.parent / ".system" / "skill-creator" / "scripts" /
        "quick_validate.py"
    )
    skipped_commands: list[str] = []
    if validator.is_file():
        failures += run([python, "-B", str(validator), str(root)], env)[0] != 0
    else:
        print(f"SKIP quick_validate.py not found at {validator}")
        skipped_commands.append(f"quick_validate.py (not found at {validator})")

    failures += run(
        [python, "-B", str(root / "scripts" / "validate_template_pack.py")], env
    )[0] != 0
    failures += run(
        [python, "-B", str(root / "scripts" / "validate_skill_structure.py")], env
    )[0] != 0
    skipped_total = 0
    skipped_files: list[tuple[str, int]] = []
    for test in sorted((root / "tests").glob("test_*.py")):
        code, skipped = run([python, "-B", str(test)], env)
        failures += code != 0
        if skipped:
            skipped_total += skipped
            skipped_files.append((test.relative_to(root).as_posix(), skipped))

    print(
        f"\nRESULT: {'FAIL' if failures else 'OK'} "
        f"({failures} failing command(s), {skipped_total} skipped test(s), "
        f"{len(skipped_commands)} skipped command(s))"
    )
    for name, count in skipped_files:
        print(f"  skipped test(s): {name} ({count})")
    for name in skipped_commands:
        print(f"  skipped command: {name}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
