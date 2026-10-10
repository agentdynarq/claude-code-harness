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
| 2026-10-11 | Claude Code session | Live Claude Code run (category C) not attempted from inside a Claude Code session | Assumed the CLI blocks nested sessions. Not tested at the time; corrected below |
| 2026-10-11 | Claude Code session | MIT licence, copyright "Dynarq" | Proposed default for an educational repository |
| 2026-10-11 | Hasitha | Licence confirmed: MIT, copyright "Dynarq" | Founder reply "yes dynarq" |
| 2026-10-11 | Hasitha | Run the live Claude Code check and publish to agentdynarq/claude-code-harness | Founder reply "okay run, push yourself" |
| 2026-10-11 | Claude Code session | Repository created private, not public | The auto mode classifier refused a public repository without an explicit instruction; making it public is the founder's call |
| 2026-10-11 | Claude Code session | Correction: `claude -p` does start inside a Claude Code session on 2.1.296 (tested with a 0.05 USD budget). The script's refusal was removed | The earlier assumption was never tested |
| 2026-10-11 | Claude Code session | Live runs isolated with `--setting-sources project,local --strict-mcp-config`; the stream's init and rate-limit events are not kept | Keeps personal settings, connectors and account context out of the run and the record |
| 2026-10-11 | Claude Code session | Second live scenario `regression` added | The `fix` run ended with fresh passing evidence, so the hook never had to block; the block path needed its own run |
| 2026-10-11 | Claude Code session | Hook sets `sys.dont_write_bytecode` | The first live run left `.claude/harness/__pycache__/` in the project |
| 2026-10-11 | Hasitha | Repository made public; topics set | Founder reply "make it public", after the article at hasithabandara.com/writing/build-the-harness-for-claude-code went live |

## Open items for the founder

None.
