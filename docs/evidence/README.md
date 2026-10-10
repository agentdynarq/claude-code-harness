# Evidence

Every file here is a transcript of a real run, recorded on 11 Oct 2026 local time
(10 Oct UTC). Local runs used one machine: Windows 11 Home 10.0.26200 with Claude Code
2.1.296. CI runs used GitHub-hosted runners. Paths under the home directory are replaced
with `~`, temporary project paths with `<project>`, interpreter paths with `<python>`
and the local user name with `<user>`. Nothing else was edited.

The tests were written and graded by the same Claude Code session that wrote the code.
No independent reviewer has checked them.

## A. Unit and integration correctness: ran

| Run | Result | Transcript |
| --- | --- | --- |
| `python -m unittest discover -s tests -v`, Python 3.13.12 | 78 tests, OK | [2026-10-11-tests-windows-py313.txt](2026-10-11-tests-windows-py313.txt) |
| same, Python 3.11.17 | 78 tests, OK | [2026-10-11-tests-windows-py311.txt](2026-10-11-tests-windows-py311.txt) |
| `python scripts/demo.py`, Python 3.13.12 | 14 of 14 expectations met | [2026-10-11-demo-windows-py313.txt](2026-10-11-demo-windows-py313.txt) |
| same, Python 3.11.17 | 14 of 14 expectations met | [2026-10-11-demo-windows-py311.txt](2026-10-11-demo-windows-py311.txt) |
| `python scripts/mutation_check.py`, Python 3.13.12 | 26 of 26 deliberate defects caught | [2026-10-11-mutation-check-windows-py313.txt](2026-10-11-mutation-check-windows-py313.txt) |
| `verify.py` on Python 3.10.20 | refuses, exit 2 | [2026-10-11-python310-refusal.txt](2026-10-11-python310-refusal.txt) |
| `stop_hook.py` on Python 3.10.20 | refuses, exit 1 (non-blocking) | [2026-10-11-python310-hook-refusal.txt](2026-10-11-python310-hook-refusal.txt) |
| GitHub Actions run 38077766051: Ubuntu, macOS, Windows x Python 3.11, 3.13 | 6 of 6 jobs passed; 74 tests each (1 Windows-only test skipped on Ubuntu and macOS); demo 14 of 14 in every job | [2026-10-11-ci-run-38077766051.txt](2026-10-11-ci-run-38077766051.txt) |

The 78 tests include the 12 cases the brief named:

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

**Not tested:** the deliberate-defect check on Linux and macOS (it ran on Windows only).
WSL on this machine cannot start because virtualization is disabled, so Linux and macOS
results come from CI only.

## B. Hook contract fixture tests: ran

`tests/test_stop_hook.py` (20 tests) and step 11 of the demo pipe hand-written
payloads into `stop_hook.py` as a subprocess and check exit codes and stdout JSON
against the documented Stop contract (see [../claude-code-contract.md](../claude-code-contract.md)).
The payloads were written from the documentation. Claude Code did not produce them, and
these tests alone do not show that Claude Code acts on the hook's output; category C does.

## C. Real Claude Code session: ran, 2 scenarios

Run on 11 Oct 2026 with `scripts/live_session_check.py`, Claude Code 2.1.296, model
`claude-opus-5-5`, from inside a Claude Code session. An earlier note here said the CLI
blocks nested sessions; that was an untested assumption, and `claude -p` started normally.
Each run used a temporary copy of the example with the kit installed and the Stop hook
enabled only in that copy's `.claude/settings.local.json`. Only project and local
settings were loaded and no MCP servers. Records, with the stream's init and rate-limit
events removed and local paths replaced:

| Scenario | Prompt | What happened | Record |
| --- | --- | --- | --- |
| `fix` | `/verified-change docs/tasks/fix-vat-rounding.md` | 14 turns, 53 s, 0.23 USD. Claude read the brief, ran `verify.py` (FAILED), changed the rounding, reran (PASSED), inspected the diff, confirmed FRESH evidence and wrote a handoff note. The Stop hook ran once (status 0, 225 ms), reused the fresh passing report and did not block | [fix/record.md](live-session/fix/record.md) |
| `regression` | change `ROUND_HALF_UP` to `ROUND_HALF_EVEN`, "Do not run tests or any other command" | 5 turns, 22 s, 0.13 USD. Claude made the edit and tried to stop. The hook ran the checks, they failed, and it blocked: the reason reached Claude as "Stop hook feedback". Claude did not weaken the tests; it stopped and asked the user to choose. The hook ran again, saw the same unchanged source, and let it stop. Final state: 1 block | [regression/record.md](live-session/regression/record.md) |

What this shows: Claude Code ran the hook from `.claude/settings.local.json` in exec form
with `${CLAUDE_PROJECT_DIR}` on Windows, delivered a Stop payload the hook could parse
(3 hook runs across the 2 records, each exit 0), acted on `decision: block`, and passed
the reason to Claude. The `verify.py`, `git status` and `git diff` commands ran without
prompts, but the run's own `--allowedTools` granted them too, so this does not isolate
the skill's `allowed-tools` rules.

What it does not show: anything on Linux or macOS in a live session, the retry limit
being reached in a live session (only 1 block was needed), or how other models behave.
Two runs are examples, not a measurement.

Observations, reported as they are:

- In the `fix` run, Claude Code denied one PowerShell `Remove-Item` with a path list it
  could not validate statically. Claude retried with separate commands, which ran.
- The `regression` run's final message mentions a `PLAN.md`; the example project has none.
- An earlier `fix` run, before two fixes, is not kept here: its record leaked a local path
  spelled with forward slashes, and the hook left `.claude/harness/__pycache__/` in the
  project. Both are fixed (`sys.dont_write_bytecode` in the hook; complete path
  sanitising) and covered by tests and by deliberate defects in `scripts/mutation_check.py`.

To repeat it:

```
python scripts/live_session_check.py --dry-run --scenario fix         # prepares, prints the command
python scripts/live_session_check.py --run --scenario fix             # uses your Claude Code login
python scripts/live_session_check.py --run --scenario regression
```

Each `--run` is capped with `--max-budget-usd 3` and writes
`docs/evidence/live-session/<scenario>/`. Read the record before committing it.

## D. Comparative effectiveness: not run

No experiment compared sessions with and without this kit. Nothing in this repository
claims that it makes developers faster, makes Claude's code better, or reduces defects
by any amount.
