# .claude/harness

Installed by claude-code-harness, an independent starter kit for use with Claude Code.
Nothing in this folder runs until you run it or enable the optional hook.

| File | Purpose |
| --- | --- |
| `verify.py` | Runs the checks listed in `checks.toml`, prints a summary, writes `evidence/latest.json` |
| `checks.example.toml` | Commented example. Copy it to `checks.toml` and list your real commands |
| `stop_hook.py` | Optional Claude Code Stop hook that runs `verify.py` when Claude ends a turn |
| `hook-settings.example.json` | The settings entry for that hook. Merge it by hand; the installer never edits settings |
| `templates/` | `CLAUDE.template.md`, `task-brief.md`, `handoff.md` |
| `install-manifest.json` | Files the installer added, with their hashes, so removal keeps your edits |

## Use

```
python .claude/harness/verify.py           # run the checks
python .claude/harness/verify.py status    # is the last result still valid for this source?
```

`run` exits 0 when every required check passed, 1 when one did not, 2 on a configuration
error. `status` exits 0 fresh pass, 1 fresh failure, 3 stale, 4 no evidence.

Every command in `checks.toml` runs with your user permissions. Listing a command there
authorises it to run. The file is not a sandbox.

## The optional Stop hook

To enable it, copy the `Stop` entry from `hook-settings.example.json` into
`.claude/settings.local.json` (only you) or `.claude/settings.json` (everyone who clones
the repository). Keep `timeout` above `settings.total_timeout_seconds` in `checks.toml`.
If `python` is not on your PATH, use the interpreter name that is, such as `python3`.

What it does: at the end of each Claude turn it reuses the last report if the selected
source files are unchanged, otherwise runs the checks. If a required check fails it asks
Claude to continue, at most `stop_hook_max_blocks` times in a row and never twice for the
same unchanged source.

To turn it off: delete the `Stop` entry from the settings file, start Claude Code with the
environment variable `HARNESS_STOP_HOOK=off`, or run
`claude --settings '{"disableAllHooks": true}'` for one session. Local hooks can be
edited or disabled by anyone, including Claude, who can write to this repository.

`evidence/` is created on the first run and ignores itself in git.
