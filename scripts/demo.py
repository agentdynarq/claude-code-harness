#!/usr/bin/env python3
"""Walk through the invoice-totals example in a temporary directory.

Copies the example, installs the kit, shows the task, then runs the real checks:
fail, fix, pass, evidence fresh, reintroduce the bug, evidence stale, fail again.
Finally it feeds the Stop hook fixture payloads. Nothing in this repository changes.

    python scripts/demo.py          run, then delete the temporary project
    python scripts/demo.py --keep   leave the temporary project for inspection

Exits 0 only if every step produced the expected outcome.
"""

from __future__ import annotations

import argparse
import difflib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "invoice-totals"
TOTALS = "invoice_totals/totals.py"

# The fix the task brief asks for, as exact text replacements on totals.py.
FIX = [
    ("from decimal import Decimal\n", "from decimal import ROUND_HALF_UP, Decimal\n"),
    ("    vat = sum((round(amount * rate, 2) for rate, amount in net_by_rate.items()), Decimal(\"0\"))\n",
     "    vat = sum(\n"
     "        ((amount * rate).quantize(CENT, rounding=ROUND_HALF_UP) for rate, amount in net_by_rate.items()),\n"
     "        Decimal(\"0\"),\n"
     "    )\n"),
]

STOP_PAYLOAD = {
    "session_id": "demo-session",
    "transcript_path": "fixture-only",
    "cwd": "fixture-only",
    "permission_mode": "default",
    "hook_event_name": "Stop",
    "stop_hook_active": False,
    "last_assistant_message": "Fixture message written by scripts/demo.py.",
}


class Demo:
    def __init__(self, project: Path):
        self.project = project
        self.expectations = 0
        self.failures: list[str] = []
        self.step_no = 0

    def step(self, title: str) -> None:
        self.step_no += 1
        print(f"\n== {self.step_no}. {title}")

    def clean(self, text: str) -> str:
        replacements = [(str(self.project), "<project>"), (str(REPO), "<repo>"), (sys.executable, "<python>"),
                        (str(Path.home()), "~")]
        for old, new in replacements:
            text = text.replace(old, new)
        return text

    def run(self, args: list[str], *, stdin: str | None = None, json_stdout: bool = False) -> subprocess.CompletedProcess:
        shown = " ".join(self.clean(a) if " " not in a else f'"{self.clean(a)}"' for a in args)
        print(f"$ {shown}" + ("   (stdin: fixture payload)" if stdin is not None else ""))
        proc = subprocess.run(args, cwd=self.project, input=stdin, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=300)
        if json_stdout and proc.stdout.strip().startswith("{"):
            print("stdout JSON, one field per block:")
            for key, value in json.loads(proc.stdout).items():
                print(f"  {key}:")
                print("\n".join(f"    {line}" for line in self.clean(str(value)).splitlines()))
        elif proc.stdout.strip():
            print(self.clean(proc.stdout.rstrip()))
        if proc.stderr.strip():
            print(self.clean(proc.stderr.rstrip()))
        print(f"[exit {proc.returncode}]")
        return proc

    def expect(self, condition: bool, description: str) -> None:
        self.expectations += 1
        mark = "ok" if condition else "EXPECTATION FAILED"
        print(f"   {mark}: {description}")
        if not condition:
            self.failures.append(description)

    def verify(self, *extra: str) -> subprocess.CompletedProcess:
        return self.run([sys.executable, str(self.project / ".claude/harness/verify.py"), *extra])

    def hook(self, payload: str) -> subprocess.CompletedProcess:
        return self.run([sys.executable, str(self.project / ".claude/harness/stop_hook.py")],
                        stdin=payload, json_stdout=True)

    def edit_totals(self, forward: bool) -> str:
        path = self.project / TOTALS
        before = path.read_text(encoding="utf-8")
        after = before
        for old, new in FIX:
            old, new = (old, new) if forward else (new, old)
            if after.count(old) != 1:
                raise SystemExit(f"demo: expected exactly one match in {TOTALS} for {old!r}")
            after = after.replace(old, new)
        path.write_text(after, encoding="utf-8", newline="\n")
        return "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                            f"a/{TOTALS}", f"b/{TOTALS}"))


def section(text: str, heading: str) -> str:
    lines = text.splitlines()
    start = lines.index(heading) + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    return "\n".join(lines[start:end]).strip()


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--keep", action="store_true", help="keep the temporary project")
    args = parser.parse_args()

    workspace = Path(tempfile.mkdtemp(prefix="cch-demo-"))
    project = workspace / "invoice project with spaces"
    demo = Demo(project)
    try:
        print(f"claude-code-harness demo. Python {sys.version.split()[0]} on {sys.platform}.")
        print("Every command below really runs. <project> is a temporary copy of examples/invoice-totals.")

        demo.step("Copy the example project to a temporary directory")
        shutil.copytree(EXAMPLE, project, ignore=shutil.ignore_patterns("__pycache__"))
        for path in sorted(p for p in project.rglob("*") if p.is_file()):
            print(f"   {path.relative_to(project).as_posix()}")
        own_files = {p: p.read_bytes() for p in (project / "CLAUDE.md", project / ".claude/harness/checks.toml")}

        demo.step("Preview the kit installation, then install")
        preview = demo.run([sys.executable, str(REPO / "install.py"), "install", str(project), "--dry-run"])
        demo.expect(preview.returncode == 0 and "Dry run: nothing was written." in preview.stdout,
                    "dry run exits 0 and writes nothing")
        demo.expect(not (project / ".claude/harness/verify.py").exists(), "verify.py is absent after the dry run")
        result = demo.run([sys.executable, str(REPO / "install.py"), "install", str(project)])
        demo.expect(result.returncode == 0, "install exits 0")
        demo.expect(all(p.read_bytes() == data for p, data in own_files.items()),
                    "the project's own CLAUDE.md and checks.toml are byte-for-byte unchanged")

        demo.step("The task and its acceptance criteria (docs/tasks/fix-vat-rounding.md)")
        brief = (project / "docs/tasks/fix-vat-rounding.md").read_text(encoding="utf-8")
        print(section(brief, "## Objective"))
        print()
        print(section(brief, "## Acceptance criteria"))

        demo.step("Run the required checks before changing anything")
        first = demo.verify()
        demo.expect(first.returncode == 1, "verify exits 1 because a required check failed")
        demo.expect("AssertionError: Decimal('0.28') != Decimal('0.29')" in first.stdout,
                    "the failure is the half-cent rounding bug")

        demo.step("Apply the fix the brief asks for")
        print(demo.edit_totals(forward=True).rstrip())

        demo.step("Run the checks again")
        second = demo.verify()
        demo.expect(second.returncode == 0 and "RESULT   PASSED" in second.stdout, "verify exits 0 and reports PASSED")

        demo.step("Ask whether that evidence still applies to the current source")
        fresh = demo.verify("status")
        demo.expect(fresh.returncode == 0 and "evidence  FRESH" in fresh.stdout, "status reports FRESH (exit 0)")

        demo.step("Change a file outside the configured source (CLAUDE.md)")
        with open(project / "CLAUDE.md", "a", encoding="utf-8", newline="\n") as handle:
            handle.write("\n<!-- demo edit -->\n")
        still = demo.verify("status")
        demo.expect(still.returncode == 0, "status is still FRESH: CLAUDE.md is not in [source] include")

        demo.step("Deliberately reintroduce the bug")
        print(demo.edit_totals(forward=False).rstrip())
        stale = demo.verify("status")
        demo.expect(stale.returncode == 3 and f"modified  {TOTALS}" in stale.stdout,
                    "status reports STALE (exit 3) and names the changed file; the earlier pass no longer counts")

        demo.step("Run the checks on the reintroduced bug")
        third = demo.verify()
        demo.expect(third.returncode == 1 and "RESULT   FAILED" in third.stdout,
                    "verify fails again (exit 1): the test catches the regression")

        demo.step("Stop hook with fixture payloads (written by this script, not by Claude Code)")
        block = demo.hook(json.dumps(STOP_PAYLOAD))
        decision = json.loads(block.stdout) if block.stdout.strip().startswith("{") else {}
        demo.expect(block.returncode == 0 and decision.get("decision") == "block"
                    and "tests: FAILED" in decision.get("reason", ""),
                    "first stop: exit 0 with decision=block and the failing check in the reason")
        again = demo.hook(json.dumps({**STOP_PAYLOAD, "stop_hook_active": True}))
        output = json.loads(again.stdout) if again.stdout.strip().startswith("{") else {}
        demo.expect(again.returncode == 0 and "decision" not in output and "unchanged" in output.get("systemMessage", ""),
                    "second stop with no source change: not blocked again, user is told why")
        bad = demo.hook("{not json")
        demo.expect(bad.returncode == 1 and not bad.stdout.strip(),
                    "malformed payload: exit 1 (non-blocking error), nothing on stdout")
    finally:
        if args.keep:
            print(f"\nKept the temporary project at {project}")
        else:
            shutil.rmtree(workspace, ignore_errors=True)

    print()
    if demo.failures:
        print(f"{len(demo.failures)} of {demo.expectations} expectations failed:")
        for failure in demo.failures:
            print(f"  - {failure}")
        return 1
    print(f"All {demo.expectations} expectations met.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
