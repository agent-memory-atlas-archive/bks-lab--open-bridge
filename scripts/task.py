#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Small write commands for a task's STATUS.md.

    python3 scripts/task.py priority <slug> {P0,P1,P2,P3}
    python3 scripts/task.py note <slug> <text>

Rewrites only the ``priority:`` line inside the YAML frontmatter of
work/tasks/<slug>/STATUS.md or work/streams/<slug>/STATUS.md (the key is added
after ``status:`` when absent), sets ``last_updated:`` to today, leaves every
other byte alone (comments, quoting, order), then regenerates work/board.md with
scripts/gen-board.py. An unknown slug or value exits 1 without writing.

``note`` appends ``- YYYY-MM-DD: <text>`` to the ``## Notes`` section of the body,
creating it at the end when there is none, and sets ``last_updated:``; nothing
else changes.

Comment and blank lines above the opening ``---`` (the shipped template starts
with a ``# yaml-language-server:`` line) are kept byte for byte.

The allowed values are the enum in work/templates/_schema.status.yaml.
The contract lives in ``scripts/tests/test_task.py``.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRIORITIES = ("P0", "P1", "P2", "P3")      # work/templates/_schema.status.yaml: priority.enum


def find_status(root: Path, slug: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", slug):
        raise ValueError(f"not a task slug: {slug!r}")
    for kind in ("tasks", "streams"):
        path = root / "work" / kind / slug / "STATUS.md"
        if path.is_file():
            return path
    raise ValueError(f"no task or stream {slug!r} under {root / 'work'}")


def set_priority(text: str, value: str, today: str) -> str:
    """Edit the frontmatter lines only; the body and all other bytes stay as they are."""
    return set_fields(text, [("priority", value, "status"), ("last_updated", today, None)])


NOTES = re.compile(r"^## Notes\s*$")


def add_note(text: str, note: str, today: str) -> str:
    """Append a dated line to the notes section of the body; the frontmatter gets last_updated."""
    note = " ".join(note.split())
    if not note:
        raise ValueError("empty note")
    nl = "\r\n" if "\r\n" in text.split("\n", 1)[0] + "\n" else "\n"
    line = f"- {today}: {note}{nl}"
    lines = set_fields(text, [("last_updated", today, None)]).splitlines(keepends=True)
    start = next((i for i, ln in enumerate(lines) if NOTES.match(ln.rstrip("\r\n"))), None)
    if start is None:
        return "".join(lines).rstrip("\r\n") + f"{nl}{nl}## Notes{nl}{nl}" + line
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    at = end
    while at > start + 1 and not lines[at - 1].strip():
        at -= 1
    if not lines[at - 1].endswith("\n"):
        lines[at - 1] += nl
    if at == start + 1:
        lines.insert(at, nl)      # a blank line under the heading, as a new section has
        at += 1
    lines.insert(at, line)
    return "".join(lines)


def set_fields(text: str, fields: list) -> str:
    """Set (key, value, insert-after-key) in the frontmatter; the body and all other bytes stay."""
    lines = text.splitlines(keepends=True)
    start = 0
    while start < len(lines) and (not lines[start].strip() or lines[start].startswith("#")):
        start += 1            # a leading "# yaml-language-server: ..." line stays as it is
    if start >= len(lines) or lines[start].rstrip("\r\n") != "---":
        raise ValueError("STATUS.md has no frontmatter")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].rstrip("\r\n") == "---"), None)
    if end is None:
        raise ValueError("STATUS.md frontmatter is not closed")
    nl = "\r\n" if lines[start].endswith("\r\n") else "\n"

    def find(key: str) -> int | None:
        return next((i for i in range(start + 1, end) if re.match(rf"{key}:(\s|$)", lines[i])), None)

    def put(key: str, new: str, after: str | None = None) -> None:
        nonlocal end
        i = find(key)
        if i is not None:
            lines[i] = f"{key}: {new}" + (lines[i][len(lines[i].rstrip("\r\n")):] or nl)
            return
        at = find(after) if after else None
        pos = at + 1 if at is not None else end
        lines.insert(pos, f"{key}: {new}{nl}")
        end += 1

    for key, value, after in fields:
        put(key, value, after=after)
    return "".join(lines)


def regenerate_board(root: Path) -> None:
    spec = importlib.util.spec_from_file_location("gen_board", ROOT / "scripts" / "gen-board.py")
    mod = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    spec.loader.exec_module(mod)
    mod.ROOT = root
    mod.TASKS, mod.STREAMS, mod.DONE = (root / "work" / n for n in ("tasks", "streams", "done"))
    mod.main([])


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="task.py", description="Small write commands for STATUS.md.")
    p.add_argument("--root", type=Path, default=ROOT, help="repository root (default: this checkout)")
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("priority", help="set a task's priority")
    pr.add_argument("slug")
    pr.add_argument("value", choices=PRIORITIES)
    nt = sub.add_parser("note", help="append a dated note to a task's notes section")
    nt.add_argument("slug")
    nt.add_argument("text")
    args = p.parse_args(argv)
    today = dt.date.today().isoformat()
    try:
        path = find_status(args.root, args.slug)
        old = path.read_bytes().decode("utf-8")   # bytes: read_text would turn CRLF into LF
        new = (set_priority(old, args.value, today) if args.cmd == "priority"
               else add_note(old, args.text, today))
    except (ValueError, OSError) as exc:
        print(f"task: {exc}", file=sys.stderr)
        return 1
    path.write_bytes(new.encode("utf-8"))
    regenerate_board(args.root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
