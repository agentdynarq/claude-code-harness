"""Category A: the verification runner, run against real subprocesses."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from helpers import PY, TempDirTest, checks_toml, py_code, verify


def run_cli(*args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = verify.main(list(args))
    return code, out.getvalue(), err.getvalue()


class RunOutcomes(TempDirTest):
    def project(self, checks, required, **kwargs) -> Path:
        return self.make_project(config=checks_toml(checks, required, **kwargs),
                                 files={"src/app.py": "VALUE = 1\n"})

    def report_for(self, root: Path) -> dict:
        return json.loads((root / verify.EVIDENCE_RELPATH / verify.REPORT_NAME).read_text(encoding="utf-8"))

    def test_required_check_succeeds(self):
        root = self.project({"tests": {"command": py_code("print('all good')")}}, ["tests"])
        code, out, _ = run_cli("--root", str(root))
        self.assertEqual(code, 0)
        self.assertIn("RESULT   PASSED", out)
        report = self.report_for(root)
        self.assertEqual(report["overall"], "passed")
        check = report["checks"][0]
        self.assertEqual((check["name"], check["outcome"], check["exit_code"]), ("tests", "passed", 0))
        self.assertEqual(check["command"], py_code("print('all good')"))
        self.assertEqual(check["cwd"], ".")
        self.assertGreaterEqual(check["duration_seconds"], 0)
        self.assertIn("all good", (root / check["log"]).read_text(encoding="utf-8"))
        self.assertEqual(len(report["source_state"]["fingerprint"]), 64)
        self.assertTrue((root / verify.EVIDENCE_RELPATH / ".gitignore").is_file())

    def test_required_check_fails_and_exit_code_is_preserved(self):
        root = self.project({"tests": {"command": py_code("import sys; print('boom'); sys.exit(7)")}}, ["tests"])
        code, out, _ = run_cli("--root", str(root))
        self.assertEqual(code, 1)
        check = self.report_for(root)["checks"][0]
        self.assertEqual((check["outcome"], check["exit_code"]), ("failed", 7))
        self.assertIn("exit 7", out)
        self.assertIn("| boom", out)

    def test_required_check_absent_fails_overall(self):
        root = self.project({"tests": {"command": py_code("pass")}}, ["tests", "lint"])
        code, out, _ = run_cli("--root", str(root))
        self.assertEqual(code, 1)
        lint = {c["name"]: c for c in self.report_for(root)["checks"]}["lint"]
        self.assertEqual(lint["outcome"], "not_configured")
        self.assertIsNone(lint["exit_code"])
        self.assertIn("NOT CONFIGURED", out)

    def test_required_check_declared_without_command_is_not_configured(self):
        root = self.make_project(config='required = ["tests"]\n[checks.tests]\n')
        code, _, _ = run_cli("--root", str(root))
        self.assertEqual(code, 1)
        self.assertEqual(self.report_for(root)["checks"][0]["outcome"], "not_configured")

    def test_optional_failure_does_not_decide_overall(self):
        root = self.project({"tests": {"command": py_code("pass")},
                             "lint": {"command": py_code("import sys; sys.exit(3)")}}, ["tests"])
        code, _, _ = run_cli("--root", str(root))
        self.assertEqual(code, 0)
        lint = {c["name"]: c for c in self.report_for(root)["checks"]}["lint"]
        self.assertEqual((lint["required"], lint["outcome"], lint["exit_code"]), (False, "failed", 3))

    def test_disabled_check_is_skipped_and_a_skipped_required_check_fails(self):
        root = self.project({"tests": {"command": py_code("pass"), "enabled": False, "reason": "waiting on CI"}},
                            ["tests"])
        code, out, _ = run_cli("--root", str(root))
        self.assertEqual(code, 1)
        check = self.report_for(root)["checks"][0]
        self.assertEqual((check["outcome"], check["detail"]), ("skipped", "waiting on CI"))
        self.assertIn("not run: waiting on CI", out)

    def test_missing_executable_is_a_failure_with_a_reason(self):
        root = self.project({"tests": {"command": ["cch-no-such-program-4821"]}}, ["tests"])
        code, _, _ = run_cli("--root", str(root))
        self.assertEqual(code, 1)
        check = self.report_for(root)["checks"][0]
        self.assertEqual(check["outcome"], "failed")
        self.assertIsNone(check["exit_code"])
        self.assertIn("executable not found", check["detail"])

    def test_python_token_runs_the_current_interpreter(self):
        root = self.project({"tests": {"command": ["{python}", "-c", "import sys; print(sys.executable)"]}}, ["tests"])
        report = verify.run_checks(root, verify.load_config(root / verify.CONFIG_RELPATH))
        self.assertEqual(report["checks"][0]["command"][0], sys.executable)
        self.assertEqual(report["overall"], "passed")

    def test_working_directory_and_paths_with_spaces(self):
        root = self.make_project(name="folder with spaces", config=checks_toml(
            {"tests": {"command": py_code("import os; open('cwd.txt','w').write(os.getcwd())"),
                       "cwd": "sub dir"}}, ["tests"]),
            files={"sub dir/keep.txt": "x"})
        code, _, _ = run_cli("--root", str(root))
        self.assertEqual(code, 0)
        written = (root / "sub dir" / "cwd.txt").read_text()
        self.assertEqual(Path(written).resolve(), (root / "sub dir").resolve())

    def test_working_directory_outside_root_is_refused(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        root = self.project({"tests": {"command": py_code("pass"), "cwd": "../outside"}}, ["tests"])
        code, _, _ = run_cli("--root", str(root))
        self.assertEqual(code, 1)
        self.assertIn("outside the project root", self.report_for(root)["checks"][0]["detail"])

    @unittest.skipUnless(os.name == "nt", "Windows batch files")
    def test_windows_cmd_file_exit_code_is_preserved(self):
        root = self.project({"tests": {"command": ["tools\\check.cmd"]}}, ["tests"])
        (root / "tools").mkdir()
        (root / "tools" / "check.cmd").write_text("@echo off\r\necho from batch\r\nexit /b 4\r\n")
        code, _, _ = run_cli("--root", str(root))
        self.assertEqual(code, 1)
        check = self.report_for(root)["checks"][0]
        self.assertEqual((check["outcome"], check["exit_code"]), ("failed", 4))
        self.assertIn("from batch", check["output_tail"])


class Timeouts(TempDirTest):
    def test_timeout_is_reported_and_the_process_tree_is_killed(self):
        marker = self.tmp / "grandchild-survived.txt"
        grandchild = f"import time, pathlib; time.sleep(4); pathlib.Path({str(marker)!r}).write_text('alive')"
        parent = (f"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', {grandchild!r}]); "
                  f"print('started', flush=True); time.sleep(60)")
        root = self.make_project(config=checks_toml({"slow": {"command": py_code(parent), "timeout_seconds": 1.5}},
                                                    ["slow"]))
        started = time.monotonic()
        report = verify.run_checks(root, verify.load_config(root / verify.CONFIG_RELPATH))
        elapsed = time.monotonic() - started
        check = report["checks"][0]
        self.assertEqual(check["outcome"], "timeout")
        self.assertIsNone(check["exit_code"])
        self.assertIn("stopped after 1.5s", check["detail"])
        self.assertIn("started", check["output_tail"])
        self.assertLess(elapsed, 30)
        time.sleep(6)  # the grandchild would have written its marker after 4 seconds
        self.assertFalse(marker.exists(), "grandchild process outlived the timeout")

    def test_total_budget_skips_checks_that_cannot_start(self):
        config = checks_toml({"first": {"command": py_code("import time; time.sleep(5)"), "timeout_seconds": 30},
                              "second": {"command": py_code("pass")}},
                             ["first", "second"], settings={"total_timeout_seconds": 1})
        root = self.make_project(config=config)
        report = verify.run_checks(root, verify.load_config(root / verify.CONFIG_RELPATH))
        outcomes = {c["name"]: c for c in report["checks"]}
        self.assertEqual(outcomes["first"]["outcome"], "timeout")
        self.assertIn("limited by settings.total_timeout_seconds", outcomes["first"]["detail"])
        self.assertEqual(outcomes["second"]["outcome"], "skipped")
        self.assertEqual(report["overall"], "failed")


class Evidence(TempDirTest):
    def setUp(self):
        super().setUp()
        self.root = self.make_project(
            config=checks_toml({"tests": {"command": py_code("pass")}}, ["tests"], include=["src/*"]),
            files={"src/app.py": "VALUE = 1\n", "README.md": "notes\n"})

    def status(self) -> tuple[int, dict]:
        code, out, _ = run_cli("status", "--root", str(self.root), "--json")
        return code, json.loads(out)

    def test_no_evidence_yet(self):
        code, status = self.status()
        self.assertEqual((code, status["state"]), (4, "missing"))

    def test_evidence_becomes_stale_after_a_relevant_change(self):
        self.assertEqual(run_cli("--root", str(self.root))[0], 0)
        self.assertEqual(self.status()[0], 0)
        (self.root / "src/app.py").write_text("VALUE = 2\n", encoding="utf-8")
        code, status = self.status()
        self.assertEqual((code, status["state"]), (3, "stale"))
        self.assertEqual(status["changes"]["modified"], ["src/app.py"])
        (self.root / "src/app.py").write_text("VALUE = 1\n", encoding="utf-8")
        self.assertEqual(self.status()[0], 0, "content identical to the recorded state is fresh again")

    def test_added_and_removed_files_make_evidence_stale(self):
        run_cli("--root", str(self.root))
        (self.root / "src/new.py").write_text("", encoding="utf-8")
        self.assertEqual(self.status()[1]["changes"]["added"], ["src/new.py"])
        (self.root / "src/new.py").unlink()
        (self.root / "src/app.py").unlink()
        self.assertEqual(self.status()[1]["changes"]["removed"], ["src/app.py"])

    def test_change_outside_the_selected_source_keeps_evidence_fresh(self):
        run_cli("--root", str(self.root))
        (self.root / "README.md").write_text("edited\n", encoding="utf-8")
        self.assertEqual(self.status()[0], 0)

    def test_changing_the_checks_makes_evidence_stale(self):
        run_cli("--root", str(self.root))
        config = self.root / verify.CONFIG_RELPATH
        config.write_text(config.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")
        code, status = self.status()
        self.assertEqual(code, 3)
        self.assertTrue(status["config_changed"])

    def test_fresh_failure_is_exit_1(self):
        config = self.root / verify.CONFIG_RELPATH
        config.write_text(checks_toml({"tests": {"command": py_code("raise SystemExit(5)")}}, ["tests"],
                                      include=["src/*"]), encoding="utf-8")
        self.assertEqual(run_cli("--root", str(self.root))[0], 1)
        code, status = self.status()
        self.assertEqual((code, status["state"], status["overall"]), (1, "fresh", "failed"))

    def test_source_changed_by_the_check_itself_is_flagged(self):
        config = self.root / verify.CONFIG_RELPATH
        config.write_text(checks_toml({"fmt": {"command": py_code("open('src/app.py','a').write('#')")}}, ["fmt"],
                                      include=["src/*"]), encoding="utf-8")
        report = verify.run_checks(self.root, verify.load_config(config))
        self.assertTrue(report["source_changed_during_run"])
        self.assertEqual(self.status()[0], 3)

    def test_evidence_and_caches_are_not_part_of_the_source(self):
        root = self.make_project(name="all", config=checks_toml({"tests": {"command": py_code("pass")}}, ["tests"]),
                                 files={"a.py": "x\n", "__pycache__/a.pyc": "junk", "node_modules/m/i.js": "1"})
        state = verify.compute_source_state(root, verify.load_config(root / verify.CONFIG_RELPATH))
        self.assertIn("a.py", state["files"])
        self.assertFalse(any(p.startswith(("__pycache__", "node_modules", ".claude/harness/evidence"))
                             for p in state["files"]))


class SecretsAndOutput(TempDirTest):
    SECRET = "synthetic-test-value-9f8e7d6c"

    def test_secret_environment_values_are_redacted_from_report_and_log(self):
        code = "import os; print('token is', os.environ['CCH_FAKE_API_TOKEN'])"
        root = self.make_project(config=checks_toml(
            {"tests": {"command": [PY, "-c", code, "--key=" + self.SECRET]}}, ["tests"]))
        with mock.patch.dict(os.environ, {"CCH_FAKE_API_TOKEN": self.SECRET, "CCH_PLAIN_SENTINEL": "plain-sentinel-1234"}):
            report = verify.run_checks(root, verify.load_config(root / verify.CONFIG_RELPATH))
        evidence = root / verify.EVIDENCE_RELPATH
        written = "".join(p.read_text(encoding="utf-8") for p in evidence.rglob("*") if p.is_file())
        self.assertEqual(report["overall"], "passed")
        self.assertNotIn(self.SECRET, written)
        self.assertIn("[redacted:CCH_FAKE_API_TOKEN]", written)
        self.assertNotIn("plain-sentinel-1234", written, "the environment must not be dumped into evidence")

    def test_non_utf8_and_non_ascii_output_does_not_break_the_run(self):
        code = "import sys; sys.stdout.buffer.write(b'caf\\xc3\\xa9 \\xe2\\x82\\xac bad:\\xff\\xfe\\n'); sys.exit(1)"
        root = self.make_project(config=checks_toml({"tests": {"command": py_code(code)}}, ["tests"]))
        code_, out, _ = run_cli("--root", str(root))
        self.assertEqual(code_, 1)
        self.assertIn("café €", out)

    def test_large_output_is_bounded(self):
        code = "print('x' * 1000 + '\\n') ; [print('line', i) for i in range(5000)]"
        root = self.make_project(config=checks_toml({"tests": {"command": py_code(code)}}, ["tests"]))
        report = verify.run_checks(root, verify.load_config(root / verify.CONFIG_RELPATH))
        check = report["checks"][0]
        self.assertLessEqual(len(check["output_tail"]), verify.TAIL_CHARS)
        self.assertIn("line 4999", check["output_tail"])
        self.assertLessEqual((root / check["log"]).stat().st_size, verify.LOG_MAX_BYTES + 200)


class Configuration(TempDirTest):
    def assert_config_error(self, text: str, fragment: str) -> None:
        root = self.make_project(config=text)
        code, _, err = run_cli("--root", str(root))
        self.assertEqual(code, 2)
        self.assertIn(fragment, err)

    def test_missing_configuration(self):
        root = self.make_project()
        code, _, err = run_cli("--root", str(root))
        self.assertEqual(code, 2)
        self.assertIn("checks.example.toml", err)

    def test_malformed_toml(self):
        self.assert_config_error("required = [\n", "not valid TOML")

    def test_shell_string_command_is_rejected(self):
        self.assert_config_error('required = ["t"]\n[checks.t]\ncommand = "npm test"\n', "not a shell string")

    def test_unknown_key_is_rejected(self):
        self.assert_config_error('requird = ["t"]\nrequired = ["t"]\n', "unknown key(s) at top level: requird")

    def test_empty_required_is_rejected(self):
        self.assert_config_error("required = []\n", "non-empty list")

    def test_absolute_cwd_is_rejected(self):
        absolute = "C:/elsewhere" if os.name == "nt" else "/elsewhere"
        self.assert_config_error(f'required = ["t"]\n[checks.t]\ncommand = ["x"]\ncwd = "{absolute}"\n', "relative")


if __name__ == "__main__":
    unittest.main()
