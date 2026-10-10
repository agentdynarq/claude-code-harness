"""Repository hygiene that the project's own rules depend on."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

from helpers import KIT, REPO

TEXT_SUFFIXES = {".md", ".py", ".toml", ".json", ".yml", ".yaml", ".txt", ".cfg", ""}
TEMPLATES = KIT / ".claude" / "harness" / "templates"
MARKER = "[REPLACE:"
EM_DASH, EN_DASH = chr(0x2014), chr(0x2013)


def text_files() -> list[Path]:
    """Files git would commit (tracked or not ignored). Falls back to a walk without git."""
    try:
        listed = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                                cwd=REPO, capture_output=True, text=True, timeout=60, check=True).stdout
        paths = [REPO / line for line in listed.splitlines() if line]
    except (OSError, subprocess.SubprocessError):
        paths = [p for p in REPO.rglob("*") if ".git" not in p.parts]
    return [p for p in paths if p.is_file() and p.suffix in TEXT_SUFFIXES and "__pycache__" not in p.parts]


class RepositoryText(unittest.TestCase):
    def test_no_em_or_en_dashes(self):
        offenders = []
        for path in text_files():
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if EM_DASH in line or EN_DASH in line:
                    offenders.append(f"{path.relative_to(REPO)}:{number}")
        self.assertEqual(offenders, [])

    def test_templates_are_marked_and_nothing_else_is_unfinished(self):
        templates = sorted(TEMPLATES.glob("*.md"))
        self.assertEqual([p.name for p in templates], ["CLAUDE.template.md", "handoff.md", "task-brief.md"])
        for path in templates:
            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("<!--\nTEMPLATE from claude-code-harness"), path.name)
            self.assertIn(MARKER, text)
        for base in (REPO / "examples", KIT):
            for path in base.rglob("*"):
                if path.is_file() and TEMPLATES not in path.parents and "__pycache__" not in path.parts:
                    self.assertNotIn(MARKER, path.read_text(encoding="utf-8"), str(path.relative_to(REPO)))

    def test_no_file_named_claude_md_inside_the_kit(self):
        # Claude Code loads CLAUDE.md files from subdirectories on demand, so a template
        # with that exact name would be read as live instructions.
        self.assertEqual([p for p in KIT.rglob("*") if p.name == "CLAUDE.md"], [])

    def test_instruction_files_stay_short(self):
        for path in (TEMPLATES / "CLAUDE.template.md", REPO / "examples/invoice-totals/CLAUDE.md"):
            self.assertLess(len(path.read_text(encoding="utf-8").splitlines()), 200, path.name)

    def test_skill_frontmatter(self):
        text = (KIT / ".claude/skills/verified-change/SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        front = text.split("---\n")[1]
        fields = dict(line.split(": ", 1) for line in front.strip().splitlines())
        self.assertEqual(fields["name"], "verified-change")
        self.assertNotEqual(fields["name"], "verify", "a project skill named verify replaces the bundled /verify")
        self.assertTrue(fields["description"])
        self.assertIn("Bash(python .claude/harness/verify.py *)", fields["allowed-tools"])


if __name__ == "__main__":
    unittest.main()
