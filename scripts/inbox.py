#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The inbox: one place where everything that needs a person waits until it is done.

A finding, a question from an agent, a decision, a draft waiting for its send:
before this existed each one lived wherever it happened to be written down: a
sentence in the log, a chat message, a mail from a scheduled job, a line in a
STATUS.md. Nothing closed them. A briefing that re-read those sources reported
things as open that had been solved hours earlier, because the sentence saying
"needed" was still there and the one saying "done" was further down.

    python3 scripts/inbox.py add --from homebox/issue-radar --kind decision \\
        --summary "PR #70 is green and waits for a merge" --task a2a \\
        --action-json '{"argv": ["gh", "pr", "merge", "70", "-R", "org/repo"]}' \\
        --closes-when-json '{"gh_pr": "org/repo#70", "state": "merged"}'
    python3 scripts/inbox.py list            # open items, most urgent first
    python3 scripts/inbox.py approve <id> [--when-json '{"gh_pr": "org/repo#70", "state": "green"}']
    python3 scripts/inbox.py check           # close what the live source says is done
    python3 scripts/inbox.py run             # execute what a person released
    python3 scripts/inbox.py render          # regenerate work/inbox.md (a view)

LAYOUT. ``work/inbox/<id>/item.yaml`` is written once and never changed.
Every later change (a note, a yes, a close) is a NEW file under
``work/inbox/<id>/events/``. Two machines writing the same inbox through git
therefore never touch the same file, the same property that keeps the task
folders conflict-free. The state of an item is derived from its events, never
stored, like the board is derived from the task folders.

CLOSING. ``closes_when`` names a probe against the live source (a PR merged, an
issue closed, a file present, a command exiting 0, a time passed). ``check``
runs the probes and closes what holds. A probe that cannot be evaluated is
UNKNOWN, never true: an item stays open rather than vanishing on a network error.

GATES. ``free`` the Bridge may act alone · ``your-yes`` acts after a person said
yes, also a conditional yes ("merge once green") that ``run`` executes when the
condition holds · ``only-you`` (send, publish, pay) is never executed by this
script, whatever was recorded.

The contract lives in ``scripts/tests/test_inbox.py``. Model: docs/inbox.md.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_VERSION = 1

KINDS = ("decision", "question", "finding", "draft", "result")
GATES = ("free", "your-yes", "only-you")
URGENCIES = ("now", "today", "later")
VERBS = ("seen", "note", "approve", "reject", "drop", "defer", "close", "executed", "failed")
TERMINAL = {"close": "done", "executed": "done", "reject": "dropped", "drop": "dropped"}
ACTIVE_STATES = ("open", "approved", "waiting")
ACTION_KEYS = {"argv", "label"}
RUN_TIMEOUT_SEC = 600
PROBE_TIMEOUT_SEC = 30
OUTPUT_TAIL = 400

GhRunner = Callable[[list], str]


# ---------------------------------------------------------------- probes

def _gh_cli(args: list) -> str:
    return subprocess.run(
        ["gh", *args], capture_output=True, text=True, timeout=PROBE_TIMEOUT_SEC, check=True
    ).stdout


def _ref(value: str) -> tuple[str, str]:
    repo, _, number = str(value).partition("#")
    if not repo or not number.isdigit():
        raise ValueError(f"expected owner/repo#N, got {value!r}")
    return repo, number


def _parse_when(value) -> dt.datetime:
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.date):
        return dt.datetime.combine(value, dt.time())
    text = str(value)
    return dt.datetime.fromisoformat(text) if "T" in text or " " in text else dt.datetime.combine(
        dt.date.fromisoformat(text), dt.time()
    )


def _status_of_task(slug: str, base: Path) -> str | None:
    work = base / "work"
    for path in [work / "tasks" / slug, work / "streams" / slug, *sorted((work / "done").glob(f"*/{slug}"))]:
        status = path / "STATUS.md"
        if status.is_file():
            text = status.read_text(encoding="utf-8")
            match = re.search(r"^status:\s*([a-z]+)", text, re.MULTILINE)
            return match.group(1) if match else None
    return None


def probe(spec, *, now: dt.datetime | None = None, gh: GhRunner | None = None,
          base: Path | None = None) -> bool | None:
    """Evaluate one probe. True / False, or None when it cannot be evaluated.

    Never raises: a broken probe is UNKNOWN, and unknown never closes anything.
    """
    if not isinstance(spec, dict) or not spec:
        return None
    now = now or dt.datetime.now()
    gh = gh or _gh_cli
    base = base or Path.cwd()
    try:
        if "all" in spec:
            results = [probe(p, now=now, gh=gh, base=base) for p in spec["all"]]
            return None if None in results else all(results)
        if "any" in spec:
            results = [probe(p, now=now, gh=gh, base=base) for p in spec["any"]]
            return True if True in results else (None if None in results else False)
        if "path_exists" in spec:
            path = Path(os.path.expanduser(str(spec["path_exists"])))
            return (path if path.is_absolute() else base / path).exists()
        if "after" in spec:
            return now >= _parse_when(spec["after"])
        if "command" in spec:
            argv = spec["command"]
            if not isinstance(argv, list) or not argv:
                return None
            done = subprocess.run([str(a) for a in argv], capture_output=True, timeout=PROBE_TIMEOUT_SEC,
                                  cwd=base)
            return done.returncode == int(spec.get("expect_exit", 0))
        if "gh_pr" in spec:
            repo, number = _ref(spec["gh_pr"])
            data = json.loads(gh(["pr", "view", number, "-R", repo, "--json", "state,statusCheckRollup"]))
            want = str(spec.get("state", "merged")).lower()
            if want == "green":
                checks = data.get("statusCheckRollup") or []
                ok = {"SUCCESS", "SKIPPED", "NEUTRAL"}
                return bool(checks) and all(
                    (c.get("conclusion") or c.get("state") or "").upper() in ok for c in checks
                )
            return str(data.get("state", "")).lower() == want
        if "gh_issue" in spec:
            repo, number = _ref(spec["gh_issue"])
            data = json.loads(gh(["issue", "view", number, "-R", repo, "--json", "state"]))
            return str(data.get("state", "")).lower() == str(spec.get("state", "closed")).lower()
        if "task_status" in spec:
            status = _status_of_task(str(spec["task_status"]), base)
            return None if status is None else status == str(spec.get("status", "done"))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, json.JSONDecodeError):
        return None
    return None


# ---------------------------------------------------------------- model

@dataclass
class Event:
    name: str
    verb: str
    by: str
    at: str
    data: dict = field(default_factory=dict)


@dataclass
class Item:
    id: str
    data: dict
    events: list
    today: dt.date

    def __getattr__(self, key):
        if key in ("summary", "kind", "gate", "urgency", "task", "source", "created", "key",
                   "action", "closes_when", "detail", "due"):
            return self.data.get("from" if key == "source" else key)
        raise AttributeError(key)

    @property
    def approval(self):
        """The current yes: None, True (plain) or the condition dict."""
        current = None
        for e in self.events:
            if e.verb == "approve":
                current = e.data.get("when") or True
            elif e.verb == "failed":
                current = None
        return current

    @property
    def approved_text(self) -> str | None:
        """The text a person released with their yes (an edited draft), if any."""
        for e in reversed(self.events):
            if e.verb == "approve":
                return e.data.get("text")
        return None

    @property
    def last_failed(self) -> bool:
        acting = [e for e in self.events if e.verb in ("approve", "executed", "failed")]
        return bool(acting) and acting[-1].verb == "failed"

    @property
    def state(self) -> str:
        deferred_until = None
        for e in self.events:
            if e.verb in TERMINAL:
                return TERMINAL[e.verb]
            if e.verb == "defer":
                deferred_until = e.data.get("until")
            elif e.verb == "approve":
                deferred_until = None
        if deferred_until:
            try:
                if _parse_when(deferred_until).date() > self.today:
                    return "deferred"
            except ValueError:
                pass
        approval = self.approval
        if approval is True:
            return "approved"
        if isinstance(approval, dict):
            return "waiting"
        return "open"

    def as_dict(self) -> dict:
        return {"id": self.id, "state": self.state, **{k: v for k, v in self.data.items()
                                                      if k != "schema_version"}}


def _slug(text: str, limit: int = 40) -> str:
    text = text.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:limit].rstrip("-") or "item"


def _check_action(action) -> None:
    if action is None:
        return
    if not isinstance(action, dict) or set(action) - ACTION_KEYS:
        raise ValueError(f"action takes only {sorted(ACTION_KEYS)}, got {action!r}")
    argv = action.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) and a for a in argv):
        raise ValueError("action.argv must be a non-empty list of strings (no shell)")


def _dump(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    tmp.replace(path)


class Inbox:
    def __init__(self, root: Path, *, actor: str, clock: Callable[[], dt.datetime] = dt.datetime.now,
                 gh: GhRunner | None = None):
        self.root = Path(root)
        self.actor = _slug(actor, 30)
        self.clock = clock
        self.gh = gh
        # work/inbox → repository root: probes and actions resolve relative paths there
        self.base = self.root.parent.parent

    # -------------------------------------------------- reading
    def _load_events(self, item_dir: Path) -> list:
        events = []
        for path in sorted((item_dir / "events").glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            events.append(Event(path.name, data.pop("verb", ""), data.pop("by", ""),
                                str(data.pop("at", "")), data))
        events.sort(key=lambda e: (e.at, e.name))
        return events

    def get(self, item_id: str) -> Item:
        item_dir = self.root / item_id
        data = yaml.safe_load((item_dir / "item.yaml").read_text(encoding="utf-8")) or {}
        return Item(item_id, data, self._load_events(item_dir), self.clock().date())

    def items(self) -> list:
        if not self.root.is_dir():
            return []
        return [self.get(p.name) for p in sorted(self.root.iterdir())
                if p.is_dir() and (p / "item.yaml").is_file()]

    def open_items(self) -> list:
        kind_rank = {k: i for i, k in enumerate(KINDS)}
        urgency_rank = {u: i for i, u in enumerate(URGENCIES)}
        active = [i for i in self.items() if i.state in ACTIVE_STATES]
        return sorted(active, key=lambda i: (urgency_rank.get(i.urgency, 9), kind_rank.get(i.kind, 9),
                                             str(i.due or "9999"), str(i.created), i.id))

    def resolve(self, prefix: str) -> str:
        if (self.root / prefix / "item.yaml").is_file():
            return prefix
        hits = [i.id for i in self.items() if i.id.startswith(prefix)]
        if len(hits) != 1:
            raise KeyError(f"{prefix!r} matches {len(hits)} items" + (f": {hits}" if hits else ""))
        return hits[0]

    # -------------------------------------------------- writing
    def add(self, *, source: str, kind: str, summary: str, task: str | None = None,
            gate: str = "your-yes", urgency: str = "today", detail: str | None = None,
            action: dict | None = None, closes_when: dict | None = None, key: str | None = None,
            due: str | None = None) -> str:
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}")
        if gate not in GATES:
            raise ValueError(f"gate must be one of {GATES}")
        if urgency not in URGENCIES:
            raise ValueError(f"urgency must be one of {URGENCIES}")
        if not summary or not str(summary).strip():
            raise ValueError("summary is required")
        if closes_when is not None and not isinstance(closes_when, dict):
            raise ValueError("closes_when must be a probe mapping")
        _check_action(action)
        if due is not None:
            _parse_when(due)            # raises ValueError on a date nobody can read
        if key:
            for existing in self.items():
                if existing.key == key and existing.state not in ("done", "dropped"):
                    self.event(existing.id, "seen", summary=summary)
                    return existing.id
        now = self.clock()
        stem = f"{now:%Y%m%d-%H%M}-{_slug(summary)}"
        item_id, n = stem, 2
        while (self.root / item_id).exists():
            item_id, n = f"{stem}-{n}", n + 1
        data = {"schema_version": SCHEMA_VERSION, "created": now.isoformat(timespec="minutes"),
                "from": source, "kind": kind, "summary": summary.strip(), "urgency": urgency, "gate": gate}
        for name, value in (("task", task), ("due", due), ("detail", detail), ("key", key),
                            ("action", action), ("closes_when", closes_when)):
            if value:
                data[name] = value
        _dump(self.root / item_id / "item.yaml", data)
        (self.root / item_id / "events").mkdir(exist_ok=True)
        return item_id

    def event(self, item_id: str, verb: str, *, by: str | None = None, **data) -> None:
        if verb not in VERBS:
            raise ValueError(f"verb must be one of {VERBS}")
        events_dir = self.root / item_id / "events"
        if not (self.root / item_id / "item.yaml").is_file():
            raise KeyError(item_id)
        now = self.clock()
        actor = _slug(by, 30) if by else self.actor
        stamp = f"{now:%Y%m%dT%H%M%S}"
        seq = len(list(events_dir.glob(f"{stamp}-*"))) if events_dir.is_dir() else 0
        body = {"verb": verb, "by": actor, "at": now.isoformat(timespec="seconds")}
        body.update({k: v for k, v in data.items() if v is not None})
        _dump(events_dir / f"{stamp}-{seq:02d}-{actor}-{verb}.yaml", body)

    def note(self, item_id: str, text: str) -> None:
        self.event(item_id, "note", text=text)

    def approve(self, item_id: str, when: dict | None = None, text: str | None = None) -> None:
        if when is not None:
            if self.get(item_id).gate == "only-you":
                raise PermissionError("an only-you item takes no conditional yes: it is never executed")
            if not isinstance(when, dict):
                raise ValueError("when must be a probe mapping")
        self.event(item_id, "approve", when=when, text=text)

    def reject(self, item_id: str, note: str | None = None) -> None:
        self.event(item_id, "reject", text=note)

    def close(self, item_id: str, note: str | None = None) -> None:
        self.event(item_id, "close", text=note)

    # -------------------------------------------------- acting on the live source
    def check(self) -> list:
        closed = []
        for item in self.items():
            if item.state in ("done", "dropped") or not item.closes_when:
                continue
            if probe(item.closes_when, now=self.clock(), gh=self.gh, base=self.base) is True:
                self.event(item.id, "close", by="check", text="closes_when holds")
                closed.append(item.id)
        return closed

    def runnable(self) -> list:
        ready = []
        for item in self.items():
            if not item.action or item.state not in ACTIVE_STATES or item.gate == "only-you":
                continue
            approval = item.approval
            if item.gate == "free" and approval is None:
                if item.last_failed:
                    continue        # a failed free action waits for a person, not for the next tick
                ready.append(item)
            elif approval is True:
                ready.append(item)
            elif isinstance(approval, dict):
                if probe(approval, now=self.clock(), gh=self.gh, base=self.base) is True:
                    ready.append(item)
        return ready

    def run(self, dry_run: bool = False) -> list:
        executed = []
        for item in self.runnable():
            if dry_run:
                executed.append(item.id)
                continue
            argv = item.action["argv"]
            try:
                done = subprocess.run(argv, capture_output=True, text=True, timeout=RUN_TIMEOUT_SEC,
                                      cwd=self.base if self.base.is_dir() else None)
                code, output = done.returncode, (done.stdout + done.stderr)[-OUTPUT_TAIL:]
            except (OSError, subprocess.SubprocessError) as exc:
                code, output = -1, str(exc)[-OUTPUT_TAIL:]
            if code == 0:
                self.event(item.id, "executed", exit=0, output=output.strip() or None)
                executed.append(item.id)
            else:
                self.event(item.id, "failed", exit=code, output=output.strip() or None)
        return executed

    # -------------------------------------------------- views and validation
    def render(self) -> str:
        rows = self.open_items()
        lines = [
            "<!-- GENERATED by scripts/inbox.py render from work/inbox/. Do not edit: change an item",
            "     with scripts/inbox.py and regenerate. -->",
            "# Inbox",
            "",
            f"> As of {self.clock():%Y-%m-%d %H:%M} · {len(rows)} open",
            "",
        ]
        if not rows:
            lines.append("_Nothing waits for you._")
        else:
            lines += ["| # | Urgency | Due | Kind | What | Task | Gate | State | Id |",
                      "|---|---|---|---|---|---|---|---|---|"]
            for n, item in enumerate(rows, 1):
                summary = str(item.summary).replace("|", "\\|")
                lines.append(f"| {n} | {item.urgency} | {item.due or ''} | {item.kind} | {summary} | {item.task or ''} "
                             f"| {item.gate} | {item.state} | `{item.id}` |")
        return "\n".join(lines) + "\n"

    def validate(self) -> list:
        problems = []
        if not self.root.is_dir():
            return problems
        for item_dir in sorted(p for p in self.root.iterdir() if p.is_dir()):
            where = item_dir.name
            try:
                data = yaml.safe_load((item_dir / "item.yaml").read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError) as exc:
                problems.append(f"{where}: unreadable item.yaml ({exc})")
                continue
            for name in ("created", "from", "kind", "summary", "urgency", "gate"):
                if not data.get(name):
                    problems.append(f"{where}: missing {name}")
            for name, allowed in (("kind", KINDS), ("gate", GATES), ("urgency", URGENCIES)):
                if data.get(name) and data[name] not in allowed:
                    problems.append(f"{where}: {name} {data[name]!r} not in {allowed}")
            try:
                _check_action(data.get("action"))
            except ValueError as exc:
                problems.append(f"{where}: {exc}")
            for path in sorted((item_dir / "events").glob("*.yaml")):
                try:
                    verb = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("verb")
                except yaml.YAMLError:
                    verb = None
                if verb not in VERBS:
                    problems.append(f"{where}: event {path.name} has verb {verb!r}")
        return problems


# ---------------------------------------------------------------- CLI

def _json_arg(text: str | None):
    return json.loads(text) if text else None


def _default_actor() -> str:
    return os.environ.get("BRIDGE_ACTOR") or socket.gethostname().split(".")[0] or "bridge"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="inbox.py", description="The Bridge inbox (docs/inbox.md).")
    p.add_argument("--root", type=Path, default=ROOT, help="repository root (default: this checkout)")
    p.add_argument("--by", default=None, help="who acts (default: $BRIDGE_ACTOR or the host name)")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="file a new item (or record a repeat of an open item with the same --key)")
    a.add_argument("--from", dest="source", required=True)
    a.add_argument("--kind", required=True, choices=KINDS)
    a.add_argument("--summary", required=True)
    a.add_argument("--task")
    a.add_argument("--gate", default="your-yes", choices=GATES)
    a.add_argument("--urgency", default="today", choices=URGENCIES)
    a.add_argument("--due", help="YYYY-MM-DD or YYYY-MM-DDTHH:MM: when it happens or must be done")
    a.add_argument("--detail")
    a.add_argument("--key", help="dedup key: a watcher that fires again adds no second item")
    a.add_argument("--action-json")
    a.add_argument("--closes-when-json")

    ls = sub.add_parser("list", help="open items, most urgent first")
    ls.add_argument("--all", action="store_true")
    ls.add_argument("--json", action="store_true")
    ls.add_argument("--short", action="store_true", help="one line per item, for a phone or an e-ink screen")

    sub.add_parser("show").add_argument("id")
    ap = sub.add_parser("approve", help="say yes; with --when-json it runs once the condition holds")
    ap.add_argument("id")
    ap.add_argument("--when-json")
    ap.add_argument("--text", help="release an edited version of a draft")
    for name in ("reject", "close", "drop"):
        sp = sub.add_parser(name)
        sp.add_argument("id")
        sp.add_argument("--note")
    df = sub.add_parser("defer")
    df.add_argument("id")
    df.add_argument("--until", required=True, help="YYYY-MM-DD")
    nt = sub.add_parser("note")
    nt.add_argument("id")
    nt.add_argument("text")
    sub.add_parser("check", help="close every item whose closes_when holds")
    rn = sub.add_parser("run", help="execute released actions (free, yes, or yes-once-condition)")
    rn.add_argument("--dry-run", action="store_true")
    sub.add_parser("render", help="regenerate work/inbox.md")
    sub.add_parser("validate")
    sy = sub.add_parser("sync", help="commit work/inbox (and only it), pull --rebase, push")
    sy.add_argument("--no-push", action="store_true")
    return p


def _short(item: Item) -> str:
    mark = {"now": "!", "today": "·", "later": " "}.get(item.urgency, " ")
    return f"{mark} {item.summary}" + (f"  [{item.task}]" if item.task else "")


def _sync(root: Path, actor: str, push: bool) -> int:
    def git(*args):
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)

    paths = ["work/inbox", "work/inbox.md"]
    git("add", "--", *[p for p in paths if (root / p).exists()])
    if git("diff", "--cached", "--quiet", "--", *paths).returncode != 0:
        msg = f"inbox: {actor} {dt.datetime.now():%Y-%m-%d %H:%M}"
        done = git("commit", "-m", msg, "--", *paths)
        if done.returncode != 0:
            print(done.stderr.strip(), file=sys.stderr)
            return 1
    if not push:
        return 0
    for step in (("pull", "--rebase", "--autostash"), ("push",)):
        done = git(*step)
        if done.returncode != 0:
            print(done.stderr.strip(), file=sys.stderr)
            return 1
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    actor = args.by or _default_actor()
    box = Inbox(args.root / "work" / "inbox", actor=actor)
    try:
        if args.cmd == "add":
            print(box.add(source=args.source, kind=args.kind, summary=args.summary, task=args.task,
                          gate=args.gate, urgency=args.urgency, detail=args.detail, key=args.key, due=args.due,
                          action=_json_arg(args.action_json), closes_when=_json_arg(args.closes_when_json)))
        elif args.cmd == "list":
            items = box.items() if args.all else box.open_items()
            if args.json:
                print(json.dumps([i.as_dict() for i in items], ensure_ascii=False, indent=1))
            elif args.short:
                print("\n".join(_short(i) for i in items) if items else "Nothing waits.")
            else:
                for i in items:
                    print(f"{i.id}  {i.state:8} {i.urgency:5} {i.kind:8} {i.gate:8}  {i.summary}"
                          + (f"  [{i.task}]" if i.task else ""))
        elif args.cmd == "show":
            item = box.get(box.resolve(args.id))
            print(yaml.safe_dump(item.as_dict(), allow_unicode=True, sort_keys=False), end="")
            for e in item.events:
                print(f"  {e.at}  {e.by:12} {e.verb:9} {json.dumps(e.data, ensure_ascii=False) if e.data else ''}")
        elif args.cmd == "approve":
            box.approve(box.resolve(args.id), when=_json_arg(args.when_json), text=args.text)
        elif args.cmd in ("reject", "close", "drop"):
            box.event(box.resolve(args.id), args.cmd, text=args.note)
        elif args.cmd == "defer":
            dt.date.fromisoformat(args.until)
            box.event(box.resolve(args.id), "defer", until=args.until)
        elif args.cmd == "note":
            box.note(box.resolve(args.id), args.text)
        elif args.cmd == "check":
            for item_id in box.check():
                print(f"closed {item_id}")
        elif args.cmd == "run":
            for item_id in box.run(dry_run=args.dry_run):
                print(("would run " if args.dry_run else "ran ") + item_id)
        elif args.cmd == "render":
            target = args.root / "work" / "inbox.md"
            target.write_text(box.render(), encoding="utf-8")
            print(f"{target.relative_to(args.root)} regenerated: {len(box.open_items())} open")
        elif args.cmd == "validate":
            problems = box.validate()
            for line in problems:
                print(line, file=sys.stderr)
            return 1 if problems else 0
        elif args.cmd == "sync":
            return _sync(args.root, actor, push=not args.no_push)
    except (KeyError, ValueError, PermissionError, json.JSONDecodeError) as exc:
        print(f"inbox: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
