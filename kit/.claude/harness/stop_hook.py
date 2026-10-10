#!/usr/bin/env python3
"""Optional Claude Code Stop hook for claude-code-harness.

When Claude finishes a turn, Claude Code sends this script the Stop payload on stdin.
The script then:

1. Reuses the latest verify.py report if the selected source files and checks.toml are
   unchanged since that report. Otherwise it runs verify.py's checks.
2. If every required check passed, it lets Claude stop.
3. If a required check did not pass, it prints {"decision": "block", "reason": ...} so
   Claude continues with the failure in view. It blocks at most
   settings.stop_hook_max_blocks times in a row (default 2) and never twice for the same
   unchanged source state. After that it lets Claude stop and tells you why.

It never exits with code 2. Malformed input or an internal error exits 1, which Claude
Code treats as a non-blocking error: Claude stops normally and you see the message.

Turn it off: delete the Stop entry from your settings file, start Claude Code with
HARNESS_STOP_HOOK=off in its environment, or run
claude --settings '{"disableAllHooks": true}' for one session.
"""

from __future__ import annotations

import sys

if sys.version_info < (3, 11):
    sys.stderr.write("claude-code-harness stop hook: Python 3.11 or newer is required; checks did not run.\n")
    raise SystemExit(1)

import io
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True  # leave no __pycache__ in the user's .claude/harness
import verify  # noqa: E402  (the runner that sits next to this file)

DISABLE_VAR = "HARNESS_STOP_HOOK"
STATE_NAME = "stop-hook-state.json"
REASON_LIMIT = 8000
TAIL_PER_CHECK = 1500
PREFIX = "claude-code-harness"


class PayloadError(ValueError):
    """The Stop payload on stdin is not usable."""


@dataclass
class HookState:
    session_id: str | None = None
    consecutive_blocks: int = 0
    notified_fingerprint: str | None = None


@dataclass
class Verification:
    overall: str
    fingerprint: str
    reused: bool
    report: dict


def parse_payload(raw: str) -> dict:
    if not raw.strip():
        raise PayloadError("stdin was empty; expected the Stop hook JSON payload")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PayloadError(f"stdin is not valid JSON ({exc.msg} at line {exc.lineno} column {exc.colno})") from None
    if not isinstance(payload, dict):
        raise PayloadError("stdin JSON must be an object")
    event = payload.get("hook_event_name")
    if event != "Stop":
        raise PayloadError(f"this hook handles the Stop event only, received hook_event_name={event!r}")
    session = payload.get("session_id")
    if not isinstance(session, str) or not session:
        raise PayloadError("session_id is missing or is not a non-empty string")
    active = payload.get("stop_hook_active")
    if active is not None and not isinstance(active, bool):
        raise PayloadError("stop_hook_active must be true or false")
    return payload


def decide(payload: dict, state: HookState, result: Verification, max_blocks: int) -> tuple[dict | None, HookState]:
    """Return (JSON output or None, new state). Pure: no I/O."""
    session = payload["session_id"]
    new = HookState(**asdict(state)) if state.session_id == session else HookState(session_id=session)
    # Reset the run of blocks only when Claude Code says this stop is not a continuation.
    # A missing field is treated as unknown, so the count keeps its value.
    if payload.get("stop_hook_active") is False:
        new.consecutive_blocks = 0

    short = result.fingerprint[:12]
    if result.overall == verify.PASSED:
        new.consecutive_blocks = 0
        new.notified_fingerprint = None
        if result.reused:
            return None, new
        return {"systemMessage": f"{PREFIX}: required checks passed for source {short}."}, new

    failing = _failing_summary(result.report)
    report_path = f"{verify.EVIDENCE_RELPATH}/{verify.REPORT_NAME}"
    if new.notified_fingerprint == result.fingerprint:
        return {"systemMessage": (
            f"{PREFIX}: required checks still not passing ({failing}). The source is unchanged "
            f"since Claude was told, so Claude was allowed to stop. Report: {report_path}"
        )}, new
    if max_blocks == 0:
        return {"systemMessage": (
            f"{PREFIX}: required checks not passing ({failing}). Blocking is off "
            f"(stop_hook_max_blocks = 0). Report: {report_path}"
        )}, new
    if new.consecutive_blocks >= max_blocks:
        return {"systemMessage": (
            f"{PREFIX}: required checks still not passing ({failing}) after {new.consecutive_blocks} "
            f"automatic retries in a row. Claude was allowed to stop so you can review. Report: {report_path}"
        )}, new
    new.consecutive_blocks += 1
    new.notified_fingerprint = result.fingerprint
    return {"decision": "block", "reason": build_reason(result, new.consecutive_blocks, max_blocks)}, new


def build_reason(result: Verification, attempt: int, max_blocks: int) -> str:
    report = result.report
    lines = [
        f"{PREFIX}: required checks did not pass, so this turn was not allowed to end "
        f"(automatic retry {attempt} of {max_blocks}).",
        f"Source state {result.fingerprint[:12]}. Full report: {verify.EVIDENCE_RELPATH}/{verify.REPORT_NAME}",
        "",
    ]
    owner_only = False
    for check in report.get("checks", []):
        if not check.get("required") or check.get("outcome") == verify.PASSED:
            continue
        label = verify.LABELS.get(check.get("outcome"), str(check.get("outcome")))
        code = f", exit code {check['exit_code']}" if check.get("exit_code") is not None else ""
        lines.append(f"{check.get('name')}: {label}{code}")
        if check.get("detail"):
            lines.append(f"  {check['detail']}")
        if check.get("outcome") in (verify.NOT_CONFIGURED, verify.SKIPPED):
            owner_only = True
        lines.extend(f"  | {line}" for line in _last_lines(check.get("output_tail") or "", TAIL_PER_CHECK))
        if check.get("log"):
            lines.append(f"  log: {check['log']}")
        lines.append("")
    lines.append(
        "If your change caused this, fix the cause and finish your turn again; the checks rerun "
        "automatically. Do not weaken tests, edit .claude/harness/checks.toml or turn off this hook "
        "to get a pass. If the failure is unrelated to your task or you cannot fix it within scope, "
        "stop and tell the user which check failed and why."
    )
    if owner_only:
        lines.append(
            "A NOT CONFIGURED or SKIPPED required check is the project owner's decision. "
            "Report it to the user instead of configuring it yourself."
        )
    reason = "\n".join(lines)
    if len(reason) > REASON_LIMIT:
        reason = reason[: REASON_LIMIT - 60] + f"\n[truncated; see {verify.EVIDENCE_RELPATH}/{verify.REPORT_NAME}]"
    return reason


def _last_lines(text: str, limit: int) -> list[str]:
    """Whole lines from the end of text, at most limit characters in total."""
    kept: list[str] = []
    size = 0
    for line in reversed(text.splitlines()):
        size += len(line) + 1
        if size > limit:
            break
        kept.append(line)
    return kept[::-1]


def _failing_summary(report: dict) -> str:
    names = [
        f"{c.get('name')} {verify.LABELS.get(c.get('outcome'), c.get('outcome'))}"
        for c in report.get("checks", [])
        if c.get("required") and c.get("outcome") != verify.PASSED
    ]
    return ", ".join(names) or "no required check passed"


def obtain_verification(root: Path, config: verify.Config) -> Verification:
    current = verify.compute_source_state(root, config)
    report = verify.load_report(root)
    if report is not None and report["source_state"].get("fingerprint") == current["fingerprint"]:
        return Verification(report["overall"], current["fingerprint"], True, report)
    report = verify.run_checks(root, config, source_state=current)
    return Verification(report["overall"], report["source_state"]["fingerprint"], False, report)


def load_state(path: Path) -> HookState:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return HookState(
            session_id=data.get("session_id") if isinstance(data.get("session_id"), str) else None,
            consecutive_blocks=int(data.get("consecutive_blocks", 0)),
            notified_fingerprint=data.get("notified_fingerprint") if isinstance(data.get("notified_fingerprint"), str) else None,
        )
    except (OSError, ValueError, TypeError, AttributeError):
        return HookState()


def save_state(path: Path, state: HookState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(asdict(state), indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def run(stdin, stdout, stderr, environ) -> int:
    if environ.get(DISABLE_VAR, "").strip().lower() in {"off", "0", "false", "no", "disabled"}:
        return 0
    try:
        payload = parse_payload(stdin.read())
    except PayloadError as exc:
        print(f"{PREFIX} stop hook: {exc}", file=stderr)
        return 1

    root = HERE.parents[1]
    config_path = root / verify.CONFIG_RELPATH
    if not config_path.is_file():
        _emit(stdout, {"systemMessage": (
            f"{PREFIX}: checks did not run because {verify.CONFIG_RELPATH} does not exist. Create it "
            f"from checks.example.toml, or remove the Stop hook from your settings."
        )})
        return 0
    try:
        config = verify.load_config(config_path)
    except verify.ConfigError as exc:
        _emit(stdout, {"systemMessage": f"{PREFIX}: checks did not run because checks.toml is invalid: {exc}"})
        return 0

    result = obtain_verification(root, config)
    state_path = root / verify.EVIDENCE_RELPATH / STATE_NAME
    output, new_state = decide(payload, load_state(state_path), result, config.stop_hook_max_blocks)
    save_state(state_path, new_state)
    if output is not None:
        _emit(stdout, output)
    return 0


def _emit(stdout, data: dict) -> None:
    stdout.write(json.dumps(data))
    stdout.flush()


def main() -> int:
    # Claude Code sends UTF-8. On Windows the default stdin encoding is the console code page.
    stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(errors="replace")
    try:
        return run(stdin, sys.stdout, sys.stderr, os.environ)
    except Exception as exc:  # never exit 2 by accident: 2 would block the stop
        print(f"{PREFIX} stop hook: internal error: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
