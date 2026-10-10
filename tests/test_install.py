"""Category A: preview, install and removal in throwaway target directories."""

from __future__ import annotations

import contextlib
import io
import json
import os
import unittest
from pathlib import Path

from helpers import KIT, REPO, TempDirTest, install, run_script, snapshot

KIT_FILES = install.kit_files(KIT)
SKILL = ".claude/skills/verified-change/SKILL.md"


def run(*args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = install.main(list(args))
    return code, out.getvalue(), err.getvalue()


def link_dir(link: Path, target: Path) -> None:
    """A directory link that needs no administrator rights: a junction on Windows."""
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


class Install(TempDirTest):
    def target(self, name: str = "target", files: dict[str, str] | None = None) -> Path:
        root = self.tmp / name
        root.mkdir()
        for rel, content in (files or {}).items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return root

    def test_kit_is_small_and_contains_the_expected_parts(self):
        self.assertIn(".claude/harness/verify.py", KIT_FILES)
        self.assertIn(".claude/harness/stop_hook.py", KIT_FILES)
        self.assertIn(SKILL, KIT_FILES)
        self.assertFalse(any(f.endswith("settings.json") or f.endswith("settings.local.json") for f in KIT_FILES),
                         "the kit must never ship a settings file")
        self.assertNotIn(".claude/harness/checks.toml", KIT_FILES)

    def test_dry_run_writes_nothing(self):
        root = self.target(files={"README.md": "existing\n"})
        before = snapshot(root)
        code, out, _ = run("install", str(root), "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(snapshot(root), before)
        self.assertEqual(out.count("  create "), len(KIT_FILES))
        self.assertIn("Dry run: nothing was written.", out)

    def test_install_copies_the_kit_and_tracks_what_it_added(self):
        root = self.target()
        code, out, _ = run("install", str(root))
        self.assertEqual(code, 0)
        for rel in KIT_FILES:
            self.assertEqual((root / rel).read_bytes(), (KIT / rel).read_bytes(), rel)
        manifest = json.loads((root / install.MANIFEST_RELPATH).read_text(encoding="utf-8"))
        self.assertEqual(sorted(manifest["files"]), KIT_FILES)
        self.assertIn(".claude", manifest["created_dirs"])
        self.assertIn("no project command was run", out)

    def test_repeated_install_is_idempotent(self):
        root = self.target()
        run("install", str(root))
        before = snapshot(root)
        code, out, _ = run("install", str(root))
        self.assertEqual(code, 0)
        self.assertIn("Nothing to do", out)
        self.assertEqual(snapshot(root), before)

    def test_conflicting_file_refuses_the_whole_install(self):
        root = self.target(files={SKILL: "---\nname: my-own-skill\n---\n"})
        before = snapshot(root)
        code, out, _ = run("install", str(root))
        self.assertEqual(code, 1)
        self.assertIn(f"conflict      {SKILL}", out)
        self.assertIn("Nothing was written", out)
        self.assertEqual(snapshot(root), before)

    def test_file_where_a_directory_is_needed_is_a_conflict(self):
        root = self.target(files={".claude/skills": "not a directory"})
        before = snapshot(root)
        self.assertEqual(run("install", str(root))[0], 1)
        self.assertEqual(snapshot(root), before)

    def test_existing_claude_md_settings_and_hooks_are_untouched(self):
        settings = {"permissions": {"deny": ["Read(./.env)"]},
                    "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}}
        root = self.target(files={"CLAUDE.md": "# Mine\n", ".claude/settings.json": json.dumps(settings),
                                  ".claude/settings.local.json": "{}", ".claude/CLAUDE.md": "# Also mine\n"})
        originals = {rel: (root / rel).read_bytes() for rel in
                     ("CLAUDE.md", ".claude/settings.json", ".claude/settings.local.json", ".claude/CLAUDE.md")}
        code, out, _ = run("install", str(root))
        self.assertEqual(code, 0)
        for rel, data in originals.items():
            self.assertEqual((root / rel).read_bytes(), data, rel)
        self.assertIn("CLAUDE.md exists and was not changed", out)
        self.assertIn("already define 1 Stop hook entry", out)
        manifest = json.loads((root / install.MANIFEST_RELPATH).read_text(encoding="utf-8"))
        self.assertNotIn(".claude", manifest["created_dirs"], "a pre-existing .claude/ is not ours to remove")

    def test_target_path_with_spaces(self):
        root = self.target(name="my project (copy) with spaces")
        self.assertEqual(run("install", str(root))[0], 0)
        self.assertTrue((root / ".claude/harness/verify.py").is_file())
        self.assertEqual(run("remove", str(root))[0], 0)
        self.assertEqual(snapshot(root), {})

    def test_target_is_required_and_must_be_a_directory(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            install.main(["install"])
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(run("install", str(self.tmp / "missing"))[0], 2)
        file_target = self.tmp / "file.txt"
        file_target.write_text("x")
        self.assertEqual(run("install", str(file_target))[0], 2)

    def test_command_line_entry_point_runs_as_a_script(self):
        root = self.target(name="script target")
        proc = run_script(REPO / "install.py", "install", str(root), "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(snapshot(root), {})


class StayInsideTarget(TempDirTest):
    def test_relative_paths_that_escape_are_rejected(self):
        target = self.tmp / "t"
        target.mkdir()
        for rel in ("../outside.txt", "a/../../outside.txt", "/etc/passwd", "C:/Windows/x", "C:x",
                    "a\\..\\..\\x", "", "a//b"):
            with self.subTest(rel=rel), self.assertRaises(install.EscapeError):
                install.safe_destination(target.resolve(), rel)

    def test_directory_link_inside_target_cannot_redirect_writes(self):
        target, outside = self.tmp / "target", self.tmp / "outside"
        target.mkdir()
        outside.mkdir()
        try:
            link_dir(target / ".claude", outside)
        except (OSError, ImportError) as exc:
            self.skipTest(f"cannot create a directory link here: {exc}")
        code, out, err = run("install", str(target))
        self.assertEqual(code, 1)
        self.assertIn("outside the target", out + err)
        self.assertEqual(list(outside.iterdir()), [], "nothing may be written through the link")

    def test_tampered_manifest_cannot_delete_outside_the_target(self):
        target = self.tmp / "target"
        target.mkdir()
        self.assertEqual(run("install", str(target))[0], 0)
        victim = self.tmp / "victim.txt"
        victim.write_text("keep me", encoding="utf-8")
        manifest_path = target / install.MANIFEST_RELPATH
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"]["../../../victim.txt"] = install.sha256_file(victim)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        code, out, _ = run("remove", str(target))
        self.assertEqual(code, 1)
        self.assertIn("refused", out)
        self.assertEqual(victim.read_text(encoding="utf-8"), "keep me")


class Remove(TempDirTest):
    def installed(self) -> Path:
        root = self.tmp / "target"
        root.mkdir()
        (root / "app.py").write_bytes(b"print('mine')\n")
        self.assertEqual(run("install", str(root))[0], 0)
        return root

    def test_dry_run_deletes_nothing(self):
        root = self.installed()
        before = snapshot(root)
        code, out, _ = run("remove", str(root), "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("Dry run: nothing was deleted.", out)
        self.assertEqual(snapshot(root), before)

    def test_clean_removal_restores_the_original_tree(self):
        root = self.installed()
        code, _, _ = run("remove", str(root))
        self.assertEqual(code, 0)
        self.assertEqual(snapshot(root), {"app.py": b"print('mine')\n"})

    def test_removal_keeps_user_modified_and_user_created_files(self):
        root = self.installed()
        skill = root / SKILL
        skill.write_text(skill.read_text(encoding="utf-8") + "\nOur team's extra rule.\n", encoding="utf-8")
        (root / ".claude/harness/checks.toml").write_text('required = ["t"]\n', encoding="utf-8")
        code, out, _ = run("remove", str(root))
        self.assertEqual(code, 0)
        self.assertIn("Our team's extra rule.", skill.read_text(encoding="utf-8"))
        self.assertTrue((root / ".claude/harness/checks.toml").is_file())
        self.assertFalse((root / ".claude/harness/verify.py").exists())
        self.assertIn(f"kept          {SKILL}  (modified since installation)", out)
        manifest = json.loads((root / install.MANIFEST_RELPATH).read_text(encoding="utf-8"))
        self.assertEqual(list(manifest["files"]), [SKILL])
        again = run("remove", str(root))
        self.assertEqual(again[0], 0)
        self.assertTrue(skill.is_file())

    def test_remove_without_manifest_does_nothing(self):
        root = self.tmp / "plain"
        root.mkdir()
        code, out, _ = run("remove", str(root))
        self.assertEqual(code, 0)
        self.assertIn("no install manifest", out)

    def test_unreadable_manifest_is_refused(self):
        root = self.installed()
        (root / install.MANIFEST_RELPATH).write_text("{broken", encoding="utf-8")
        before = snapshot(root)
        for action in ("install", "remove"):
            with self.subTest(action=action):
                self.assertEqual(run(action, str(root))[0], 1)
                self.assertEqual(snapshot(root), before)


if __name__ == "__main__":
    unittest.main()
