"""The live-session record must not leak local paths, the user name or account context."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from helpers import REPO

sys.path.insert(0, str(REPO / "scripts"))
import live_session_check as live  # noqa: E402


class Sanitise(unittest.TestCase):
    def test_every_spelling_of_local_paths_is_replaced(self):
        home = Path.home()
        project = home / "AppData" / "Local" / "Temp" / "cch-live-abc" / "invoice-totals"
        native = str(project)
        spellings = [
            native,
            native.replace("\\", "\\\\"),
            native.replace("\\", "/"),
            native.upper(),
            json.dumps({"cwd": native}),
            f'cd "{native.replace(chr(92), "/")}" && python .claude/harness/verify.py',
        ]
        if native[1:2] == ":":
            spellings.append("/" + native[0].lower() + native[2:].replace("\\", "/"))
        for text in spellings:
            with self.subTest(text=text):
                cleaned = live.sanitise(text, project)
                self.assertIn("<project>", cleaned, "each spelling of the project path gets the label")
                self.assertNotIn(home.name.lower(), cleaned.lower())
        self.assertNotIn(home.name.lower(), live.sanitise(str(home / "other" / "file.txt"), project).lower())

    def test_a_stray_user_name_is_replaced(self):
        name = Path.home().name
        if len(name) < 3:
            self.skipTest("user name too short to replace safely")
        self.assertEqual(live.sanitise(f"owner={name}", Path("/nowhere")), "owner=<user>")

    def test_project_label_wins_over_home(self):
        project = Path.home() / "work" / "proj"
        self.assertEqual(live.sanitise(str(project / "a.py"), project), str(Path("<project>") / "a.py"))


class PublicStream(unittest.TestCase):
    def test_init_and_rate_limit_events_are_dropped(self):
        raw = "\n".join(json.dumps(e) for e in [
            {"type": "system", "subtype": "init", "model": "m", "mcp_servers": [{"name": "private-server"}]},
            {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed"}},
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash",
                                                          "input": {"command": "python .claude/harness/verify.py"}}]}},
            {"type": "user", "message": {"content": [{"type": "text", "text": "Stop hook feedback: checks failed"}]}},
            {"type": "result", "subtype": "success", "num_turns": 2, "total_cost_usd": 0.1},
        ])
        public = live.public_stream(raw)
        self.assertNotIn("private-server", public)
        self.assertNotIn("rate_limit", public)
        self.assertEqual(len(public.splitlines()), 3)
        calls, feedback, result, model = live.summarise_stream(raw)
        self.assertEqual(calls, ["Bash: python .claude/harness/verify.py"])
        self.assertEqual(feedback, ["Stop hook feedback: checks failed"])
        self.assertEqual((result["num_turns"], model), (2, "m"))


if __name__ == "__main__":
    unittest.main()
