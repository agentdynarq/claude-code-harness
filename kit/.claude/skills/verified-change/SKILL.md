---
name: verified-change
description: Make a bounded code change and show evidence that it works, using the project's configured checks in .claude/harness/checks.toml. Use when asked to fix a bug, add a small feature or change behaviour in this repository, especially when a task brief exists.
argument-hint: "[path to a task brief, or a one line objective]"
allowed-tools: Bash(python .claude/harness/verify.py *) Bash(git status *) Bash(git diff *) PowerShell(python .claude/harness/verify.py *) PowerShell(git status *) PowerShell(git diff *)
---

# Verified change

Task: $ARGUMENTS

Work through these steps in order. Stay inside the task's scope. The checks are the
project owner's definition of "works"; your job is to meet them, not to change them.

## 1. Load the task

- If the task above is a file path, read it as the task brief.
- If it is a one line objective, draft a brief from `.claude/harness/templates/task-brief.md`
  and show it to the user. Ask for acceptance criteria if you cannot state them as
  observable results. Do not edit code until the brief has scope, exclusions and
  acceptance criteria.

## 2. Understand before editing

- Read `CLAUDE.md`, the files in scope and the tests that cover the behaviour.
- Run `python .claude/harness/verify.py` once to record the starting state. Note which
  required checks already fail, so you do not claim or chase failures you did not cause.

## 3. Plan when the task warrants it

Write a short plan (files, changes, new tests) and wait for confirmation when the change
touches more than one module, changes a public interface, or the brief leaves a design
choice open. For a change inside one function with a clear test, go straight to step 4.

## 4. Implement a bounded change

- Change only what the brief's scope allows. No unrelated refactors, renames, formatting
  sweeps or dependency changes.
- If the behaviour has no test, add one and confirm it fails before your fix.

## 5. Run the agreed verification

- Run the focused command from the brief, then `python .claude/harness/verify.py`.
- Read the summary, not only the exit code. If a required check fails, fix the cause and
  rerun. Never weaken a test, edit `.claude/harness/checks.toml` or disable the Stop hook
  to get a pass.
- NOT CONFIGURED or SKIPPED required checks are the owner's decision: report them.

## 6. Inspect the diff

Run `git status --short` and `git diff`. Remove anything outside scope: debug output,
commented-out code, stray files, secrets, generated files.

## 7. Report evidence and limits

- Run `python .claude/harness/verify.py status` and confirm the evidence is FRESH. If you
  changed a file after the last run, run verify.py again first.
- Write a handoff from `.claude/harness/templates/handoff.md` next to the brief, then give
  the user: what changed, the verify result per required check, the source fingerprint,
  what is still unverified, and the next action.
- Say plainly when a check failed, timed out, was skipped or is not configured. A passing
  check shows that the configured commands passed; it does not prove anything they do not test.
