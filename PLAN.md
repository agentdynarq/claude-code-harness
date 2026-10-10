# Plan and decision log

## Purpose

A small, tested starter kit that shows the three parts of a coding-agent harness
(context, tools, checks) working together on a real example, to support the post
"Before you code. Build the harness." The repository has to earn that message with
working code and recorded evidence.

## Scope of release 0.1.0

In: CLAUDE.md, task brief and handoff templates; one skill; a check runner with
evidence tied to source state; one optional Stop hook; a preview, install and remove
tool; an example project with a real bug; a walkthrough; tests.

Out: MCP servers, dashboards, databases, model API calls, multi-agent setups, a
dangerous-command filter, automatic edits to settings files, publishing.

## Decision log

| Date | Who | Decision | Why |
| --- | --- | --- | --- |
| 2026-10-10 | Hasitha | Build `claude-code-harness` for the agentdynarq account; local repository and commit only, no remote, push or release | Founder request; publishing needs a separate instruction |
| 2026-10-10 | Hasitha | No contributor or co-author names in commits; no em dashes | Founder instruction |
| 2026-10-10 | Claude Code session | Python 3.11+, standard library only, `unittest` | Runs anywhere Python runs; `tomllib` needs 3.11; nothing to install |
| 2026-10-10 | Claude Code session | Stop hook as the one lifecycle point | Simplest documented point that sees a finished turn and can send Claude back to work |
| 2026-10-10 | Claude Code session | Hook never exits 2; at most 2 blocks in a row by default; never twice for an unchanged source | Claude Code's own 8-continuation cap resets on every tool call, so it does not stop a fixing loop |
| 2026-10-10 | Claude Code session | Evidence keyed to a SHA-256 fingerprint of selected files plus `checks.toml` | A pass must not be reused after the source or the checks change |
| 2026-10-10 | Claude Code session | Installer only creates files (exclusive create), refuses on any conflict, records hashes, never edits settings | Smaller correct tool over a universal installer; removal can keep user edits |
| 2026-10-10 | Claude Code session | Skill named `verified-change`, not `verify` | A project `verify` skill replaces the bundled `/verify` and changes commit instructions |
| 2026-10-10 | Claude Code session | Template named `CLAUDE.template.md` | Claude Code loads `CLAUDE.md` files in subdirectories on demand |
| 2026-10-11 | Claude Code session | Live Claude Code run (category C) not attempted from inside a Claude Code session | The CLI guards against nested sessions; the procedure is scripted in `scripts/live_session_check.py` for a normal terminal |
| 2026-10-11 | Claude Code session | MIT licence, copyright "Dynarq" | Proposed default for an educational repository. Needs founder confirmation before publishing |

## Open items for the founder

1. Confirm the licence and the copyright holder name.
2. Run `python scripts/live_session_check.py --run` from a normal terminal, or say if it
   should not run (it uses the Claude Code login and counts against usage).
3. Approve publishing: repository description, visibility, first push.
