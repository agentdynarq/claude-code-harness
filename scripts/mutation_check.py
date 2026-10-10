#!/usr/bin/env python3
"""Break the code on purpose and confirm the tests notice.

For each mutation: copy the repository to a temporary directory, apply one deliberate
defect, run the test that should catch it, and require that test to FAIL. A test that
has only ever been seen to pass has not shown that it can catch anything.

    python scripts/mutation_check.py           run every mutation
    python scripts/mutation_check.py 3 7       run selected mutations by number

Exits 0 only if every selected mutation was caught. The repository itself is not modified.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VERIFY = "kit/.claude/harness/verify.py"
HOOK = "kit/.claude/harness/stop_hook.py"
INSTALL = "install.py"

# (description, file, original text, defect, test that must fail)
MUTATIONS = [
    ("timeout leaves the process tree running", VERIFY,
     "            _terminate_tree(proc)\n            outcome, exit_code = TIMEOUT, None",
     "            proc.kill()\n            outcome, exit_code = TIMEOUT, None",
     "test_verify.Timeouts.test_timeout_is_reported_and_the_process_tree_is_killed"),
    ("redaction does nothing", VERIFY,
     "            if value in text:\n", "            if False:\n",
     "test_verify.SecretsAndOutput.test_secret_environment_values_are_redacted_from_report_and_log"),
    ("overall ignores required results", VERIFY,
     "    overall = PASSED if all(r.outcome == PASSED for r in results if r.required) else FAILED",
     "    overall = PASSED",
     "test_verify.RunOutcomes.test_required_check_fails_and_exit_code_is_preserved"),
    ("real exit code replaced by 1", VERIFY,
     "    result.exit_code = exit_code\n", "    result.exit_code = None if exit_code is None else min(exit_code, 1)\n",
     "test_verify.RunOutcomes.test_required_check_fails_and_exit_code_is_preserved"),
    ("required check without a table is ignored", VERIFY,
     "        if name not in defined:\n", "        if False:\n",
     "test_verify.RunOutcomes.test_required_check_absent_fails_overall"),
    ("fingerprint ignores file content", VERIFY,
     "                files[rel] = _hash_file(current / filename)",
     "                files[rel] = 'same'",
     "test_verify.Evidence.test_evidence_becomes_stale_after_a_relevant_change"),
    ("fingerprint ignores the checks configuration", VERIFY,
     'digest.update(f"{FINGERPRINT_SCHEME}\\nconfig {config.sha256}\\n".encode())',
     'digest.update(f"{FINGERPRINT_SCHEME}\\n".encode())',
     "test_verify.Evidence.test_changing_the_checks_makes_evidence_stale"),
    ("shell string commands accepted", VERIFY,
     "            if isinstance(command, str):\n", "            if isinstance(command, str) and False:\n",
     "test_verify.Configuration.test_shell_string_command_is_rejected"),
    ("hook ignores its retry limit", HOOK,
     "    if new.consecutive_blocks >= max_blocks:\n", "    if False:\n",
     "test_stop_hook.HookProcess.test_retries_are_bounded_while_claude_keeps_changing_code"),
    ("hook blocks the same unchanged failure again", HOOK,
     "    if new.notified_fingerprint == result.fingerprint:\n", "    if False:\n",
     "test_stop_hook.HookProcess.test_unchanged_failure_is_not_blocked_twice_even_on_a_new_turn"),
    ("hook exits 2 on an internal error", HOOK,
     "internal error: {exc.__class__.__name__}: {exc}\", file=sys.stderr)\n        return 1",
     "internal error: {exc.__class__.__name__}: {exc}\", file=sys.stderr)\n        return 2",
     "test_stop_hook.HookProcess.test_internal_error_exits_1_never_2"),
    ("hook reads stdin in the console code page", HOOK,
     "    stdin = io.TextIOWrapper(sys.stdin.buffer, encoding=\"utf-8\", errors=\"replace\")",
     "    stdin = sys.stdin",
     "test_stop_hook.HookProcess.test_unicode_payload_is_read_as_utf8"),
    ("hook accepts any event", HOOK,
     "    if event != \"Stop\":\n", "    if False:\n",
     "test_stop_hook.HookProcess.test_wrong_event_or_fields_are_rejected"),
    ("hook blocks when the configuration is missing", HOOK,
     "        _emit(stdout, {\"systemMessage\": (\n            f\"{PREFIX}: checks did not run because",
     "        _emit(stdout, {\"decision\": \"block\", \"reason\": (\n            f\"{PREFIX}: checks did not run because",
     "test_stop_hook.HookProcess.test_missing_configuration_is_reported_and_does_not_block"),
    ("hook reuses evidence after the source changed", HOOK,
     "    if report is not None and report[\"source_state\"].get(\"fingerprint\") == current[\"fingerprint\"]:",
     "    if report is not None:",
     "test_stop_hook.HookProcess.test_passing_checks_allow_stop_and_unchanged_source_reuses_evidence"),
    ("hook leaves __pycache__ in the project", HOOK,
     "sys.dont_write_bytecode = True  # leave no __pycache__ in the user's .claude/harness\n", "",
     "test_stop_hook.HookProcess.test_passing_checks_allow_stop_and_unchanged_source_reuses_evidence"),
    ("live record keeps forward-slash paths", "scripts/live_session_check.py",
     'variants = {native, native.replace("\\\\", "\\\\\\\\"), native.replace("\\\\", "/")}',
     'variants = {native, native.replace("\\\\", "\\\\\\\\")}',
     "test_live_record.Sanitise.test_every_spelling_of_local_paths_is_replaced"),
    ("live record keeps a stray user name", "scripts/live_session_check.py",
     "    if len(home.name) >= 3:\n", "    if False:\n",
     "test_live_record.Sanitise.test_a_stray_user_name_is_replaced"),
    ("installer follows links out of the target", INSTALL,
     "    if not resolved.is_relative_to(target):\n", "    if False:\n",
     "test_install.StayInsideTarget.test_directory_link_inside_target_cannot_redirect_writes"),
    ("installer allows '..' segments", INSTALL,
     "any(part in (\"..\", \"\") for part in rel.split(\"/\"))", "False",
     "test_install.StayInsideTarget.test_relative_paths_that_escape_are_rejected"),
    ("installer overwrites conflicting files", INSTALL,
     "                items.append(Item(rel, \"conflict\", \"already exists with different content",
     "                items.append(Item(rel, \"create\", \"already exists with different content",
     "test_install.Install.test_conflicting_file_refuses_the_whole_install"),
    ("installer ignores --dry-run", INSTALL,
     "    if dry_run:\n        print(\"\\nDry run: nothing was written.\", file=out)\n        return 0\n",
     "",
     "test_install.Install.test_dry_run_writes_nothing"),
    ("removal deletes modified files", INSTALL,
     "        elif sha256_file(dest) == digest:\n", "        elif True:\n",
     "test_install.Remove.test_removal_keeps_user_modified_and_user_created_files"),
    ("an em dash in the README", "README.md",
     "## Who it is for\n", "## Who it is for " + chr(0x2014) + " and who it is not\n",
     "test_repo_text.RepositoryText.test_no_em_or_en_dashes"),
    ("an unresolved template marker in the example", "examples/invoice-totals/CLAUDE.md",
     "## Purpose\n", "## Purpose\n[REPLACE: one or two sentences]\n",
     "test_repo_text.RepositoryText.test_templates_are_marked_and_nothing_else_is_unfinished"),
    ("example test no longer exposes the bug", "examples/invoice-totals/tests/test_totals.py",
     "        self.assertEqual(totals.vat, Decimal(\"0.29\"))", "        self.assertEqual(totals.vat, Decimal(\"0.28\"))",
     "test_demo.Walkthrough.test_demo_meets_every_expectation_and_leaves_the_repository_alone"),
]


def run_mutation(number: int) -> bool:
    description, rel, old, new, test = MUTATIONS[number - 1]
    workspace = Path(tempfile.mkdtemp(prefix="cch-mutation-"))
    try:
        copy = workspace / "repo"
        shutil.copytree(REPO, copy, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        target = copy / rel
        text = target.read_text(encoding="utf-8")
        if text.count(old) != 1:
            print(f"{number:>2}. SETUP ERROR  {description}: original text found {text.count(old)} times in {rel}")
            return False
        target.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
        proc = subprocess.run([sys.executable, "-m", "unittest", test], cwd=copy / "tests",
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
        caught = proc.returncode != 0 and ("FAILED" in proc.stderr or "Error" in proc.stderr)
        verdict = "caught" if caught else "NOT CAUGHT"
        print(f"{number:>2}. {verdict:<11} {description}  ->  {test}")
        return caught
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def main() -> int:
    selected = [int(a) for a in sys.argv[1:]] or list(range(1, len(MUTATIONS) + 1))
    print(f"Applying {len(selected)} deliberate defect(s), each in a fresh temporary copy.")
    results = [run_mutation(n) for n in selected]
    print(f"\n{sum(results)} of {len(results)} defects caught by the named test.")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
