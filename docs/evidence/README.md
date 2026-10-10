# Evidence

Every file here is a transcript of a real run, recorded on 11 Oct 2026 local time
(10 Oct UTC) on one machine: Windows 11 Home 10.0.26200, Claude Code 2.1.296 installed.
Paths under the home directory are replaced with `~`, temporary project paths with
`<project>`, and interpreter paths with `<python>`. Nothing else was edited.

The tests were written and graded by the same Claude Code session that wrote the code.
No independent reviewer has checked them.

## A. Unit and integration correctness: ran

| Run | Result | Transcript |
| --- | --- | --- |
| `python -m unittest discover -s tests -v`, Python 3.13.12 | 74 tests, OK | [2026-10-11-tests-windows-py313.txt](2026-10-11-tests-windows-py313.txt) |
| same, Python 3.11.17 | 74 tests, OK | [2026-10-11-tests-windows-py311.txt](2026-10-11-tests-windows-py311.txt) |
| `python scripts/demo.py`, Python 3.13.12 | 14 of 14 expectations met | [2026-10-11-demo-windows-py313.txt](2026-10-11-demo-windows-py313.txt) |
| same, Python 3.11.17 | 14 of 14 expectations met | [2026-10-11-demo-windows-py311.txt](2026-10-11-demo-windows-py311.txt) |
| `python scripts/mutation_check.py`, Python 3.13.12 | 23 of 23 deliberate defects caught | [2026-10-11-mutation-check-windows-py313.txt](2026-10-11-mutation-check-windows-py313.txt) |
| `verify.py` on Python 3.10.20 | refuses, exit 2 | [2026-10-11-python310-refusal.txt](2026-10-11-python310-refusal.txt) |
| `stop_hook.py` on Python 3.10.20 | refuses, exit 1 (non-blocking) | [2026-10-11-python310-hook-refusal.txt](2026-10-11-python310-hook-refusal.txt) |

The 74 tests include the 12 cases the brief named:

| Case | Test |
| --- | --- |
| Required check succeeds | `test_verify.RunOutcomes.test_required_check_succeeds` |
| Required check fails, exit code kept | `test_verify.RunOutcomes.test_required_check_fails_and_exit_code_is_preserved` |
| Required check absent | `test_verify.RunOutcomes.test_required_check_absent_fails_overall` |
| Command times out, process tree killed | `test_verify.Timeouts.test_timeout_is_reported_and_the_process_tree_is_killed` |
| Evidence stale after a relevant change | `test_verify.Evidence.test_evidence_becomes_stale_after_a_relevant_change` |
| Malformed hook input | `test_stop_hook.HookProcess.test_malformed_json_is_a_non_blocking_error` |
| Hook recursion and retries | `test_stop_hook.HookProcess.test_retries_are_bounded_while_claude_keeps_changing_code`, `test_unchanged_failure_is_not_blocked_twice_even_on_a_new_turn` |
| Installation conflict | `test_install.Install.test_conflicting_file_refuses_the_whole_install` |
| Repeated installation | `test_install.Install.test_repeated_install_is_idempotent` |
| Target path with spaces | `test_install.Install.test_target_path_with_spaces`, `test_verify.RunOutcomes.test_working_directory_and_paths_with_spaces` |
| Writing outside the target | `test_install.StayInsideTarget` (3 tests, including a real Windows junction) |
| Removal keeps user-modified content | `test_install.Remove.test_removal_keeps_user_modified_and_user_created_files` |

The deliberate-defect run applies each defect to a fresh temporary copy and requires
the named test to fail. One defect was not caught on the first attempt: the Unicode
payload test sent `\u` escapes instead of raw UTF-8, so it never exercised decoding.
The test was fixed and the defect is now caught (number 12 in the transcript).

**Not tested:** Linux and macOS. WSL on this machine cannot start because
virtualization is disabled. The CI workflow has not run.

## B. Hook contract fixture tests: ran

`tests/test_stop_hook.py` (20 tests) and step 11 of the demo pipe hand-written
payloads into `stop_hook.py` as a subprocess and check exit codes and stdout JSON
against the documented Stop contract (see [../claude-code-contract.md](../claude-code-contract.md)).
The payloads were written from the documentation. Claude Code did not produce them, and
these tests do not show that Claude Code acts on the hook's output.

## C. Real Claude Code session: not run

This session ran inside Claude Code, which guards against starting a nested session.
Getting around that guard was not attempted. To run it yourself, from a normal
terminal in this repository:

```
python scripts/live_session_check.py --dry-run     # prepares a temp copy, prints the command
python scripts/live_session_check.py --run         # uses your Claude Code login; counts against usage
```

What `--run` does:

1. Copies `examples/invoice-totals` to a temporary folder, commits it with git, installs
   the kit, and enables the Stop hook in that copy's `.claude/settings.local.json` only.
2. Runs `claude -p "/verified-change docs/tasks/fix-vat-rounding.md"` with
   `--permission-mode acceptEdits`, an `--allowedTools` list for the test and verify
   commands, `--max-budget-usd 3`, `--no-session-persistence` and a debug log.
3. Writes `docs/evidence/live-session/record.md` with the tool calls, the Stop hook lines
   from the debug log, the hook state, `verify.py status`, the diff and the final
   message, plus the raw stream with paths replaced. Read it before committing it.

What would count as a pass: the Stop hook appears in the debug log, `verify.py status`
reports FRESH and PASSED, and the diff changes only the rounding step (plus a handoff
note). A different outcome is still a valid record; report it as it is.

The `--dry-run` path was run on this machine: it created the temporary project, one
commit, the installed kit and the hook entry, and printed the command. The refusal to
start inside Claude Code was also checked (exit 2).

## D. Comparative effectiveness: not run

No experiment compared sessions with and without this kit. Nothing in this repository
claims that it makes developers faster, makes Claude's code better, or reduces defects
by any amount.
