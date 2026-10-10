#!/usr/bin/env python3
"""Category C: run the example in a real Claude Code session and keep a record.

Sets up a temporary copy of examples/invoice-totals with the kit installed and the Stop
hook enabled in that copy's .claude/settings.local.json, then runs claude -p there.

Scenarios:
  fix         "/verified-change docs/tasks/fix-vat-rounding.md" on the buggy example.
  regression  starts from the fixed code and asks for a change that breaks the tests,
              without running anything, so the Stop hook has to send Claude back.

This uses your own Claude Code login and counts against your usage or API budget.
Only the temporary project's settings load (--setting-sources project,local) and no MCP
servers (--strict-mcp-config), so your personal settings and connectors stay out of the run.

    python scripts/live_session_check.py --dry-run [--scenario S]   set up, print the command
    python scripts/live_session_check.py --run [--scenario S]       run it, write a sanitised record

The record (record.md and the stream without its init and rate-limit events, paths
replaced) goes to --out, default docs/evidence/live-session/<scenario>/. Read it before
committing it. Nothing outside the temporary project is changed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

from demo import FIX

REPO = Path(__file__).resolve().parents[1]
PROMPTS = {
    "fix": "/verified-change docs/tasks/fix-vat-rounding.md",
    "regression": ("In invoice_totals/totals.py, change the VAT rounding mode from ROUND_HALF_UP to "
                   "ROUND_HALF_EVEN. Make only that edit. Do not run tests or any other command."),
}
ALLOWED = ["Bash(python -m unittest *)", "Bash(python .claude/harness/verify.py *)", "Bash(git diff *)",
           "Bash(git status *)", "PowerShell(python -m unittest *)", "PowerShell(python .claude/harness/verify.py *)",
           "PowerShell(git diff *)", "PowerShell(git status *)"]
DROPPED_EVENTS = {("system", "init"), ("rate_limit_event", None)}  # local tools, servers, skills; account usage


def remove_tree(path: Path) -> None:
    """Delete a folder, including git's read-only object files on Windows."""
    def retry(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=retry)
    else:
        shutil.rmtree(path, onerror=retry)


def sh(args: list[str], cwd: Path, timeout: float = 120) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def prepare(project: Path, scenario: str) -> None:
    shutil.copytree(REPO / "examples" / "invoice-totals", project, ignore=shutil.ignore_patterns("__pycache__"))
    message = "example before the task"
    if scenario == "regression":
        totals = project / "invoice_totals" / "totals.py"
        text = totals.read_text(encoding="utf-8")
        for old, new in FIX:
            text = text.replace(old, new)
        totals.write_text(text, encoding="utf-8", newline="\n")
        message = "example with the rounding fix applied"
    ident = ["-c", "user.name=harness-live-check", "-c", "user.email=live-check@example.invalid"]
    for args in (["git", "init", "-q"], ["git", "add", "-A"], ["git", *ident, "commit", "-q", "-m", message]):
        result = sh(args, project)
        if result.returncode:
            raise SystemExit(f"setup failed: {' '.join(args)}\n{result.stderr}")
    installed = sh([sys.executable, str(REPO / "install.py"), "install", str(project)], REPO)
    if installed.returncode:
        raise SystemExit(f"install failed:\n{installed.stdout}{installed.stderr}")
    snippet = json.loads((project / ".claude/harness/hook-settings.example.json").read_text(encoding="utf-8"))
    (project / ".claude/settings.local.json").write_text(json.dumps(snippet, indent=2) + "\n", encoding="utf-8")


def claude_command(project: Path, scenario: str, model: str | None) -> list[str]:
    command = ["claude", "-p", PROMPTS[scenario], "--permission-mode", "acceptEdits", "--output-format",
               "stream-json", "--verbose", "--max-budget-usd", "3", "--no-session-persistence",
               "--setting-sources", "project,local", "--strict-mcp-config",
               "--debug-file", str(project.parent / "claude-debug.log"), "--allowedTools", *ALLOWED]
    return command + (["--model", model] if model else [])


def sanitise(text: str, project: Path) -> str:
    """Replace the project and home paths in every spelling, then any leftover user name."""
    home = Path.home()
    for path, label in ((project, "<project>"), (home, "~")):
        native = str(path)
        variants = {native, native.replace("\\", "\\\\"), native.replace("\\", "/")}
        if re.match(r"^[A-Za-z]:", native):
            variants.add("/" + native[0].lower() + native[2:].replace("\\", "/"))
        for variant in sorted(variants, key=len, reverse=True):
            text = re.sub(re.escape(variant), label.replace("\\", r"\\"), text, flags=re.IGNORECASE)
    if len(home.name) >= 3:
        text = re.sub(re.escape(home.name), "<user>", text, flags=re.IGNORECASE)
    return text


def events(raw: str):
    for line in raw.splitlines():
        try:
            yield line, json.loads(line)
        except ValueError:
            continue


def public_stream(raw: str) -> str:
    return "".join(line + "\n" for line, event in events(raw)
                   if (event.get("type"), event.get("subtype")) not in DROPPED_EVENTS)


def summarise_stream(raw: str) -> tuple[list[str], list[str], dict, str]:
    """Tool calls, other user-turn text (hook feedback), the result event and the model."""
    calls, feedback, result, model = [], [], {}, ""
    for _, event in events(raw):
        kind = event.get("type")
        if kind == "system" and event.get("subtype") == "init":
            model = str(event.get("model", ""))
        elif kind == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    data = block.get("input", {})
                    calls.append(f"{block.get('name')}: {data.get('command') or data.get('file_path') or data.get('skill') or ''}")
        elif kind == "user":
            content = event.get("message", {}).get("content", [])
            texts = [content] if isinstance(content, str) else [
                b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
            feedback += [t[:1500] for t in texts if t.strip()]
        elif kind == "system" and "hook" in str(event.get("subtype", "")):
            feedback.append(json.dumps(event)[:1500])
        elif kind == "result":
            result = event
    return calls, feedback, result, model


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--scenario", choices=sorted(PROMPTS), default="fix")
    parser.add_argument("--model")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    out = args.out or REPO / "docs" / "evidence" / "live-session" / args.scenario

    workspace = Path(tempfile.mkdtemp(prefix="cch-live-"))
    project = workspace / "invoice-totals"
    try:
        prepare(project, args.scenario)
        command = claude_command(project, args.scenario, args.model)
        print(f"Prepared {sanitise(str(project), project)} for scenario {args.scenario!r}; Stop hook enabled there.")
        shown = subprocess.list2cmdline(command) if os.name == "nt" else " ".join(command)
        print("Command:\n  " + sanitise(shown, project))
        if args.dry_run:
            return 0
        if shutil.which("claude") is None:
            print("claude is not on PATH.", file=sys.stderr)
            return 2
        version = sh(["claude", "--version"], project).stdout.strip()
        session = subprocess.run(command, cwd=project, stdin=subprocess.DEVNULL, capture_output=True,
                                 text=True, encoding="utf-8", errors="replace", timeout=1800)
        status = sh([sys.executable, ".claude/harness/verify.py", "status", "--json"], project)
        diff = sh(["git", "diff", "--stat"], project).stdout + "\n" + sh(["git", "diff"], project).stdout
        untracked = sh(["git", "status", "--short"], project).stdout
        debug = workspace / "claude-debug.log"
        hook_lines = [line for line in debug.read_text(encoding="utf-8", errors="replace").splitlines()
                      if "Hooks: Stop" in line] if debug.exists() else []
        state = project / ".claude/harness/evidence/stop-hook-state.json"
        calls, feedback, result, model = summarise_stream(session.stdout)
        summary = {k: result.get(k) for k in ("subtype", "is_error", "num_turns", "duration_ms", "total_cost_usd")}

        out.mkdir(parents=True, exist_ok=True)
        (out / "stream.jsonl").write_text(sanitise(public_stream(session.stdout), project), encoding="utf-8",
                                          newline="\n")
        record = [
            f"# Live Claude Code session record: {args.scenario}, {date.today().isoformat()}", "",
            "Written by scripts/live_session_check.py. Paths are replaced with <project>, ~ and <user>.", "",
            f"- Claude Code: {version}", f"- Model: {model or 'unknown'}", f"- Prompt: `{PROMPTS[args.scenario]}`",
            f"- Exit code: {session.returncode}", f"- Result: `{json.dumps(summary)}`",
            f"- Permission denials: {len(result.get('permission_denials') or [])}",
            "", "## Tool calls", *[f"- `{c}`" for c in calls],
            "", "## Text that reached Claude as a user turn (the prompt and any hook feedback)",
            *[f"```\n{t}\n```" for t in feedback],
            "", "## Stop hook runs in the debug log", *([f"    {line}" for line in hook_lines] or ["None found."]),
            "", "## Stop hook state at the end", "```", state.read_text(encoding="utf-8") if state.exists() else "missing", "```",
            "", "## verify.py status after the session", "```", status.stdout, "```",
            "", "## Changes", "```", untracked + "\n" + diff, "```",
            "", "## Final message", str(result.get("result", "")),
        ]
        (out / "record.md").write_text(sanitise("\n".join(record) + "\n", project), encoding="utf-8", newline="\n")
        print(f"Record written to {sanitise(str(out / 'record.md'), project)}. Read it before sharing it.")
        return 0
    finally:
        if args.keep:
            print(f"Kept {workspace}")
        else:
            remove_tree(workspace)


if __name__ == "__main__":
    sys.exit(main())
