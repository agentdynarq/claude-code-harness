#!/usr/bin/env python3
"""Run a project's configured checks and record evidence tied to its source state.

Part of claude-code-harness, an independent starter kit for use with Claude Code.
Standard library only. Python 3.11 or newer.

Configuring a command in checks.toml authorises this script to execute it with
your user permissions. The configuration is not a sandbox.

Usage:
    python .claude/harness/verify.py           run the checks, print a summary, write a report
    python .claude/harness/verify.py status    compare the last report with the current source

Exit codes for "run":    0 every required check passed, 1 a required check did not pass,
                         2 configuration or usage error.
Exit codes for "status": 0 fresh evidence of a pass, 1 fresh evidence of a failure,
                         3 stale evidence, 4 no evidence, 2 configuration or usage error.
"""

from __future__ import annotations

import sys

if sys.version_info < (3, 11):
    sys.stderr.write("verify.py needs Python 3.11 or newer (it uses tomllib).\n")
    raise SystemExit(2)

import argparse
import fnmatch
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
import tomllib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.1.0"
REPORT_SCHEMA = "claude-code-harness/verify-report/1"
FINGERPRINT_SCHEME = "claude-code-harness/source-state/1"

CONFIG_RELPATH = ".claude/harness/checks.toml"
EVIDENCE_RELPATH = ".claude/harness/evidence"
REPORT_NAME = "latest.json"
PYTHON_TOKEN = "{python}"

PASSED = "passed"
FAILED = "failed"
TIMEOUT = "timeout"
SKIPPED = "skipped"
NOT_CONFIGURED = "not_configured"
LABELS = {
    PASSED: "PASSED",
    FAILED: "FAILED",
    TIMEOUT: "TIMEOUT",
    SKIPPED: "SKIPPED",
    NOT_CONFIGURED: "NOT CONFIGURED",
}

DEFAULT_TOTAL_TIMEOUT = 300.0
DEFAULT_CHECK_TIMEOUT = 120.0
DEFAULT_STOP_HOOK_MAX_BLOCKS = 2
LOG_MAX_BYTES = 256 * 1024
TAIL_LINES = 40
TAIL_CHARS = 4000

# Never hashed, whatever the include patterns say. Keeps the walk fast and
# keeps tool caches and the evidence itself out of the source state.
ALWAYS_EXCLUDED_DIRS = frozenset(
    {".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv",
     ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
)

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
SECRET_NAME_RE = re.compile(
    r"TOKEN|SECRET|PASSWORD|PASSWD|PASSPHRASE|CREDENTIAL|API_?KEY|ACCESS_?KEY|PRIVATE_?KEY|(^|_)KEY$",
    re.IGNORECASE,
)

DEFAULT_ROOT = Path(__file__).resolve().parents[2]


class ConfigError(Exception):
    """The checks configuration is missing or invalid."""


@dataclass(frozen=True)
class Check:
    name: str
    command: tuple[str, ...] | None
    cwd: str
    timeout: float
    enabled: bool
    reason: str | None


@dataclass(frozen=True)
class Config:
    path: Path
    sha256: str
    required: tuple[str, ...]
    checks: tuple[Check, ...]
    total_timeout: float
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    stop_hook_max_blocks: int


@dataclass
class CheckResult:
    name: str
    required: bool
    outcome: str
    command: list[str] | None = None
    executable: str | None = None
    cwd: str | None = None
    exit_code: int | None = None
    duration_seconds: float | None = None
    timeout_seconds: float | None = None
    detail: str | None = None
    log: str | None = None
    output_tail: str | None = None


# ---------------------------------------------------------------- configuration


def load_config(path: Path) -> Config:
    path = Path(path)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raise ConfigError(f"no checks configuration at {path}") from None
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from None
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except UnicodeDecodeError:
        raise ConfigError(f"{path.name} is not UTF-8 text") from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path.name} is not valid TOML: {exc}") from None

    _reject_unknown(data, {"required", "settings", "source", "checks"}, "top level")

    required = data.get("required")
    if not isinstance(required, list) or not required or not all(isinstance(n, str) for n in required):
        raise ConfigError('"required" must be a non-empty list of check names, for example required = ["tests"]')
    for name in required:
        _check_name(name)
    if len(set(required)) != len(required):
        raise ConfigError('"required" lists the same check more than once')

    settings = _table(data, "settings")
    _reject_unknown(settings, {"total_timeout_seconds", "default_timeout_seconds", "stop_hook_max_blocks"}, "[settings]")
    total_timeout = _positive(settings.get("total_timeout_seconds", DEFAULT_TOTAL_TIMEOUT), "settings.total_timeout_seconds")
    default_timeout = _positive(settings.get("default_timeout_seconds", DEFAULT_CHECK_TIMEOUT), "settings.default_timeout_seconds")
    max_blocks = settings.get("stop_hook_max_blocks", DEFAULT_STOP_HOOK_MAX_BLOCKS)
    if not isinstance(max_blocks, int) or isinstance(max_blocks, bool) or not 0 <= max_blocks <= 5:
        raise ConfigError("settings.stop_hook_max_blocks must be a whole number from 0 to 5")

    source = _table(data, "source")
    _reject_unknown(source, {"include", "exclude"}, "[source]")
    include = _patterns(source.get("include", ["*"]), "source.include")
    if not include:
        raise ConfigError("source.include must name at least one pattern")
    exclude = _patterns(source.get("exclude", []), "source.exclude")

    checks = []
    for name, spec in _table(data, "checks").items():
        _check_name(name)
        if not isinstance(spec, dict):
            raise ConfigError(f"checks.{name} must be a table, for example [checks.{name}]")
        _reject_unknown(spec, {"command", "cwd", "timeout_seconds", "enabled", "reason"}, f"[checks.{name}]")
        command = spec.get("command")
        if command is not None:
            if isinstance(command, str):
                raise ConfigError(
                    f'checks.{name}.command must be a list of arguments, not a shell string. '
                    f'Write ["npm", "test"] instead of "npm test". If you need a shell, '
                    f'call it explicitly, for example ["bash", "-c", "..."].'
                )
            if (not isinstance(command, list) or not command
                    or not all(isinstance(a, str) for a in command) or not command[0]):
                raise ConfigError(f"checks.{name}.command must be a non-empty list of strings")
            command = tuple(command)
        cwd = spec.get("cwd", ".")
        if not isinstance(cwd, str) or not cwd or Path(cwd).is_absolute() or Path(cwd).drive:
            raise ConfigError(f"checks.{name}.cwd must be a path relative to the project root")
        enabled = spec.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ConfigError(f"checks.{name}.enabled must be true or false")
        reason = spec.get("reason")
        if reason is not None and not isinstance(reason, str):
            raise ConfigError(f"checks.{name}.reason must be text")
        timeout = _positive(spec.get("timeout_seconds", default_timeout), f"checks.{name}.timeout_seconds")
        checks.append(Check(name, command, cwd, timeout, enabled, reason))

    return Config(
        path=path,
        sha256=hashlib.sha256(raw).hexdigest(),
        required=tuple(required),
        checks=tuple(checks),
        total_timeout=total_timeout,
        include=include,
        exclude=exclude,
        stop_hook_max_blocks=max_blocks,
    )


def _reject_unknown(table: dict, allowed: set[str], where: str) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise ConfigError(f"unknown key(s) at {where}: {', '.join(unknown)}. Allowed: {', '.join(sorted(allowed))}")


def _table(data: dict, key: str) -> dict:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ConfigError(f"{key} must be a table")
    return value


def _check_name(name: str) -> None:
    if not NAME_RE.match(name):
        raise ConfigError(f"check name {name!r} must use letters, digits, '.', '_' or '-' and start with a letter or digit")


def _positive(value, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ConfigError(f"{where} must be a positive number of seconds")
    return float(value)


def _patterns(value, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(p, str) and p for p in value):
        raise ConfigError(f"{where} must be a list of patterns, for example [\"src/*\"]")
    return tuple(value)


# ---------------------------------------------------------------- source state


def compute_source_state(root: Path, config: Config) -> dict:
    """Hash every selected file under root. The fingerprint also covers the config."""
    root = Path(root).resolve()
    evidence = root / EVIDENCE_RELPATH
    files: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        dirnames[:] = sorted(
            d for d in dirnames if d not in ALWAYS_EXCLUDED_DIRS and current / d != evidence
        )
        for filename in filenames:
            rel = (current / filename).relative_to(root).as_posix()
            if _selected(rel, config.include, config.exclude):
                files[rel] = _hash_file(current / filename)
    digest = hashlib.sha256()
    digest.update(f"{FINGERPRINT_SCHEME}\nconfig {config.sha256}\n".encode())
    for rel in sorted(files):
        digest.update(f"{rel}\0{files[rel]}\n".encode("utf-8"))
    return {
        "fingerprint": digest.hexdigest(),
        "file_count": len(files),
        "files": dict(sorted(files.items())),
    }


def _selected(rel: str, include: tuple[str, ...], exclude: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatchcase(rel, p) for p in include) and not any(
        fnmatch.fnmatchcase(rel, p) for p in exclude
    )


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    except OSError as exc:
        return f"unreadable:{exc.__class__.__name__}"
    return digest.hexdigest()


def diff_source_states(recorded: dict, current: dict) -> dict:
    old, new = recorded.get("files", {}), current.get("files", {})
    return {
        "added": sorted(set(new) - set(old)),
        "removed": sorted(set(old) - set(new)),
        "modified": sorted(p for p in set(old) & set(new) if old[p] != new[p]),
    }


# ---------------------------------------------------------------- running checks


def make_redactor(environ) -> callable:
    """Replace values of secret-looking environment variables if they appear in text.

    This only catches secrets that are present, verbatim, in the environment of this
    process. It is a last line of defence for logs, not a guarantee.
    """
    secrets = sorted(
        {(value, name) for name, value in environ.items()
         if SECRET_NAME_RE.search(name) and len(value) >= 8},
        key=lambda item: len(item[0]),
        reverse=True,
    )

    def redact(text: str) -> str:
        for value, name in secrets:
            if value in text:
                text = text.replace(value, f"[redacted:{name}]")
        return text

    return redact


def run_checks(root: Path, config: Config, *, source_state: dict | None = None) -> dict:
    """Run every configured check, write the report and return it."""
    root = Path(root).resolve()
    evidence_dir = root / EVIDENCE_RELPATH
    logs_dir = evidence_dir / "logs"
    _prepare_evidence_dir(evidence_dir, logs_dir)
    redact = make_redactor(os.environ)
    before = source_state if source_state is not None else compute_source_state(root, config)

    started_at = _now()
    started = time.monotonic()
    deadline = started + config.total_timeout
    required = set(config.required)
    results: list[CheckResult] = []
    for check in config.checks:
        results.append(_run_one(root, check, check.name in required, logs_dir,
                                deadline - time.monotonic(), redact))
    defined = {check.name for check in config.checks}
    for name in config.required:
        if name not in defined:
            results.append(CheckResult(name=name, required=True, outcome=NOT_CONFIGURED,
                                       detail=f"listed in required, but checks.toml has no [checks.{name}] table"))
    duration = time.monotonic() - started
    after = compute_source_state(root, config)

    overall = PASSED if all(r.outcome == PASSED for r in results if r.required) else FAILED
    counts = {outcome: sum(r.outcome == outcome for r in results) for outcome in LABELS}
    report = {
        "schema": REPORT_SCHEMA,
        "tool_version": VERSION,
        "started_at": started_at,
        "finished_at": _now(),
        "duration_seconds": round(duration, 3),
        "root": str(root),
        "platform": {"system": platform.system(), "release": platform.release(),
                     "python": platform.python_version()},
        "config": {"path": _display_path(config.path, root), "sha256": config.sha256},
        "required": list(config.required),
        "source_state": before,
        "source_changed_during_run": before["fingerprint"] != after["fingerprint"],
        "overall": overall,
        "counts": counts,
        "checks": [asdict(r) for r in results],
    }
    _write_json_atomic(evidence_dir / REPORT_NAME, report)
    return report


def _run_one(root: Path, check: Check, required: bool, logs_dir: Path,
             budget_left: float, redact) -> CheckResult:
    result = CheckResult(name=check.name, required=required, outcome=NOT_CONFIGURED, cwd=check.cwd)
    if check.command is None:
        result.detail = "no command configured"
        return result
    argv = list(check.command)
    if argv[0] == PYTHON_TOKEN:
        argv[0] = sys.executable
    result.command = [redact(arg) for arg in argv]
    if not check.enabled:
        result.outcome = SKIPPED
        result.detail = check.reason or "disabled in checks.toml"
        return result
    if budget_left <= 0:
        result.outcome = SKIPPED
        result.detail = "total time budget was used up before this check started"
        return result

    result.outcome = FAILED
    workdir = (root / check.cwd).resolve()
    if not workdir.is_relative_to(root):
        result.detail = f"working directory {check.cwd!r} resolves outside the project root"
        return result
    if not workdir.is_dir():
        result.detail = f"working directory does not exist: {check.cwd}"
        return result
    executable = _resolve_executable(argv[0], workdir)
    if executable is None:
        result.detail = f"executable not found: {argv[0]}"
        return result
    result.executable = redact(executable)

    timeout = min(check.timeout, budget_left)
    result.timeout_seconds = round(timeout, 3)
    started = time.monotonic()
    outcome, exit_code, output, error = _execute([executable, *argv[1:]], workdir, timeout)
    result.duration_seconds = round(time.monotonic() - started, 3)
    result.outcome = outcome
    result.exit_code = exit_code
    if error:
        result.detail = error
    elif outcome == TIMEOUT:
        limited = " (limited by settings.total_timeout_seconds)" if timeout < check.timeout else ""
        result.detail = f"stopped after {timeout:g}s{limited}; the process tree was terminated"

    text = redact(output)
    log_path = logs_dir / f"check-{check.name}.log"
    log_path.write_text(text, encoding="utf-8", errors="replace")
    result.log = log_path.relative_to(root).as_posix()
    result.output_tail = _tail(text)
    return result


def _resolve_executable(name: str, workdir: Path) -> str | None:
    if os.path.isabs(name):
        return name if Path(name).is_file() else None
    if "/" in name or "\\" in name:
        candidate = workdir / name
        return str(candidate) if candidate.is_file() else None
    return shutil.which(name)


def _execute(argv: list[str], cwd: Path, timeout: float) -> tuple[str, int | None, str, str | None]:
    """Run argv without a shell. Returns (outcome, exit code, output, error)."""
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    with tempfile.TemporaryFile() as sink:
        try:
            proc = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=sink,
                                    stderr=subprocess.STDOUT, shell=False, **kwargs)
        except OSError as exc:
            return FAILED, None, "", f"could not start: {exc.strerror or exc}"
        try:
            exit_code = proc.wait(timeout=timeout)
            outcome = PASSED if exit_code == 0 else FAILED
        except subprocess.TimeoutExpired:
            _terminate_tree(proc)
            outcome, exit_code = TIMEOUT, None
        except BaseException:
            _terminate_tree(proc)
            raise
        finally:
            if os.name != "nt":
                _kill_group(proc.pid, signal.SIGKILL)  # leftovers the check started
        output = _read_tail(sink)
    return outcome, exit_code, output, None


def _terminate_tree(proc: subprocess.Popen) -> None:
    if os.name == "nt":
        taskkill = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "taskkill.exe"
        try:
            subprocess.run([str(taskkill), "/F", "/T", "/PID", str(proc.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        _kill_group(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
        _kill_group(proc.pid, signal.SIGKILL)
    if proc.poll() is None:
        proc.kill()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def _kill_group(pgid: int, sig) -> None:
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _read_tail(sink) -> str:
    sink.flush()
    size = sink.seek(0, os.SEEK_END)
    start = max(0, size - LOG_MAX_BYTES)
    sink.seek(start)
    text = sink.read().decode("utf-8", errors="replace")
    if start:
        text = f"[first {start} bytes of output not kept]\n" + text.split("\n", 1)[-1]
    return text


def _tail(text: str) -> str:
    tail = "\n".join(text.splitlines()[-TAIL_LINES:])
    return tail[-TAIL_CHARS:]


def _prepare_evidence_dir(evidence_dir: Path, logs_dir: Path) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    ignore = evidence_dir / ".gitignore"
    if not ignore.exists():
        ignore.write_text("# Written by claude-code-harness verify.py. Evidence is local by default.\n*\n",
                          encoding="utf-8")
    for old in logs_dir.glob("check-*.log"):
        old.unlink()


def _write_json_atomic(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _display_path(path: Path, root: Path) -> str:
    resolved = Path(path).resolve()
    return resolved.relative_to(root).as_posix() if resolved.is_relative_to(root) else str(resolved)


# ---------------------------------------------------------------- evidence status


def load_report(root: Path) -> dict | None:
    """Return the latest report, or None if it is missing or unusable."""
    path = Path(root) / EVIDENCE_RELPATH / REPORT_NAME
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (not isinstance(report, dict) or report.get("schema") != REPORT_SCHEMA
            or not isinstance(report.get("source_state"), dict)
            or report.get("overall") not in (PASSED, FAILED)):
        return None
    return report


def evidence_status(root: Path, config: Config) -> dict:
    root = Path(root).resolve()
    report = load_report(root)
    current = compute_source_state(root, config)
    status = {"state": "missing", "current_fingerprint": current["fingerprint"],
              "report": f"{EVIDENCE_RELPATH}/{REPORT_NAME}"}
    if report is None:
        return status
    recorded = report["source_state"]
    status.update(
        state="fresh" if recorded.get("fingerprint") == current["fingerprint"] else "stale",
        overall=report["overall"],
        recorded_at=report.get("finished_at"),
        recorded_fingerprint=recorded.get("fingerprint"),
        config_changed=report.get("config", {}).get("sha256") != config.sha256,
        changes=diff_source_states(recorded, current),
    )
    return status


# ---------------------------------------------------------------- output


def display_command(argv: list[str]) -> str:
    return subprocess.list2cmdline(argv) if os.name == "nt" else shlex.join(argv)


def format_summary(report: dict) -> str:
    state = report["source_state"]
    lines = [
        f"claude-code-harness verify {report['tool_version']}",
        f"root     {report['root']}",
        f"config   {report['config']['path']}",
        f"source   {state['fingerprint'][:12]} ({state['file_count']} files)",
        "",
    ]
    width = max(len(c["name"]) for c in report["checks"])
    for c in report["checks"]:
        parts = [f"  {LABELS[c['outcome']]:<14} {c['name']:<{width}}  {'required' if c['required'] else 'optional'}"]
        if c["exit_code"] is not None:
            parts.append(f"exit {c['exit_code']}")
        if c["duration_seconds"] is not None:
            parts.append(f"{c['duration_seconds']:.2f}s")
        if c["command"] and c["outcome"] != SKIPPED:
            parts.append(display_command(c["command"]))
        lines.append("  ".join(parts))
        if c["detail"]:
            lines.append(f"      {'not run: ' if c['outcome'] == SKIPPED else ''}{c['detail']}")
        if c["outcome"] in (FAILED, TIMEOUT) and c["output_tail"]:
            lines.extend(f"      | {line}" for line in c["output_tail"].splitlines()[-15:])
    required = [c for c in report["checks"] if c["required"]]
    passed = sum(c["outcome"] == PASSED for c in required)
    lines += ["", f"RESULT   {report['overall'].upper()}  ({passed} of {len(required)} required checks passed)"]
    if report["source_changed_during_run"]:
        lines.append("warning  selected source files changed while the checks ran, so this evidence is already stale")
    lines.append(f"report   {EVIDENCE_RELPATH}/{REPORT_NAME}")
    return "\n".join(lines)


def format_status(status: dict) -> str:
    if status["state"] == "missing":
        return (f"evidence  NONE\nreport    {status['report']} is missing or unreadable\n"
                f"run       python {CONFIG_RELPATH.rsplit('/', 1)[0]}/verify.py")
    lines = [
        f"evidence  {status['state'].upper()}",
        f"report    {status['report']} ({status['overall'].upper()}, finished {status['recorded_at']})",
        f"recorded  {status['recorded_fingerprint'][:12]}",
        f"current   {status['current_fingerprint'][:12]}",
    ]
    if status["state"] == "stale":
        changes = status["changes"]
        for kind in ("modified", "added", "removed"):
            lines.extend(f"  {kind:<9} {path}" for path in changes[kind])
        if status["config_changed"]:
            lines.append("  modified  checks configuration")
        lines.append("The recorded result does not apply to the current source. Run verify.py again.")
    return "\n".join(lines)


# ---------------------------------------------------------------- command line


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(
        prog="verify.py",
        description="Run the checks listed in .claude/harness/checks.toml and record evidence.",
    )
    parser.add_argument("command", nargs="?", choices=["run", "status"], default="run")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT,
                        help="project root (default: the directory that contains .claude/)")
    parser.add_argument("--config", type=Path, help=f"checks file (default: <root>/{CONFIG_RELPATH})")
    parser.add_argument("--json", action="store_true", help="print JSON instead of the summary")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    if not root.is_dir():
        print(f"verify: project root is not a directory: {root}", file=sys.stderr)
        return 2
    config_path = args.config if args.config else root / CONFIG_RELPATH
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"verify: configuration error: {exc}", file=sys.stderr)
        if not Path(config_path).exists():
            print("verify: copy .claude/harness/checks.example.toml to checks.toml and list the "
                  "commands this project already uses.", file=sys.stderr)
        return 2

    if args.command == "status":
        status = evidence_status(root, config)
        print(json.dumps(status, indent=2) if args.json else format_status(status))
        if status["state"] == "missing":
            return 4
        if status["state"] == "stale":
            return 3
        return 0 if status["overall"] == PASSED else 1

    try:
        report = run_checks(root, config)
    except KeyboardInterrupt:
        print("verify: interrupted; no report written", file=sys.stderr)
        return 130
    print(json.dumps(report, indent=2) if args.json else format_summary(report))
    return 0 if report["overall"] == PASSED else 1


if __name__ == "__main__":
    sys.exit(main())
