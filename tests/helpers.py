"""Shared fixtures. Every test works in its own temporary directory."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
KIT = REPO / "kit"
HARNESS_SRC = KIT / ".claude" / "harness"
for path in (HARNESS_SRC, REPO):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import install  # noqa: E402
import stop_hook  # noqa: E402
import verify  # noqa: E402

PY = sys.executable


def toml_list(argv: list[str]) -> str:
    """A TOML array of strings. JSON string escapes are valid TOML basic-string escapes."""
    return json.dumps(argv)


def py_code(code: str) -> list[str]:
    return [PY, "-c", code]


def checks_toml(checks: dict[str, dict], required: list[str], *, include: list[str] | None = None,
                settings: dict | None = None) -> str:
    lines = [f"required = {toml_list(required)}"]
    if settings:
        lines.append("[settings]")
        lines += [f"{k} = {json.dumps(v)}" for k, v in settings.items()]
    if include is not None:
        lines += ["[source]", f"include = {toml_list(include)}"]
    for name, spec in checks.items():
        lines.append(f"[checks.{name}]")
        for key, value in spec.items():
            lines.append(f"{key} = {toml_list(value) if isinstance(value, list) else json.dumps(value)}")
    return "\n".join(lines) + "\n"


class TempDirTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="cch-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def make_project(self, name: str = "project", *, config: str | None = None,
                     files: dict[str, str] | None = None, with_scripts: bool = True) -> Path:
        root = self.tmp / name
        harness = root / ".claude" / "harness"
        harness.mkdir(parents=True)
        if with_scripts:
            for script in ("verify.py", "stop_hook.py"):
                shutil.copy2(HARNESS_SRC / script, harness / script)
        if config is not None:
            (harness / "checks.toml").write_text(config, encoding="utf-8")
        for rel, content in (files or {}).items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return root


def run_script(script: Path, *args: str, stdin: str | None = None, env: dict | None = None,
               cwd: Path | None = None, timeout: float = 120) -> subprocess.CompletedProcess:
    full_env = dict(os.environ)
    full_env.update(env or {})
    return subprocess.run([PY, str(script), *args], input=stdin, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=full_env, cwd=cwd, timeout=timeout)


def snapshot(root: Path) -> dict[str, bytes | None]:
    """Every file and directory under root, with file contents. Directories map to None."""
    result: dict[str, bytes | None] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        result[rel] = path.read_bytes() if path.is_file() else None
    return result
