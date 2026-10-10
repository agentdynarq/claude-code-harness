#!/usr/bin/env python3
"""Category C: run the example task in a real Claude Code session and keep a record.

Sets up a temporary copy of examples/invoice-totals with the kit installed and the Stop
hook enabled in that copy's .claude/settings.local.json, then runs:

    claude -p "/verified-change docs/tasks/fix-vat-rounding.md" ...

This uses your own Claude Code login and counts against your usage or API budget.
Run it from a normal terminal, not from inside a Claude Code session.

    python scripts/live_session_check.py --dry-run           set up and print the command only
    python scripts/live_session_check.py --run [--model M]   run it and write a sanitised record

The record (record.md, plus the raw stream with paths replaced) goes to --out,
default docs/evidence/live-session/. Nothing outside the temporary project is changed.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROMPT = "/verified-change docs/tasks/fix-vat-rounding.md"
ALLOWED = ["Bash(python -m unittest *)", "Bash(python .claude/harness/verify.py *)", "Bash(git diff *)",
           "Bash(git status *)", "PowerShell(python -m unittest *)", "PowerShell(python .claude/harness/verify.py *)",
           "PowerShell(git diff *)", "PowerShell(git status *)"]


def sh(args: list[str], cwd: Path, timeout: float = 120) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def prepare(project: Path) -> None:
    shutil.copytree(REPO / "examples" / "invoice-totals", project, ignore=shutil.ignore_patterns("__pycache__"))
    ident = ["-c", "user.name=harness-live-check", "-c", "user.email=live-check@example.invalid"]
    for args in (["git", "init", "-q"], ["git", "add", "-A"], ["git", *ident, "commit", "-q", "-m", "example before the task"]):
        result = sh(args, project)
        if result.returncode:
            raise SystemExit(f"setup failed: {' '.join(args)}\n{result.stderr}")
    installed = sh([sys.executable, str(REPO / "install.py"), "install", str(project)], REPO)
    if installed.returncode:
        raise SystemExit(f"install failed:\n{installed.stdout}{installed.stderr}")
    snippet = json.loads((project / ".claude/harness/hook-settings.example.json").read_text(encoding="utf-8"))
    (project / ".claude/settings.local.json").write_text(json.dumps(snippet, indent=2) + "\n", encoding="utf-8")


def claude_command(project: Path, model: str | None) -> list[str]:
    command = ["claude", "-p", PROMPT, "--permission-mode", "acceptEdits", "--output-format", "stream-json",
               "--verbose", "--max-budget-usd", "3", "--no-session-persistence",
               "--debug-file", str(project.parent / "claude-debug.log"), "--allowedTools", *ALLOWED]
    return command + (["--model", model] if model else [])


def sanitise(text: str, project: Path) -> str:
    for old, new in ((str(project), "<project>"), (str(project).replace("\\", "\\\\"), "<project>"),
                     (str(Path.home()), "~"), (str(Path.home()).replace("\\", "\\\\"), "~")):
        text = text.replace(old, new)
    return text


def summarise_stream(raw: str) -> tuple[list[str], dict]:
    """Tool calls and the final result. The init event is skipped: it lists account context."""
    calls, result = [], {}
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    data = block.get("input", {})
                    calls.append(f"{block.get('name')}: {data.get('command') or data.get('file_path') or data.get('skill') or ''}")
        elif event.get("type") == "system" and "hook" in str(event.get("subtype", "")):
            calls.append(f"[system {event.get('subtype')}] {json.dumps(event)[:300]}")
        elif event.get("type") == "result":
            result = {k: event.get(k) for k in ("subtype", "is_error", "num_turns", "duration_ms", "result")}
    return calls, result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--model")
    parser.add_argument("--out", type=Path, default=REPO / "docs" / "evidence" / "live-session")
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()

    if os.environ.get("CLAUDECODE") and args.run:
        print("Refusing to start: this terminal is inside a Claude Code session (CLAUDECODE is set). "
              "Run the script from a normal terminal.", file=sys.stderr)
        return 2
    workspace = Path(tempfile.mkdtemp(prefix="cch-live-"))
    project = workspace / "invoice-totals"
    try:
        prepare(project)
        command = claude_command(project, args.model)
        print(f"Prepared {project}\nHook enabled in {project / '.claude/settings.local.json'}")
        shown = subprocess.list2cmdline(command) if os.name == "nt" else " ".join(command)
        print("Command:\n  " + sanitise(shown, project))
        if args.dry_run:
            return 0
        if shutil.which("claude") is None:
            print("claude is not on PATH.", file=sys.stderr)
            return 2
        version = sh(["claude", "--version"], project).stdout.strip()
        session = subprocess.run(command, cwd=project, capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", timeout=1800)
        status = sh([sys.executable, ".claude/harness/verify.py", "status", "--json"], project)
        diff = sh(["git", "diff", "--stat"], project).stdout + "\n" + sh(["git", "diff"], project).stdout
        untracked = sh(["git", "status", "--short"], project).stdout
        debug = workspace / "claude-debug.log"
        hook_lines = [line for line in debug.read_text(encoding="utf-8", errors="replace").splitlines()
                      if "Stop" in line and "Hook" in line] if debug.exists() else []
        state = project / ".claude/harness/evidence/stop-hook-state.json"
        calls, result = summarise_stream(session.stdout)

        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "stream.jsonl").write_text(sanitise(session.stdout, project), encoding="utf-8")
        record = [
            f"# Live Claude Code session record, {date.today().isoformat()}", "",
            f"- Claude Code: {version}", f"- Prompt: `{PROMPT}`", f"- Model flag: {args.model or 'default'}",
            f"- Exit code: {session.returncode}", f"- Result: `{json.dumps({k: v for k, v in result.items() if k != 'result'})}`",
            "", "## Tool calls", *[f"- `{sanitise(c, project)}`" for c in calls],
            "", "## Stop hook lines from the debug log",
            *([f"    {sanitise(line, project)}" for line in hook_lines[:40]] or ["None found."]),
            "", "## Stop hook state at the end", "```", state.read_text(encoding="utf-8") if state.exists() else "missing", "```",
            "", "## verify.py status after the session", "```", sanitise(status.stdout, project), "```",
            "", "## Changes", "```", sanitise(untracked + "\n" + diff, project), "```",
            "", "## Final message", sanitise(str(result.get("result", "")), project),
        ]
        (args.out / "record.md").write_text("\n".join(record) + "\n", encoding="utf-8")
        print(f"Record written to {args.out / 'record.md'}. Read it before sharing it.")
        return 0
    finally:
        if args.keep:
            print(f"Kept {workspace}")
        else:
            shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
