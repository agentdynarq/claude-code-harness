"""Category B: Stop hook contract tests with fixture payloads.

These feed hand-written payloads to stop_hook.py. They check the documented contract
(stdin JSON in; exit code and stdout JSON out) but are not a Claude Code session.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from helpers import TempDirTest, checks_toml, py_code, run_script, stop_hook, verify

SESSION = "fixture-session-1"


def payload(active: bool | None = False, **extra) -> str:
    data = {"session_id": SESSION, "transcript_path": "fixture", "cwd": "fixture",
            "permission_mode": "default", "hook_event_name": "Stop",
            "last_assistant_message": "fixture"}
    if active is not None:
        data["stop_hook_active"] = active
    data.update(extra)
    return json.dumps(data, ensure_ascii=False)  # raw UTF-8, not \u escapes


class HookProcess(TempDirTest):
    """Runs the real script in a temporary project, as Claude Code would."""

    def hook(self, root: Path, stdin: str, env: dict | None = None):
        return run_script(root / ".claude/harness/stop_hook.py", stdin=stdin, env=env)

    def failing_project(self, **settings) -> Path:
        return self.make_project(
            config=checks_toml({"tests": {"command": py_code("print('expected 0.29, got 0.28'); raise SystemExit(1)")}},
                               ["tests"], include=["src/*"], settings=settings or None),
            files={"src/app.py": "v = 1\n"})

    def test_malformed_json_is_a_non_blocking_error(self):
        root = self.failing_project()
        for bad in ("{not json", "", "   ", "[1, 2]", '"Stop"'):
            with self.subTest(stdin=bad):
                proc = self.hook(root, bad)
                self.assertEqual(proc.returncode, 1)
                self.assertEqual(proc.stdout.strip(), "")
                self.assertIn("claude-code-harness stop hook:", proc.stderr)
        self.assertFalse((root / verify.EVIDENCE_RELPATH).exists(), "no checks may run on malformed input")

    def test_wrong_event_or_fields_are_rejected(self):
        root = self.failing_project()
        cases = [
            json.dumps({"session_id": SESSION, "hook_event_name": "PreToolUse"}),
            json.dumps({"hook_event_name": "Stop"}),
            json.dumps({"session_id": SESSION, "hook_event_name": "Stop", "stop_hook_active": "yes"}),
        ]
        for case in cases:
            with self.subTest(stdin=case):
                proc = self.hook(root, case)
                self.assertEqual((proc.returncode, proc.stdout.strip()), (1, ""))

    def test_missing_configuration_is_reported_and_does_not_block(self):
        root = self.make_project(files={"src/app.py": ""})
        proc = self.hook(root, payload())
        self.assertEqual(proc.returncode, 0)
        output = json.loads(proc.stdout)
        self.assertNotIn("decision", output)
        self.assertIn("checks.toml does not exist", output["systemMessage"])

    def test_invalid_configuration_is_reported_and_does_not_block(self):
        root = self.make_project(config='required = ["t"]\n[checks.t]\ncommand = "make test"\n')
        output = json.loads(self.hook(root, payload()).stdout)
        self.assertNotIn("decision", output)
        self.assertIn("checks.toml is invalid", output["systemMessage"])

    def test_failing_check_blocks_with_the_failure_in_the_reason(self):
        root = self.failing_project()
        proc = self.hook(root, payload())
        self.assertEqual(proc.returncode, 0)
        output = json.loads(proc.stdout)
        self.assertEqual(output["decision"], "block")
        self.assertIn("tests: FAILED, exit code 1", output["reason"])
        self.assertIn("expected 0.29, got 0.28", output["reason"])
        self.assertIn("automatic retry 1 of 2", output["reason"])

    def test_retries_are_bounded_while_claude_keeps_changing_code(self):
        root = self.failing_project()
        decisions = []
        for attempt in range(4):
            if attempt:
                (root / "src/app.py").write_text(f"v = {attempt + 1}\n", encoding="utf-8")  # Claude edits
            out = json.loads(self.hook(root, payload(active=attempt > 0)).stdout)
            decisions.append(out.get("decision", "allow"))
        self.assertEqual(decisions, ["block", "block", "allow", "allow"])
        last = json.loads(self.hook(root, payload(active=True)).stdout)
        self.assertIn("still not passing", last["systemMessage"])

    def test_unchanged_failure_is_not_blocked_twice_even_on_a_new_turn(self):
        root = self.failing_project()
        self.assertEqual(json.loads(self.hook(root, payload()).stdout)["decision"], "block")
        for active in (True, False):
            output = json.loads(self.hook(root, payload(active=active)).stdout)
            self.assertNotIn("decision", output)
            self.assertIn("unchanged", output["systemMessage"])

    def test_a_new_turn_with_new_changes_gets_a_fresh_budget(self):
        root = self.failing_project(stop_hook_max_blocks=1)
        self.assertEqual(json.loads(self.hook(root, payload()).stdout)["decision"], "block")
        (root / "src/app.py").write_text("v = 2\n", encoding="utf-8")
        self.assertNotIn("decision", json.loads(self.hook(root, payload(active=True)).stdout))
        (root / "src/app.py").write_text("v = 3\n", encoding="utf-8")
        self.assertEqual(json.loads(self.hook(root, payload(active=False)).stdout)["decision"], "block")

    def test_passing_checks_allow_stop_and_unchanged_source_reuses_evidence(self):
        counter = self.tmp / "runs.txt"
        code = f"open({str(counter)!r}, 'a').write('run\\n')"
        root = self.make_project(config=checks_toml({"tests": {"command": py_code(code)}}, ["tests"],
                                                    include=["src/*"]), files={"src/app.py": ""})
        first = self.hook(root, payload())
        self.assertIn("passed", json.loads(first.stdout)["systemMessage"])
        second = self.hook(root, payload())
        self.assertEqual((second.returncode, second.stdout.strip()), (0, ""))
        self.assertEqual(counter.read_text().count("run"), 1, "unchanged source must reuse the evidence")
        (root / "src/app.py").write_text("changed\n", encoding="utf-8")
        self.hook(root, payload())
        self.assertEqual(counter.read_text().count("run"), 2, "changed source must run the checks again")

    def test_report_only_mode_never_blocks(self):
        root = self.failing_project(stop_hook_max_blocks=0)
        output = json.loads(self.hook(root, payload()).stdout)
        self.assertNotIn("decision", output)
        self.assertIn("Blocking is off", output["systemMessage"])

    def test_environment_switch_disables_the_hook(self):
        root = self.failing_project()
        proc = self.hook(root, payload(), env={"HARNESS_STOP_HOOK": "off"})
        self.assertEqual((proc.returncode, proc.stdout), (0, ""))
        self.assertFalse((root / verify.EVIDENCE_RELPATH).exists(), "disabled hook must not run checks")

    def test_internal_error_exits_1_never_2(self):
        root = self.failing_project()
        (root / verify.EVIDENCE_RELPATH).write_text("a file where a directory belongs", encoding="utf-8")
        proc = self.hook(root, payload())
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout.strip(), "")
        self.assertIn("internal error", proc.stderr)

    def test_unicode_payload_is_read_as_utf8(self):
        root = self.make_project(config=checks_toml({"t": {"command": py_code("pass")}}, ["t"]))
        text = payload(last_assistant_message="Gesamtbetrag 5,54 € ✓ ā")
        self.assertIn("ā", text, "the payload must carry raw non-ASCII characters")
        proc = run_script(root / ".claude/harness/stop_hook.py", stdin=text, env={"PYTHONIOENCODING": "cp1252"})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("passed", json.loads(proc.stdout)["systemMessage"])


class DecideLogic(unittest.TestCase):
    """The pure decision function, without processes or files."""

    def result(self, overall: str, fingerprint: str = "a" * 64, reused: bool = False):
        report = {"checks": [{"name": "tests", "required": True, "outcome": overall, "exit_code": 1}]}
        return stop_hook.Verification(overall, fingerprint, reused, report)

    def test_missing_stop_hook_active_does_not_reset_the_count(self):
        state = stop_hook.HookState(SESSION, 2, "b" * 64)
        data = json.loads(payload(active=None))
        output, new = stop_hook.decide(data, state, self.result("failed"), max_blocks=2)
        self.assertNotIn("decision", output)
        self.assertEqual(new.consecutive_blocks, 2)

    def test_explicit_false_resets_the_count(self):
        state = stop_hook.HookState(SESSION, 2, "b" * 64)
        output, new = stop_hook.decide(json.loads(payload(False)), state, self.result("failed"), max_blocks=2)
        self.assertEqual(output["decision"], "block")
        self.assertEqual(new.consecutive_blocks, 1)

    def test_a_different_session_starts_clean(self):
        state = stop_hook.HookState("other-session", 2, "a" * 64)
        output, new = stop_hook.decide(json.loads(payload(True)), state, self.result("failed"), max_blocks=2)
        self.assertEqual(output["decision"], "block")
        self.assertEqual(new.session_id, SESSION)

    def test_pass_clears_state_and_is_silent_when_evidence_was_reused(self):
        state = stop_hook.HookState(SESSION, 1, "a" * 64)
        output, new = stop_hook.decide(json.loads(payload(True)), state, self.result("passed", reused=True), 2)
        self.assertIsNone(output)
        self.assertEqual((new.consecutive_blocks, new.notified_fingerprint), (0, None))

    def test_reason_stays_within_the_documented_10000_character_cap(self):
        report = {"checks": [{"name": f"c{i}", "required": True, "outcome": "failed", "exit_code": 1,
                              "output_tail": "x" * 5000} for i in range(10)]}
        reason = stop_hook.build_reason(stop_hook.Verification("failed", "a" * 64, False, report), 1, 2)
        self.assertLessEqual(len(reason), 10000)

    def test_owner_decisions_are_flagged_in_the_reason(self):
        report = {"checks": [{"name": "lint", "required": True, "outcome": "not_configured", "exit_code": None}]}
        reason = stop_hook.build_reason(stop_hook.Verification("failed", "a" * 64, False, report), 1, 2)
        self.assertIn("project owner's decision", reason)


class SettingsSnippet(unittest.TestCase):
    def test_example_settings_match_the_documented_hook_shape(self):
        snippet = json.loads((Path(stop_hook.HERE) / "hook-settings.example.json").read_text(encoding="utf-8"))
        self.assertEqual(list(snippet), ["hooks"])
        groups = snippet["hooks"]["Stop"]
        handler = groups[0]["hooks"][0]
        self.assertEqual(handler["type"], "command")
        self.assertEqual(handler["args"], ["${CLAUDE_PROJECT_DIR}/.claude/harness/stop_hook.py"])
        self.assertGreater(handler["timeout"], verify.DEFAULT_TOTAL_TIMEOUT,
                           "the hook timeout must exceed the runner's default total budget")


if __name__ == "__main__":
    unittest.main()
