#!/usr/bin/env python3
"""Run deck-forge validation and every standalone regression test."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path


def run(command: list[str], env: dict[str, str]) -> int:
    print("\n$ " + " ".join(command), flush=True)
    return subprocess.run(command, env=env, check=False).returncode


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
    if validator.is_file():
        failures += run([python, "-B", str(validator), str(root)], env) != 0
    else:
        print(f"SKIP quick_validate.py not found at {validator}")

    failures += run(
        [python, "-B", str(root / "scripts" / "validate_template_pack.py")], env
    ) != 0
    failures += run(
        [python, "-B", str(root / "scripts" / "validate_skill_structure.py")], env
    ) != 0
    for test in sorted((root / "tests").glob("test_*.py")):
        failures += run([python, "-B", str(test)], env) != 0

    print(f"\nRESULT: {'FAIL' if failures else 'OK'} ({failures} failing command(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
