# Claude Code behaviour this kit relies on

Checked on 10 Oct 2026 against the official documentation and a local install of
Claude Code 2.1.296 (`claude --version`). Each page was fetched as Markdown
(`<url>.md`) and read directly.

| Page | URL |
| --- | --- |
| Best practices | https://code.claude.com/docs/en/best-practices |
| Memory | https://code.claude.com/docs/en/memory |
| Hooks reference | https://code.claude.com/docs/en/hooks |
| Skills | https://code.claude.com/docs/en/skills |
| Settings | https://code.claude.com/docs/en/settings |
| Permissions (for rule syntax and trust) | https://code.claude.com/docs/en/permissions |

If Claude Code changes any of the facts below, the matching part of this kit needs review.

## Stop hook

| Fact | Where it is used |
| --- | --- |
| The `Stop` event fires when the main agent finishes responding; not on user interrupt; API errors fire `StopFailure` instead | Lifecycle point for `stop_hook.py` |
| Input on stdin: common fields (`session_id`, `transcript_path`, `cwd`, `permission_mode`, `hook_event_name`) plus `stop_hook_active`, `last_assistant_message`, `background_tasks`, `session_crons` | `parse_payload` requires `hook_event_name == "Stop"` and a `session_id`, and reads `stop_hook_active`. Other fields are ignored |
| `stop_hook_active` is true when Claude is already continuing because of a Stop hook | Run of consecutive blocks resets only when it is explicitly `false` |
| Claude Code overrides a Stop block after 8 consecutive continuations; the count resets each time Claude calls a tool | Why the hook keeps its own limit (`stop_hook_max_blocks`) and its "same unchanged source" rule |
| Exit 0 with a JSON object on stdout applies its fields. `{"decision": "block", "reason": ...}` prevents stopping and gives Claude the reason | Block output |
| `systemMessage` is shown to the user | Non-blocking messages |
| `additionalContext`, `systemMessage` and plain stdout are capped at 10,000 characters each | Reason capped at 8,000 characters |
| Exit 2 is a blocking error. Any other non-zero exit without valid JSON is a non-blocking error; the action goes ahead | The hook exits 1 for malformed input and internal errors and never exits 2 |
| `onFailure` has no effect on Stop hooks | Not used |

## Hook configuration

| Fact | Where it is used |
| --- | --- |
| Hooks live in `~/.claude/settings.json`, `.claude/settings.json`, `.claude/settings.local.json`, managed settings, plugins, skill or agent frontmatter | The kit ships none of these. The snippet is merged by hand |
| Command hook fields: `type`, `command`, `args`, `timeout`, `statusMessage`, `shell`, `async`, `onFailure` | Snippet uses `type`, `command`, `args`, `timeout`, `statusMessage` |
| With `args`, the hook runs in exec form: `command` is resolved on PATH and spawned directly, no shell, on every platform. `${CLAUDE_PROJECT_DIR}` is substituted into `args` | Snippet: `"command": "python", "args": ["${CLAUDE_PROJECT_DIR}/.claude/harness/stop_hook.py"]` |
| On Windows, exec form needs a real executable, not a `.cmd` shim | `python.exe` is a real executable |
| Default command hook timeout is 600 seconds | Snippet sets 600 explicitly; runner default total is 300 |
| Matching handlers run in parallel; hooks inherit Claude Code's environment | `HARNESS_STOP_HOOK=off` works through the environment |
| `"disableAllHooks": true` turns hooks off; `--settings '{"disableAllHooks": true}'` does so for one run. No setting disables one hook while keeping it configured | Documented disable routes |
| Interactive sessions hold back settings-file hooks until the folder is trusted. `-p` and SDK sessions treat the folder as trusted | Activation note, and why `live_session_check.py` uses a temporary copy |

## Skills

| Fact | Where it is used |
| --- | --- |
| Project skills live at `.claude/skills/<name>/SKILL.md`; YAML frontmatter, `description` recommended | `verified-change` |
| `allowed-tools` grants permission for the listed tools during the turn that invokes the skill; it does not restrict other tools | Pre-approves `verify.py`, `git status`, `git diff` |
| `Bash(cmd *)` with a trailing space and `*` also matches the bare command; PowerShell rules use the same shape | Rule spelling in `allowed-tools` |
| `$ARGUMENTS` expands to the text after the skill name | `Task: $ARGUMENTS` |
| A project skill named like a bundled one replaces it. A project `verify` skill also changes Claude Code's commit instructions | The skill is named `verified-change`, not `verify` |

## Memory and settings

| Fact | Where it is used |
| --- | --- |
| Claude treats CLAUDE.md "as context, not enforced configuration" | Instructions versus enforced checks in the README |
| Project CLAUDE.md lives at `./CLAUDE.md` or `./.claude/CLAUDE.md`; CLAUDE.md files in subdirectories load on demand | The template is named `CLAUDE.template.md` so it is never loaded as instructions |
| Block HTML comments in CLAUDE.md are stripped before Claude reads it | Template notes for humans sit in a comment |
| Target under 200 lines per CLAUDE.md | Template and example stay short; a test checks it |
| `.claude/settings.local.json` is personal; `.claude/settings.json` is shared; list settings such as `permissions.allow` merge across scopes | Where to put the hook entry |
| `Edit` deny rules cover Claude's file tools and recognised Bash file commands, not arbitrary scripts; the sandbox is the OS-level control | Limits stated in the README |

## Checked in a live session

Two `claude -p` runs on Windows with Claude Code 2.1.296 (records in
[`evidence/live-session`](evidence/live-session)) confirmed, for that setup:

- The exec-form hook entry in `.claude/settings.local.json` ran, with
  `${CLAUDE_PROJECT_DIR}` substituted, and `python` resolved on PATH.
- The Stop payload parsed: `hook_event_name`, `session_id` and `stop_hook_active` as documented.
- `{"decision": "block", "reason": ...}` kept the turn going, and the reason reached
  Claude as text prefixed with "Stop hook feedback:".
- A Stop with no output and exit 0 let Claude stop.

## Still assumptions

- The same behaviour on Linux and macOS in a live session.
- The skill's `allowed-tools` rules match the commands Claude issues. The live runs also
  passed `--allowedTools`, so they do not isolate the skill's rules. Claude may spell a
  path with backslashes on Windows, which would not match and would prompt.
- `python` resolves to Python 3.11 or newer wherever Claude Code runs.
