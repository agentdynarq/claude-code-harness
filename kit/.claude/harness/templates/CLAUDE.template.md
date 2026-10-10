<!--
TEMPLATE from claude-code-harness.
Copy this file to CLAUDE.md at your project root (it is named CLAUDE.template.md
so Claude Code does not load it as instructions from this folder), replace every [REPLACE: ...] marker
and delete any section that does not apply. Keep the result short; Claude Code's docs
recommend under 200 lines. Task-specific acceptance criteria do not belong here: put
them in a task brief (templates/task-brief.md).

This file guides Claude. It does not enforce anything. Block HTML comments like this
one are stripped before Claude reads the file.
-->
# [REPLACE: project name]

## Purpose
[REPLACE: one or two sentences on what this project does and who uses it.]

## Architecture constraints
- [REPLACE: a rule Claude must respect, for example "Money is Decimal, never float."]
- [REPLACE: another, for example "The domain package makes no network calls."]

## Commands
- Install: `[REPLACE: install command]`
- Test: `[REPLACE: test command]`
- Lint: `[REPLACE: lint command, or delete this line]`
- All required checks: `python .claude/harness/verify.py` (listed in `.claude/harness/checks.toml`)

## Handle with care
- `[REPLACE: path]`: [REPLACE: why a change here is risky]

## Definition of done
- The task brief's acceptance criteria are met.
- `python .claude/harness/verify.py` reports PASSED.
- `python .claude/harness/verify.py status` reports FRESH evidence for the final source.
- The diff contains only changes inside the brief's scope.
- A handoff note lists the evidence, unresolved problems and the next action.

## Where details live
- Task briefs and handoff notes: `[REPLACE: for example docs/tasks/]`
- [REPLACE: architecture notes, ADRs, runbooks, or delete this line]
