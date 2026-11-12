#!/usr/bin/env python3
"""Build the installable deck-forge ZIP from an immutable Git commit."""

import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "SKILL.md", "agents/openai.yaml", "LICENSE", "THIRD_PARTY_NOTICES.md",
    "tracks/html-build.md", "tracks/pptx-native.md", "tracks/translate-and-qa.md",
    "scripts/forge.py", "scripts/native_charts.py", "scripts/render_pptx.py",
}
SOURCE_ONLY = {".git", ".github", "examples", "evals", "tests", "tools", "__pycache__"}


def build(ref: str, output: Path) -> tuple[str, int, str]:
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    revision = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "--verify", "--end-of-options", ref + "^{commit}"],
        text=True,
    ).strip()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        archive = Path(temp) / "deck-forge.zip"
        subprocess.run(["git", "-C", str(ROOT), "archive", "--format=zip", "--prefix=deck-forge/",
                        "-o", str(archive.resolve()), revision], check=True)
        with zipfile.ZipFile(archive) as package:
            names = package.namelist()
            if any(not n.startswith("deck-forge/") for n in names):
                raise ValueError("unexpected archive root")
            files = [name[len("deck-forge/"):] for name in names if not name.endswith("/")]
            missing = REQUIRED - set(files)
            excluded = [name for name in files if SOURCE_ONLY.intersection(Path(name).parts)]
            if missing or excluded or package.testzip():
                raise ValueError(f"archive failed validation: missing={sorted(missing)}, excluded={excluded}")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        with output.open("xb") as dest, archive.open("rb") as source:
            try:
                shutil.copyfileobj(source, dest)
            except OSError:
                dest.close()
                output.unlink()
                raise
    return revision, len(files), digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="HEAD", help="commit, branch or release tag")
    parser.add_argument("--output", type=Path, required=True, help="new .zip file")
    args = parser.parse_args()
    try:
        revision, count, digest = build(args.ref, args.output.resolve())
    except (OSError, ValueError, subprocess.CalledProcessError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"package_skill: {exc}\n")
    print(f"{revision}  {count} files\nSHA256 {digest}  {args.output}")


if __name__ == "__main__":
    main()
