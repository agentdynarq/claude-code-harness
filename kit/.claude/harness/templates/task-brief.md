<!--
TEMPLATE from claude-code-harness. One brief per task. Copy it to your task folder,
replace every [REPLACE: ...] marker, and hand the file to Claude, for example:
/verified-change docs/tasks/<task>.md
Each acceptance criterion should be something a command or a reviewer can observe.
-->
# Task: [REPLACE: short name]

## Objective
[REPLACE: the behaviour that should exist after this task, and why.]

## Scope
- [REPLACE: files or modules that may change]

## Exclusions
- [REPLACE: what must not change, for example public interfaces, dependencies, config]

## Acceptance criteria
1. [REPLACE: observable result, for example "input X gives output Y"]
2. `python .claude/harness/verify.py` reports PASSED and `status` reports FRESH evidence.

## Verification commands
```
[REPLACE: the focused command for this task, for example one test file]
python .claude/harness/verify.py
python .claude/harness/verify.py status
```
