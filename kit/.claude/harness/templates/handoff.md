<!--
TEMPLATE from claude-code-harness. Write one at the end of a task, next to its brief.
Report what happened, including checks that failed, timed out, were skipped or are
not configured. Copy values from the verify.py output; do not round them up.
-->
# Handoff: [REPLACE: task name]

Date: [REPLACE: YYYY-MM-DD]
Brief: `[REPLACE: path to the task brief]`

## Completed work
- [REPLACE: change, with the file it is in]

## Evidence
- Command: `python .claude/harness/verify.py`
- Result: [REPLACE: PASSED or FAILED, with each required check's outcome]
- Source state: [REPLACE: first 12 characters of the fingerprint from the verify output]
- Evidence status at handoff: [REPLACE: FRESH or STALE, from verify.py status]
- Report: `.claude/harness/evidence/latest.json`

## Unresolved problems
- [REPLACE: what is still wrong or unverified, or "None known"]

## Next action
- [REPLACE: the single next step, and who takes it]
