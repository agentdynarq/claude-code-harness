# claude-code-harness

Before you code, build the harness: context, tools, checks.

A small starter kit for using Claude Code on an existing project. It gives Claude
written context, a short workflow to follow, and a check runner that decides whether
a change is done. An optional Stop hook closes the loop by sending failures back to
Claude before a turn ends.

This is an independent project for use with Claude Code. It is not made, reviewed or
endorsed by Anthropic.

## Who it is for

Developers who use Claude Code on a project that already has tests, linters or build
commands, and who want three things:

- Claude starts each task with the project's real constraints and commands.
- Each task has written acceptance criteria and a way to check them.
- "Done" means the agreed checks passed on the code as it is now, not on an earlier version.

## What "harness" means here

The harness is everything around the coding agent that guides it and judges its
output: the instructions it reads, the tools and workflow it follows, the checks that
run, and the feedback that reaches it. Claude Code's own agent runtime is unchanged;
this kit only adds files that Claude Code already knows how to read.

```
  Context               Work                      Checks                    Feedback
  CLAUDE.md       --->  /verified-change   --->   verify.py          --->   summary + JSON report
  task brief            understand, plan,         runs checks.toml,         optional Stop hook:
                        edit, inspect diff        ties the result to        a failure sends Claude
                                                  the source state          back to work (bounded)
      ^                                                                          |
      +----------------------- handoff note with the evidence <------------------+
```

## What is in the kit

Everything that gets copied into a project lives in [`kit/`](kit/):

| Path in your project | What it is |
| --- | --- |
| `.claude/harness/verify.py` | The check runner. Standard library Python, no dependencies |
| `.claude/harness/checks.example.toml` | Commented example. You copy it to `checks.toml` and list your real commands |
| `.claude/harness/stop_hook.py` | Optional Claude Code Stop hook around `verify.py` |
| `.claude/harness/hook-settings.example.json` | The settings entry for that hook. You merge it by hand |
| `.claude/harness/templates/` | `CLAUDE.template.md`, `task-brief.md`, `handoff.md` |
| `.claude/skills/verified-change/SKILL.md` | One skill: understand, plan when warranted, make a bounded change, verify, inspect the diff, report |

Outside the kit: [`install.py`](install.py) (preview, install, remove),
[`examples/invoice-totals`](examples/invoice-totals) (a project with a real bug),
[`scripts/demo.py`](scripts/demo.py) (the walkthrough),
[`scripts/live_session_check.py`](scripts/live_session_check.py) (records a real Claude Code
session on the example), [`scripts/mutation_check.py`](scripts/mutation_check.py) (breaks the
code on purpose and confirms a test notices), and [`tests/`](tests).

## Requirements

- Python 3.11 or newer. Nothing to install from PyPI.
- Claude Code, only for the skill and the hook. The checks, demo and tests run without it.
- git, only for the skill's diff step.
- No API key, MCP server, database or account for the demo and tests.

## Quickstart

```
git clone https://github.com/agentdynarq/claude-code-harness
cd claude-code-harness
python -m unittest discover -s tests
python scripts/demo.py
```

The demo copies the example project to a temporary folder whose path contains spaces,
runs every step below for real, checks each outcome, and deletes the folder. It exits 0
only if all 14 expectations hold. Add `--keep` to inspect the folder afterwards.

## The working example

[`examples/invoice-totals`](examples/invoice-totals) computes invoice totals. Its
[`CLAUDE.md`](examples/invoice-totals/CLAUDE.md) says VAT rounds half a cent away from
zero. The code uses Python's `round()`, which rounds half to even on `Decimal`, so
1.50 at 19% gives 0.28 VAT instead of 0.29. The example ships with that bug on purpose.

**1. The task.** [`docs/tasks/fix-vat-rounding.md`](examples/invoice-totals/docs/tasks/fix-vat-rounding.md)
states the objective, scope, exclusions, 6 acceptance criteria and the verification commands.

**2. The initial failing check.** Excerpts from the recorded run in
[`docs/evidence/2026-10-11-demo-windows-py313.txt`](docs/evidence/2026-10-11-demo-windows-py313.txt). `...` marks lines left out here.

```
  FAILED         tests      required  exit 1  0.16s  <python> -m unittest discover -s tests -v
      | AssertionError: Decimal('0.28') != Decimal('0.29')
      ...
      | AssertionError: Decimal('0.52') != Decimal('0.54')
      ...
      | FAILED (failures=2)
  SKIPPED        typecheck  optional
      not run: mypy is not a dependency of this example; set enabled = true where it is installed

RESULT   FAILED  (0 of 1 required checks passed)
```

**3. The change.**

```diff
-from decimal import Decimal
+from decimal import ROUND_HALF_UP, Decimal
...
-    vat = sum((round(amount * rate, 2) for rate, amount in net_by_rate.items()), Decimal("0"))
+    vat = sum(
+        ((amount * rate).quantize(CENT, rounding=ROUND_HALF_UP) for rate, amount in net_by_rate.items()),
+        Decimal("0"),
+    )
```

**4. The passing check**, then a freshness check against the current source:

```
  PASSED         tests      required  exit 0  0.14s  <python> -m unittest discover -s tests -v
...
RESULT   PASSED  (1 of 1 required checks passed)

evidence  FRESH
...
recorded  74eb229d6ac5
current   74eb229d6ac5
```

**5. The bug reintroduced.** `verify.py` fails again with the same two assertions.

**6. Stale evidence.** Before rerunning, `status` refuses to reuse the earlier pass:

```
evidence  STALE
report    .claude/harness/evidence/latest.json (PASSED, finished 2026-10-10T19:10:14Z)
recorded  74eb229d6ac5
current   2e1c003125f9
  modified  invoice_totals/totals.py
The recorded result does not apply to the current source. Run verify.py again.
```

Editing `CLAUDE.md` leaves the evidence fresh, because the example's `[source] include`
selects only `invoice_totals/*` and `tests/*`.

### Reproduce it by hand

PowerShell:

```powershell
$demo = Join-Path $env:TEMP "invoice demo"
Copy-Item -Recurse examples\invoice-totals $demo
python install.py install $demo --dry-run
python install.py install $demo
Set-Location $demo
python .claude/harness/verify.py           # FAILED, exit 1
# make the change shown above in invoice_totals/totals.py
python .claude/harness/verify.py           # PASSED, exit 0
python .claude/harness/verify.py status    # FRESH, exit 0
# undo the change
python .claude/harness/verify.py status    # STALE, exit 3
```

bash: the same commands with `demo="$(mktemp -d)/invoice demo"`, `cp -r examples/invoice-totals "$demo"`
and `cd "$demo"`.

## Adopt it in an existing project

1. Preview. Nothing is written:
   ```
   python install.py install path/to/your-project --dry-run
   ```
   Each kit file is listed as `create`, `unchanged`, `kept` or `conflict`.
2. Install. The installer only creates new files, inside the target, opened in exclusive
   create mode. If any file conflicts, it writes nothing and stops. It never edits
   `CLAUDE.md`, `.claude/settings*.json`, hooks or permissions, and it never runs your
   project's commands. It records what it added, with hashes, in
   `.claude/harness/install-manifest.json`. Running it again changes nothing.
   ```
   python install.py install path/to/your-project
   ```
3. Copy `.claude/harness/checks.example.toml` to `checks.toml` and list the commands
   your project already uses, for example `["npm", "test"]` or `["{python}", "-m", "pytest"]`.
   Until you do, `verify.py` exits 2 and names the missing file.
4. Run `python .claude/harness/verify.py` yourself and read the result.
5. Context. If you have no `CLAUDE.md`, start from `templates/CLAUDE.template.md`. If you
   have one, add a definition-of-done line that names `verify.py`. Put per-task acceptance
   criteria in a task brief, not in `CLAUDE.md`.
6. Work. In Claude Code: `/verified-change docs/tasks/your-task.md`.
7. Optional hook, see below.

Remove with `python install.py remove path/to/your-project --dry-run`, then without
`--dry-run`. Removal deletes only files whose hash still matches what was installed.
Files you edited, `checks.toml`, and `evidence/` stay.

## How checks work

`checks.toml` lists commands as argument lists. They run without a shell, with a
per-check timeout and a total budget. On timeout the whole process tree is terminated
(a test confirms a grandchild process does not survive; it passed on Windows, Linux and macOS).

| Outcome | Meaning |
| --- | --- |
| `PASSED` | exit code 0 |
| `FAILED` | non-zero exit code (recorded as is), or the command could not start |
| `TIMEOUT` | stopped at its time limit |
| `SKIPPED` | `enabled = false`, or the total budget ran out first |
| `NOT CONFIGURED` | named in `required` but has no command |

The result is `PASSED` only if every required check passed. `verify.py` exits 0, 1, or 2
for a configuration error. Each run writes `.claude/harness/evidence/latest.json` with
each check's name, command, working directory, duration, outcome, exit code and output
tail, plus a SHA-256 fingerprint of the selected source files and of `checks.toml`.
`verify.py status` recomputes the fingerprint and exits 0 fresh pass, 1 fresh failure,
3 stale, 4 no evidence. The evidence folder ignores itself in git.

Values of environment variables whose names look secret (`TOKEN`, `SECRET`, `PASSWORD`,
`API_KEY` and similar) are replaced if they appear in output or commands. The environment
itself is never written. This catches only secrets present verbatim in the environment.

**Listing a command in `checks.toml` authorises `verify.py`, and the hook if enabled, to
run it with your user permissions. The configuration is not a sandbox.**

## The optional Stop hook

The hook runs when Claude finishes a turn. If the selected source is unchanged since
the last report, it reuses that report. Otherwise it runs the checks. When a required
check fails it returns `{"decision": "block", "reason": ...}` with the failure output, so
Claude continues with the failure in view.

Loop protection: Claude Code stops honouring Stop hook blocks after 8 continuations in a
row, but that count resets whenever Claude calls a tool, which a fixing agent does. So
the hook keeps its own limits: at most `stop_hook_max_blocks` blocks in a row (default 2,
`0` reports without blocking), and never a second block for the same unchanged source.
Malformed input or an internal error exits 1, a non-blocking error in Claude Code's
contract. The hook never exits 2. Missing or invalid `checks.toml` produces a message,
not a block.

**Enable it deliberately.** Read
[`hook-settings.example.json`](kit/.claude/harness/hook-settings.example.json), then copy
its `Stop` entry into `.claude/settings.local.json` (only you) or `.claude/settings.json`
(everyone who clones). It uses exec form, `"command": "python"` with the script path in
`args`, which the docs say spawns the program directly with no shell on any platform.
Use `python3` if that is your interpreter's name. Keep the hook `timeout` above
`total_timeout_seconds`.

**Disable it:**
- delete the `Stop` entry from the settings file,
- or start Claude Code with the environment variable `HARNESS_STOP_HOOK=off`,
- or run one session with `claude --settings '{"disableAllHooks": true}'`.

## Instructions versus enforced checks

| Part | Kind | Limits |
| --- | --- | --- |
| `CLAUDE.md`, task brief, skill | Context. Claude Code's docs call CLAUDE.md "context, not enforced configuration" | Claude may misread or skip them |
| `verify.py` | Runs the configured commands and reports exactly what they returned | Proves only what your tests test. Runs with your permissions |
| Stop hook | Runs automatically at the end of a turn | Local hooks can be edited or disabled by anyone with write access to the repository, including Claude. Not a security boundary |
| Claude Code permissions (`permissions.deny` in settings) | Enforced by the Claude Code client | Covers Claude's tools and recognised file commands, not arbitrary scripts. For OS-level isolation use Claude Code's sandbox |

To stop Claude editing the harness itself, add native deny rules such as
`"Edit(.claude/harness/**)"` to `.claude/settings.json`. Within the limits above, that is
stronger than any sentence in `CLAUDE.md`. This kit does not try to detect dangerous
shell commands with patterns; use Claude Code's permission rules and sandbox for that.

## Tested environments and evidence

Evidence is kept in [`docs/evidence`](docs/evidence), separated by kind:

| Category | Status |
| --- | --- |
| A. Unit and integration tests, demo, deliberate-defect check | Locally on Windows 11 with Python 3.13 and 3.11, including the deliberate-defect check. In GitHub Actions on Ubuntu, macOS and Windows with Python 3.11 and 3.13: all tests and the demo passed, with one Windows-only test skipped off Windows |
| B. Hook contract tests with fixture payloads | Ran on the same setups. Fixture payloads follow the documented Stop schema; they were not produced by Claude Code |
| C. Real Claude Code session | 2 scenarios on Windows with Claude Code 2.1.296 and one model, recorded in [`docs/evidence/live-session`](docs/evidence/live-session). `fix`: the skill's workflow end to end, the hook reused a fresh pass. `regression`: Claude broke the tests and tried to stop, the hook blocked once, Claude received the failure and stopped to ask instead of weakening the tests. Two runs are examples, not a measurement |
| D. Comparative effectiveness | **Not run.** No claim is made that this kit makes developers faster or Claude's code better |

The GitHub Actions results are recorded in
[`docs/evidence/2026-10-11-ci-run-38078843521.txt`](docs/evidence/2026-10-11-ci-run-38078843521.txt),
extracted from the job logs. The deliberate-defect check ran on Windows only.

The Claude Code facts this kit relies on, and where they come from, are in
[`docs/claude-code-contract.md`](docs/claude-code-contract.md). They were checked
against the documentation on 10 Oct 2026 and Claude Code 2.1.296.

## Known limitations

- On Windows, processes a check leaves running after it exits normally are not cleaned
  up. On timeout the whole tree is killed with `taskkill /T`. On Linux and macOS each
  check runs in its own session; the timeout test (a grandchild must not survive) passed
  there in CI, but killing leftovers after a normal exit has no test.
- `.cmd` and `.bat` commands on Windows run through `cmd.exe` by the operating system,
  so their arguments follow `cmd.exe` parsing.
- Every Stop hashes the selected source files. On a large repository, narrow `[source] include`.
- The fingerprint covers file contents and `checks.toml`. It does not cover installed
  tool versions, the environment or files outside the include patterns.
- Redaction catches only secret values present verbatim in the environment.
- The hook state is per project, not per concurrent session; two sessions in one
  checkout share one retry count.

## How this differs from llm-eval-harness

[llm-eval-harness](https://github.com/agentdynarq/llm-eval-harness) evaluates
language-model answers and retrieval results. claude-code-harness does not score model
output. It runs a software project's own checks against a coding agent's changes and
records whether they passed on the current source.

## License

MIT. See [LICENSE](LICENSE).
