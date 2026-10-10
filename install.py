#!/usr/bin/env python3
"""Preview, install or remove the claude-code-harness kit in an existing project.

    python install.py install TARGET --dry-run   list what would be written and any conflicts
    python install.py install TARGET             copy the kit; refuses if any file conflicts
    python install.py remove TARGET --dry-run    list what removal would delete and keep
    python install.py remove TARGET              delete installed files you have not modified

The installer only creates new files inside TARGET. It never edits CLAUDE.md, settings
files, hooks or permissions, and it never runs project commands.
Standard library only. Python 3.11 or newer.

Exit codes: 0 done or nothing to do, 1 refused (conflict or unsafe path), 2 usage error.
"""

from __future__ import annotations

import sys

if sys.version_info < (3, 11):
    sys.stderr.write("install.py needs Python 3.11 or newer.\n")
    raise SystemExit(2)

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

VERSION = "0.1.0"
KIT_DIR = Path(__file__).resolve().parent / "kit"
MANIFEST_RELPATH = ".claude/harness/install-manifest.json"
MANIFEST_SCHEMA = "claude-code-harness/install-manifest/1"


class InstallError(Exception):
    """The operation was refused. Nothing unsafe was written."""


class EscapeError(InstallError):
    """A path would land outside the target directory."""


class UsageError(InstallError):
    """The target argument is not a usable directory."""


@dataclass
class Item:
    rel: str
    status: str
    detail: str = ""


# ---------------------------------------------------------------- paths


def resolve_target(raw: str) -> Path:
    target = Path(raw).expanduser()
    if not target.exists():
        raise UsageError(f"target directory does not exist: {target}")
    if not target.is_dir():
        raise UsageError(f"target is not a directory: {target}")
    return target.resolve(strict=True)


def safe_destination(target: Path, rel: str) -> Path:
    """Join rel onto the resolved target and refuse anything that leaves it.

    Rejects absolute paths, drive letters, '..' segments and backslashes, then resolves
    the result so that a symlink or junction inside the target cannot redirect a write.
    """
    pure = PurePosixPath(rel)
    if (not rel or "\\" in rel or pure.is_absolute() or PureWindowsPath(rel).drive
            or PureWindowsPath(rel).is_absolute() or any(part in ("..", "") for part in rel.split("/"))):
        raise EscapeError(f"unsafe relative path {rel!r}")
    candidate = target.joinpath(*pure.parts)
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(target):
        raise EscapeError(f"{rel} resolves to {resolved}, outside the target {target}")
    return candidate


def kit_files(kit_dir: Path = KIT_DIR) -> list[str]:
    return sorted(
        path.relative_to(kit_dir).as_posix()
        for path in kit_dir.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------- manifest


def read_manifest(target: Path) -> dict | None:
    path = safe_destination(target, MANIFEST_RELPATH)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InstallError(f"{MANIFEST_RELPATH} is unreadable ({exc}); inspect or delete it by hand") from None
    files = data.get("files") if isinstance(data, dict) else None
    dirs = data.get("created_dirs") if isinstance(data, dict) else None
    if (data.get("schema") != MANIFEST_SCHEMA or not isinstance(files, dict) or not isinstance(dirs, list)
            or not all(isinstance(k, str) and isinstance(v, str) for k, v in files.items())
            or not all(isinstance(d, str) for d in dirs)):
        raise InstallError(f"{MANIFEST_RELPATH} is not a claude-code-harness manifest; inspect it by hand")
    return data


def write_manifest(target: Path, files: dict[str, str], created_dirs: set[str]) -> None:
    path = safe_destination(target, MANIFEST_RELPATH)
    data = {
        "schema": MANIFEST_SCHEMA,
        "kit_version": VERSION,
        "files": dict(sorted(files.items())),
        "created_dirs": sorted(created_dirs),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------- install


def plan_install(target: Path, kit_dir: Path = KIT_DIR) -> tuple[list[Item], dict | None]:
    manifest = read_manifest(target)
    tracked = manifest["files"] if manifest else {}
    items = []
    for rel in kit_files(kit_dir):
        try:
            dest = safe_destination(target, rel)
        except EscapeError as exc:
            items.append(Item(rel, "conflict", str(exc)))
            continue
        if dest.is_symlink() or (dest.exists() and not dest.is_file()):
            items.append(Item(rel, "conflict", "exists and is not a regular file"))
        elif dest.exists():
            current = sha256_file(dest)
            if current == sha256_file(kit_dir / rel):
                items.append(Item(rel, "unchanged"))
            elif rel in tracked and current == tracked[rel]:
                items.append(Item(rel, "kept", "installed by another kit version, unmodified; left as is"))
            elif rel in tracked:
                items.append(Item(rel, "kept", "you modified it after installation; left as is"))
            else:
                items.append(Item(rel, "conflict", "already exists with different content and was not installed by this tool"))
        else:
            blocker = next((p for p in dest.parents if p.is_relative_to(target) and p.exists() and not p.is_dir()), None)
            if blocker is not None:
                items.append(Item(rel, "conflict", f"{blocker.relative_to(target).as_posix()} exists and is not a directory"))
            else:
                items.append(Item(rel, "create"))
    return items, manifest


def install(target: Path, *, dry_run: bool, kit_dir: Path = KIT_DIR, out=None) -> int:
    out = out or sys.stdout
    items, manifest = plan_install(target, kit_dir)
    print(f"claude-code-harness {VERSION}: install into {target}", file=out)
    _print_items(items, out)
    conflicts = [i for i in items if i.status == "conflict"]
    if conflicts:
        print(f"\nRefused: {len(conflicts)} conflict(s). Nothing was written. Move or merge those "
              f"files by hand, then run this again.", file=out)
        return 1
    if dry_run:
        print("\nDry run: nothing was written.", file=out)
        return 0
    to_create = [i for i in items if i.status == "create"]
    if not to_create:
        print("\nNothing to do: every kit file is already present.", file=out)
        _print_next_steps(target, out)
        return 0

    files = dict(manifest["files"]) if manifest else {}
    created_dirs = set(manifest["created_dirs"]) if manifest else set()
    try:
        for item in to_create:
            dest = safe_destination(target, item.rel)  # checked again right before writing
            missing = [p for p in reversed(dest.parents) if p.is_relative_to(target) and not p.exists()]
            for directory in missing:
                directory.mkdir()
                created_dirs.add(directory.relative_to(target).as_posix())
            data = (kit_dir / item.rel).read_bytes()
            with open(dest, "xb") as handle:  # "x": fail rather than overwrite
                handle.write(data)
            files[item.rel] = hashlib.sha256(data).hexdigest()
    finally:
        if files or created_dirs:  # record partial progress too, so removal can clean it up
            write_manifest(target, files, created_dirs)
    print(f"\nInstalled {len(to_create)} file(s). Recorded in {MANIFEST_RELPATH}.", file=out)
    _print_next_steps(target, out)
    return 0


def _print_next_steps(target: Path, out) -> None:
    has_checks = (target / ".claude/harness/checks.toml").is_file()
    claude_md = next((p for p in ("CLAUDE.md", ".claude/CLAUDE.md") if (target / p).is_file()), None)
    stop_hooks = _count_stop_hooks(target)
    print("\nNext steps. None of these has been done for you, and no project command was run:", file=out)
    step = 1
    if not has_checks:
        print(f"  {step}. Copy .claude/harness/checks.example.toml to .claude/harness/checks.toml and list "
              f"the commands this project already uses. Each listed command will be executed.", file=out)
        step += 1
    print(f"  {step}. Run the checks yourself once: python .claude/harness/verify.py", file=out)
    step += 1
    if claude_md:
        print(f"  {step}. {claude_md} exists and was not changed. To tie it to the checks, you could add to "
              f"its definition of done: `python .claude/harness/verify.py` reports PASSED.", file=out)
    else:
        print(f"  {step}. No CLAUDE.md found. Start from .claude/harness/templates/CLAUDE.template.md.", file=out)
    step += 1
    print(f"  {step}. Optional Stop hook: read .claude/harness/hook-settings.example.json, then merge its "
          f"entry by hand into .claude/settings.local.json (you) or .claude/settings.json (shared).", file=out)
    if stop_hooks:
        print(f"     Your settings already define {stop_hooks} Stop hook entr{'y' if stop_hooks == 1 else 'ies'}; "
              f"the harness hook would run alongside them.", file=out)


def _count_stop_hooks(target: Path) -> int:
    count = 0
    for name in ("settings.json", "settings.local.json"):
        try:
            data = json.loads((target / ".claude" / name).read_text(encoding="utf-8"))
            count += len(data.get("hooks", {}).get("Stop", []))
        except (OSError, ValueError, AttributeError, TypeError):
            continue
    return count


# ---------------------------------------------------------------- remove


def plan_remove(target: Path) -> tuple[list[Item], dict | None]:
    manifest = read_manifest(target)
    if manifest is None:
        return [], None
    items = []
    for rel, digest in sorted(manifest["files"].items()):
        try:
            dest = safe_destination(target, rel)
        except EscapeError as exc:
            items.append(Item(rel, "refused", str(exc)))
            continue
        if not dest.exists() and not dest.is_symlink():
            items.append(Item(rel, "already gone"))
        elif dest.is_symlink() or not dest.is_file():
            items.append(Item(rel, "kept", "no longer a regular file"))
        elif sha256_file(dest) == digest:
            items.append(Item(rel, "delete"))
        else:
            items.append(Item(rel, "kept", "modified since installation"))
    return items, manifest


def remove(target: Path, *, dry_run: bool, out=None) -> int:
    out = out or sys.stdout
    items, manifest = plan_remove(target)
    print(f"claude-code-harness {VERSION}: remove from {target}", file=out)
    if manifest is None:
        print("Nothing to remove: no install manifest found.", file=out)
        return 0
    _print_items(items, out)
    refused = [i for i in items if i.status == "refused"]
    if dry_run:
        print("\nDry run: nothing was deleted.", file=out)
        return 1 if refused else 0

    for item in items:
        if item.status == "delete":
            safe_destination(target, item.rel).unlink()
    remaining = {i.rel: manifest["files"][i.rel] for i in items if i.status in ("kept", "refused")}
    if remaining:
        write_manifest(target, remaining, set(manifest["created_dirs"]))
    else:
        safe_destination(target, MANIFEST_RELPATH).unlink()

    kept_dirs = set()
    for rel in sorted(manifest["created_dirs"], key=lambda d: d.count("/"), reverse=True):
        try:
            directory = safe_destination(target, rel)
        except EscapeError:
            kept_dirs.add(rel)
            continue
        try:
            directory.rmdir()
        except FileNotFoundError:
            pass
        except OSError:
            kept_dirs.add(rel)
    if remaining and kept_dirs != set(manifest["created_dirs"]):
        write_manifest(target, remaining, kept_dirs)

    deleted = sum(i.status == "delete" for i in items)
    print(f"\nDeleted {deleted} file(s).", file=out)
    if remaining:
        print(f"Kept {len(remaining)} file(s) listed above; they stay in {MANIFEST_RELPATH}.", file=out)
    for rel in sorted(kept_dirs):
        print(f"Kept directory {rel}/ because it is not empty.", file=out)
    return 1 if refused else 0


def _print_items(items: list[Item], out) -> None:
    for item in items:
        detail = f"  ({item.detail})" if item.detail else ""
        print(f"  {item.status:<13} {item.rel}{detail}", file=out)


# ---------------------------------------------------------------- command line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="install.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="action", required=True)
    for name, help_text in (("install", "copy the kit into TARGET"), ("remove", "remove the kit from TARGET")):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("target", help="the project directory (required, never guessed)")
        cmd.add_argument("--dry-run", action="store_true", help="show the plan without writing anything")
    args = parser.parse_args(argv)
    try:
        target = resolve_target(args.target)
        if args.action == "install":
            return install(target, dry_run=args.dry_run)
        return remove(target, dry_run=args.dry_run)
    except InstallError as exc:
        print(f"install.py: {exc}", file=sys.stderr)
        return 2 if isinstance(exc, UsageError) else 1


if __name__ == "__main__":
    sys.exit(main())
