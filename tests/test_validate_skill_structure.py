#!/usr/bin/env python3
"""Exercise the installed layout and its progressive-disclosure checks."""

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "validate_skill_structure.py"
SPEC = importlib.util.spec_from_file_location("validate_skill_structure", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SkillStructureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="deckforge-skill-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "deck-forge"
        self.root.mkdir()
        self.write("SKILL.md", "---\nname: deck-forge\ndescription: Test skill\n---\n\n"
                   "[Build](tracks/html-build.md)\n[Edit](tracks/pptx-native.md)\n"
                   "[Translate](tracks/translate-and-qa.md)\n")
        self.write("tracks/html-build.md", "Use the [style](../assets/html/base.css). "
                   "Run `python scripts/forge.py verify-html`.\n")
        self.write("tracks/pptx-native.md", "# Native slides\n")
        self.write("tracks/translate-and-qa.md", "# Translation\n")
        self.write("assets/html/base.css", "body { color: black; }\n")
        self.write("scripts/forge.py", "# fixture\n")
        self.write("agents/openai.yaml", 'interface:\n'
                   '  short_description: "Build a polished HTML slide deck"\n'
                   '  default_prompt: "Use $deck-forge to build a deck"\n')

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def append(self, name, content):
        with (self.root / name).open("a", encoding="utf-8") as file:
            file.write(content)

    def errors(self):
        return "\n".join(MODULE.validate(self.root)).replace("\\", "/")

    def test_checkout(self):
        self.assertEqual(MODULE.validate(ROOT), [])

    def test_validator_runs_from_installed_tree_with_no_checkout_material(self):
        installed_script = self.write("scripts/validate_skill_structure.py", SCRIPT.read_text(encoding="utf-8"))
        result = subprocess.run([sys.executable, "-B", str(installed_script), "--json"],
                                cwd=self.root.parent, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_guide_and_unlinked_existing_guide(self):
        (self.root / "tracks" / "pptx-native.md").unlink()
        self.assertIn("missing track: tracks/pptx-native.md", self.errors())
        path = self.root / "SKILL.md"
        self.write("SKILL.md", path.read_text(encoding="utf-8").replace(
            "[Build](tracks/html-build.md)", "Build with html-build.md"))
        self.assertIn("track is not linked from SKILL.md: tracks/html-build.md", self.errors())

    def test_removed_or_misplaced_asset_and_missing_command(self):
        css = self.root / "assets" / "html" / "base.css"
        css.rename(css.with_name("renamed.css"))
        (self.root / "scripts" / "forge.py").unlink()
        result = self.errors()
        self.assertIn("broken relative link: tracks/html-build.md -> ../assets/html/base.css", result)
        self.assertIn("missing runtime command: tracks/html-build.md -> scripts/forge.py", result)

    def test_checkout_links_can_exist_but_must_not_be_runtime_dependencies(self):
        self.write("examples/demo/index.html", "<html></html>")
        self.write(".github/README.md", "[Demo](../examples/demo/index.html)\n")
        self.assertEqual(self.errors(), "")
        self.append("tracks/html-build.md", "[Demo](../examples/demo/index.html)\n")
        self.assertIn("runtime link to checkout-only content", self.errors())

    def test_local_links_cannot_escape_the_package(self):
        outside = self.root.parent / "outside.md"
        outside.write_text("outside", encoding="utf-8")
        self.append("tracks/pptx-native.md", "[Details](../../outside.md)\n")
        self.assertIn("local link outside skill tree", self.errors())

    def test_three_tracks_and_no_superseded_rule_trees(self):
        self.write("tracks/fourth.md", "# Non-routing attachment\n")
        self.write("AUTHORING.md", "# Old authoring guide\n")
        self.write("references/old-guide.md", "# Previous route\n")
        result = self.errors()
        self.assertIn("unexpected track: tracks/fourth.md", result)
        self.assertIn("unexpected root guide: AUTHORING.md", result)
        self.assertIn("legacy references/ guides", result)

    def test_entry_at_line_budget_and_beyond(self):
        path = self.root / "SKILL.md"
        needed = 80 - len(path.read_text(encoding="utf-8").splitlines())
        self.append("SKILL.md", "filler\n" * needed)
        self.assertEqual(self.errors(), "")
        self.append("SKILL.md", "over budget\n")
        self.assertIn("SKILL.md must stay within 80 lines", self.errors())

    def test_illegal_frontmatter_key(self):
        path = self.root / "SKILL.md"
        self.write("SKILL.md", path.read_text(encoding="utf-8").replace(
            "name: deck-forge\n", "name: deck-forge\nlicense: MIT\n"))
        self.assertIn("frontmatter keys must be name/description only", self.errors())


if __name__ == "__main__":
    unittest.main(verbosity=2)
