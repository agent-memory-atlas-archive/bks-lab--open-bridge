#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Workplace: plan the day's work as workspaces with one agent tab per task, and steer the tabs.

The plan is CORE and knows no terminal: which active task gets a tab, in which
workspace, whether its tab is already open, whether an earlier session can be
resumed, and what is blocked or resting. Everything a terminal does (list tabs,
open them, type into one, rename one) goes through a DRIVER, so the same Bridge
works with a terminal multiplexer, with another one, or with none at all.

    python3 scripts/workplace.py propose [--json]      # what /briefing shows
    python3 scripts/workplace.py open [--only A,B] [--resume]        # dry run
    python3 scripts/workplace.py open --yes            # hand the plan to the driver
    python3 scripts/workplace.py status                # every tab: task, state, last line
    python3 scripts/workplace.py send TAB TEXT...      # type into one tab
    python3 scripts/workplace.py adopt TAB SLUG        # name an existing tab after a task

CONFIG lives in bridge-config.yaml under `workplace:`:

    workplace:
      driver: none                       # or {command: ["python3", "path/to/driver.py"]}
      workspaces:                        # first match wins: slugs, then contexts, then default
        - {name: Bigcorp, contexts: [bigcorp], color: "#1565C0"}
        - {name: Platform, slugs: ["platform-*"]}
        - {name: Misc, default: true}
      limits: {max_workspaces: 4, max_tabs: 3, stale_days: 10, activity_days: 7}
      tab_names: {payments-incident: Payments}
      agent: {new: "claude -n {slug} {prompt}", resume: "claude --resume {session}"}

DRIVER PROTOCOL. A driver is a command. It gets one JSON object on stdin with a
`verb` and answers one JSON object on stdout, the shape agents/_runtime/approval.py
uses for owner approval:

    {"verb": "tabs"}                       -> {"tabs": [{"name", "workspace", "ref", "state", "last"}]}
                                              state: working | waiting | needs-you | shell
    {"verb": "sessions"}                   -> {"sessions": {"<tab name>": "<session id>"}}
    {"verb": "open", "plan": {...}, "only": [...] | null, "resume": bool, "here": ref | null}
                                           -> {"report": ["line", ...]}
    {"verb": "send", "tab": ref, "text": "..."}       -> {"report": [...]}
    {"verb": "rename", "tab": ref, "title": "..."}    -> {"report": [...]}

A driver never closes a tab or a workspace. A driver that fails or answers
nonsense is reported, never raised, and never read as "no tab is open":
`open --yes` refuses and `status` says the driver failed. Model: docs/workplace.md.
The contract lives in scripts/tests/test_workplace.py.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ACTIVE = ("doing", "review")
PRIORITY_BONUS = {"P0": 3, "P1": 2, "P2": 1}
ROW_CAP = 10            # a slug named in every log row must not drown the rest
LABEL_MAX = 30
DRIVER_TIMEOUT_SEC = 120
DEFAULT_LIMITS = {"max_workspaces": 4, "max_tabs": 3, "stale_days": 10, "activity_days": 7}
DEFAULT_AGENT = {"new": "claude -n {slug} {prompt}", "resume": "claude --resume {session}"}
NEW_TAB_PROMPT = (
    "You are the tab for the task {slug}. Get a short overview: read {status_path}, the rows about "
    "{slug} in work/log.md (grep) and its recent commits (git log --oneline -5 -- {task_dir}), and the "
    "open inbox items for it (python3 scripts/inbox.py list). Then print at most eight lines: state, open "
    "points, next step, and whether you could take it without asking. Then wait; on 'go on' take the "
    "next step. Never close a tab or a workspace.")


# ---------------------------------------------------------------- tasks

def frontmatter(text: str) -> dict:
    parts = re.split(r"^---\s*$", text, maxsplit=2, flags=re.M)
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}


def _date(value) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def heading(text: str) -> str:
    parts = re.split(r"^---\s*$", text, maxsplit=2, flags=re.M)
    body = parts[2] if len(parts) == 3 else text
    match = re.search(r"^# (.+)$", body, flags=re.M)
    return match.group(1).strip() if match else ""


def tab_label(task: dict, cfg: dict) -> str:
    override = (cfg.get("tab_names") or {}).get(task["slug"])
    if override:
        return override
    text = re.split(r" [—–] | \(", task.get("heading") or "")[0].strip()
    if not text:
        return task["slug"]
    if len(text) <= LABEL_MAX:
        return text
    return text[:LABEL_MAX].rsplit(" ", 1)[0].rstrip(",:;") + "…"


def collect_tasks(root: Path) -> list:
    tasks = []
    for kind in ("tasks", "streams"):
        for status in sorted((root / "work" / kind).glob("*/STATUS.md")):
            if status.parent.name.startswith("_"):
                continue
            text = status.read_text(encoding="utf-8")
            fm = frontmatter(text)
            if fm.get("status") not in ACTIVE:
                continue
            tasks.append({
                "slug": fm.get("slug") or status.parent.name, "kind": kind, "status": fm.get("status"),
                "context": fm.get("context"), "priority": fm.get("priority"),
                "blocked_by": fm.get("blocked_by"), "updated": _date(fm.get("last_updated")),
                "status_path": str(status.relative_to(root)), "heading": heading(text),
            })
    return tasks


def workspace_for(task: dict, cfg: dict) -> dict:
    spaces = cfg.get("workspaces") or []
    for ws in spaces:
        if any(fnmatch.fnmatch(task["slug"], p) for p in ws.get("slugs") or []):
            return ws
    for ws in spaces:
        if task.get("context") and task["context"] in (ws.get("contexts") or []):
            return ws
    return next((ws for ws in spaces if ws.get("default")), {"name": "Work"})


ROW_RE = re.compile(r"^\|\s*(\d{4}-\d{2}-\d{2})[ T]\d{2}:\d{2}\s*\|(.*)$")


def log_mentions(log_text: str, slugs: list, today: dt.date, days: int) -> dict:
    since = today - dt.timedelta(days=days)
    pats = {s: re.compile(rf"(?<![\w-]){re.escape(s)}(?![\w-])") for s in slugs}
    out: dict = {}
    for line in log_text.splitlines():
        match = ROW_RE.match(line)
        day = _date(match.group(1)) if match else None
        if not match or not day or day < since:
            continue
        for slug, pat in pats.items():
            if pat.search(match.group(2)):
                entry = out.setdefault(slug, {"rows": 0, "last": day})
                entry["rows"] += 1
                entry["last"] = max(entry["last"], day)
    return out


def _score(task: dict, mention: dict | None, today: dt.date) -> tuple:
    last = max(d for d in (task.get("updated"), (mention or {}).get("last"), dt.date.min) if d)
    age = (today - last).days
    recency = 3 if age <= 1 else 1 if age <= 3 else 0
    rows = min((mention or {}).get("rows", 0), ROW_CAP)
    return rows + recency + PRIORITY_BONUS.get(task.get("priority") or "", 0), age


def tab_command(tab: dict, root: Path, cwd: str, cfg: dict) -> str:
    agent = {**DEFAULT_AGENT, **(cfg.get("agent") or {})}
    if tab["action"] == "resume":
        run = agent["resume"].format(session=shlex.quote(tab["session_id"]), slug=shlex.quote(tab["slug"]))
    else:
        status_path = tab.get("status_path") or ""
        prompt = NEW_TAB_PROMPT.format(slug=tab["slug"], status_path=status_path,
                                       task_dir=str(Path(status_path).parent))
        run = agent["new"].format(slug=shlex.quote(tab["slug"]), prompt=shlex.quote(prompt))
    return f"cd -- {shlex.quote(cwd)} && {run}"


# ---------------------------------------------------------------- the plan

def propose(tasks: list, cfg: dict, mentions: dict, sessions: dict, open_tabs: dict,
            today: dt.date, root: Path) -> dict:
    """sessions and open_tabs are keyed by slug; open_tabs values are driver tab dicts."""
    limits = {**DEFAULT_LIMITS, **(cfg.get("limits") or {})}
    blocked, stale, groups = [], [], {}
    for task in tasks:
        score, age = _score(task, mentions.get(task["slug"]), today)
        entry = {**task, "score": score, "age": age, "rows": (mentions.get(task["slug"]) or {}).get("rows", 0)}
        if task.get("blocked_by"):
            blocked.append(entry)
        elif age > limits["stale_days"] and task["slug"] not in open_tabs:
            stale.append(entry)
        else:
            ws = workspace_for(task, cfg)
            groups.setdefault(ws["name"], {"ws": ws, "tasks": []})["tasks"].append(entry)

    ranked = []
    for name, group in groups.items():
        group["tasks"].sort(key=lambda t: (-t["score"], t["age"], t["slug"]))
        top = group["tasks"][: limits["max_tabs"]]
        ranked.append((sum(t["score"] for t in top), name, group, top))
    ranked.sort(key=lambda r: (-r[0], r[1]))

    workspaces, deferred = [], []
    for i, (score, name, group, top) in enumerate(ranked):
        if i >= limits["max_workspaces"]:
            deferred += group["tasks"]
            continue
        ws = group["ws"]
        cwd = str(ws.get("cwd") or root)
        tabs = []
        for t in top:
            action = "open" if t["slug"] in open_tabs else "resume" if t["slug"] in sessions else "new"
            tab = {"slug": t["slug"], "label": tab_label(t, cfg), "action": action, "score": t["score"],
                   "rows": t["rows"], "age": t["age"], "status_path": t.get("status_path")}
            if action == "open":
                tab.update({k: open_tabs[t["slug"]].get(k) for k in ("ref", "workspace", "ws_ref")})
            else:
                if action == "resume":
                    tab["session_id"] = sessions[t["slug"]]
                tab["command"] = tab_command(tab, root, cwd, cfg)
            tabs.append(tab)
        workspaces.append({"name": name, "score": score, "tabs": tabs, "cwd": cwd,
                           **{k: ws[k] for k in ("color", "description", "aliases") if ws.get(k)}})
        deferred += group["tasks"][limits["max_tabs"]:]
    deferred.sort(key=lambda t: (-t["score"], t["slug"]))
    return {"date": today.isoformat(), "control": cfg.get("control") or {"name": "Control"},
            "workspaces": workspaces, "deferred": deferred, "blocked": blocked,
            "stale": sorted(stale, key=lambda t: -t["age"])}


def slug_index(tasks: list, cfg: dict) -> dict:
    index = {}
    for t in tasks:
        index[t["slug"]] = t["slug"]
        index.setdefault(tab_label(t, cfg), t["slug"])
    return index


def build_plan(root: Path, cfg: dict, today: dt.date, driver) -> dict:
    limits = {**DEFAULT_LIMITS, **(cfg.get("limits") or {})}
    tasks = collect_tasks(root)
    log_path = root / "work" / "log.md"
    log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    mentions = log_mentions(log, [t["slug"] for t in tasks], today, limits["activity_days"])
    index = slug_index(tasks, cfg)
    # A driver that failed does NOT mean "no tab is open": planning on that would
    # mark every open task as new and open it a second time. The plan records the
    # failure and `open --yes` refuses to act on it.
    tab_list = driver.tabs_or_none()
    session_map = driver.sessions_or_none()
    sessions = {index[name]: sid for name, sid in (session_map or {}).items() if name in index}
    open_tabs = {index[t["name"]]: t for t in (tab_list or []) if t.get("name") in index}
    plan = propose(tasks, cfg, mentions, sessions, open_tabs, today, root)
    if tab_list is None:
        plan["driver_error"] = getattr(driver, "error", "") or f"driver {driver.name} gave no tab list"
    return plan


def render(plan: dict) -> str:
    out = [f"Workplace today ({plan['date']}), steered from “{plan['control']['name']}”", ""]
    for i, ws in enumerate(plan["workspaces"], 1):
        out.append(f"{i}. {ws['name']}")
        for t in ws["tabs"]:
            why = f"{t['rows']} log rows, last {t['age']} d ago"
            out.append(f"     {t['label']:<32} {t['action']:<7} {t['slug']:<34} {why}")
    if plan["deferred"]:
        out += ["", "No tab today: " + ", ".join(t["slug"] for t in plan["deferred"])]
    if plan["blocked"]:
        out.append("Blocked: " + ", ".join(f"{t['slug']} ({str(t['blocked_by'])[:50]})" for t in plan["blocked"]))
    if plan["stale"]:
        out.append("Resting (park?): " + ", ".join(f"{t['slug']} ({t['age']} d)" for t in plan["stale"]))
    return "\n".join(out)


def status_rows(root: Path, cfg: dict, driver) -> list | None:
    """Rows for every tab, or None when the driver could not say (never an empty "all quiet")."""
    tabs = driver.tabs_or_none()
    if tabs is None:
        return None
    index = slug_index(collect_tasks(root), cfg)
    order = {"needs-you": 0, "waiting": 1, "working": 2, "shell": 3}
    rows = [{**t, "slug": index.get(t.get("name", ""))} for t in tabs]
    return sorted(rows, key=lambda r: (order.get(r.get("state"), 9), r.get("workspace") or ""))


# ---------------------------------------------------------------- drivers

class NoneDriver:
    """No terminal integration: nothing is open, nothing can be typed into, the plan says what to start."""

    name = "none"
    error = ""

    def tabs_or_none(self):
        return self.tabs()

    def sessions_or_none(self):
        return self.sessions()

    def tabs(self) -> list:
        return []

    def sessions(self) -> dict:
        return {}

    def open(self, plan: dict, only, resume: bool, here) -> list:
        lines = ["No driver configured (workplace.driver): start these yourself, one terminal each."]
        for ws in plan["workspaces"]:
            if only and ws["name"] not in only:
                continue
            lines.append(f"{ws['name']}:")
            for t in ws["tabs"]:
                if t.get("command") and (resume or t["action"] != "resume"):
                    lines.append(f"  {t['label']}: {t['command']}")
        return lines

    def send(self, tab: str, text: str) -> list:
        return [f"No driver configured: type into {tab} yourself."]

    def rename(self, tab: str, title: str) -> list:
        return [f"No driver configured: name the tab {title!r} yourself."]


class CommandDriver:
    """A driver behind a command that speaks the JSON protocol in the module docstring."""

    def __init__(self, argv: list):
        self.argv = [str(a) for a in argv]
        self.name = Path(self.argv[-1]).stem if self.argv else "command"
        self.error = ""

    def _call(self, payload: dict) -> dict | None:
        try:
            done = subprocess.run(self.argv, input=json.dumps(payload, default=str, ensure_ascii=False),
                                  capture_output=True, text=True, timeout=DRIVER_TIMEOUT_SEC)
        except (OSError, subprocess.SubprocessError) as exc:
            self.error = f"driver {self.name} failed to run: {exc}"
            return None
        if done.returncode != 0:
            self.error = f"driver {self.name} failed (exit {done.returncode}): {done.stderr.strip()[:200]}"
            return None
        try:
            lines = done.stdout.strip().splitlines()
            data = json.loads(lines[-1]) if lines else {}
        except ValueError:
            self.error = f"driver {self.name} failed: no JSON answer"
            return None
        return data if isinstance(data, dict) else None

    def tabs_or_none(self) -> list | None:
        data = self._call({"verb": "tabs"})
        tabs = (data or {}).get("tabs") if data is not None else None
        if not isinstance(tabs, list):
            if data is not None:
                self.error = f"driver {self.name} answered no tab list"
            return None
        return [t for t in tabs if isinstance(t, dict)]

    def sessions_or_none(self) -> dict | None:
        data = self._call({"verb": "sessions"})
        sessions = (data or {}).get("sessions", {}) if data is not None else None
        if not isinstance(sessions, dict):
            if data is not None:
                self.error = f"driver {self.name} answered sessions that are not a mapping"
            return None
        return sessions

    def tabs(self) -> list:
        return self.tabs_or_none() or []

    def sessions(self) -> dict:
        return self.sessions_or_none() or {}

    def _report(self, payload: dict) -> list:
        data = self._call(payload)
        if data is None:
            return [getattr(self, "error", f"driver {self.name} failed")]
        return [str(line) for line in data.get("report") or []]

    def open(self, plan: dict, only, resume: bool, here) -> list:
        return self._report({"verb": "open", "plan": plan, "only": sorted(only) if only else None,
                             "resume": resume, "here": here})

    def send(self, tab: str, text: str) -> list:
        return self._report({"verb": "send", "tab": tab, "text": text})

    def rename(self, tab: str, title: str) -> list:
        return self._report({"verb": "rename", "tab": tab, "title": title})


def driver_from(spec):
    if spec in (None, "none"):
        return NoneDriver()
    if isinstance(spec, dict):
        argv = spec.get("command")
        if isinstance(argv, list) and argv and all(isinstance(a, str) for a in argv):
            return CommandDriver([a.replace("${root}", str(ROOT)) for a in argv])
    raise ValueError(f"workplace.driver must be 'none' or {{command: [argv]}}, got {spec!r}")


def load_cfg(root: Path) -> dict:
    path = root / "bridge-config.yaml"
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("workplace") or {}


def find_tab(tabs: list, name: str, index: dict) -> dict:
    want = name.lower()
    exact = [t for t in tabs if str(t.get("name", "")).lower() == want or str(index.get(t.get("name"))) == name]
    if len(exact) == 1:
        return exact[0]
    part = [t for t in tabs if want in str(t.get("name", "")).lower()]
    if len(part) == 1:
        return part[0]
    raise LookupError(f"no single tab for {name!r} ({len(exact) or len(part)} matches)")


# ---------------------------------------------------------------- CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="workplace.py", description="Plan and steer the day's agent tabs.")
    ap.add_argument("--root", type=Path, default=ROOT)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("propose").add_argument("--json", action="store_true")
    op = sub.add_parser("open")
    op.add_argument("--only", help="only these workspaces, comma separated")
    op.add_argument("--yes", action="store_true", help="hand the plan to the driver (default: dry run)")
    op.add_argument("--resume", action="store_true", help="also reopen tabs of earlier sessions")
    op.add_argument("--here", help="driver ref of the calling tab, which becomes the control tab")
    sub.add_parser("status").add_argument("--json", action="store_true")
    sd = sub.add_parser("send")
    sd.add_argument("tab")
    sd.add_argument("text", nargs="+")
    ad = sub.add_parser("adopt")
    ad.add_argument("tab")
    ad.add_argument("slug")
    args = ap.parse_args(argv)

    cfg = load_cfg(args.root)
    try:
        driver = driver_from(cfg.get("driver"))
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    today = dt.date.today()

    if args.cmd == "propose":
        plan = build_plan(args.root, cfg, today, driver)
        print(json.dumps(plan, default=str, ensure_ascii=False, indent=1) if args.json else render(plan))
        if plan.get("driver_error"):
            print(f"Warning: open tabs unknown ({plan['driver_error']}); every task shows as new.",
                  file=sys.stderr)
        return 0
    if args.cmd == "open":
        plan = build_plan(args.root, cfg, today, driver)
        only = set(args.only.split(",")) if args.only else None
        if plan.get("driver_error"):
            print(f"Open tabs are unknown ({plan['driver_error']}): not opening anything, "
                  "it could open a task a second time.", file=sys.stderr)
            return 1 if args.yes else 0
        if not args.yes:
            print(f"Dry run with driver {driver.name}; add --yes to open:")
            for ws in plan["workspaces"]:
                if only and ws["name"] not in only:
                    continue
                for t in ws["tabs"]:
                    if t["action"] == "open":
                        print(f"  {ws['name']}: {t['label']} is open already")
                    elif args.resume or t["action"] != "resume":
                        print(f"  {ws['name']}: {t['action']} {t['label']}")
            return 0
        print("\n".join(driver.open(plan, only, args.resume, args.here)))
        return 0
    if args.cmd == "status":
        rows = status_rows(args.root, cfg, driver)
        if rows is None:
            print(getattr(driver, "error", "") or f"driver {driver.name} failed", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=1))
        elif not rows:
            print(f"No tabs known to driver {driver.name}.")
        else:
            for i, r in enumerate(rows, 1):
                print(f"{i:>2}  {str(r.get('workspace'))[:12]:<12} {str(r.get('name'))[:34]:<34} "
                      f"{str(r.get('state')):<9} {str(r.get('last') or '')[:80]}")
        return 0
    tasks = collect_tasks(args.root)
    index = slug_index(tasks, cfg)
    tabs = driver.tabs()
    try:
        tab = find_tab(tabs, args.tab, index) if tabs else {"name": args.tab, "ref": args.tab}
    except LookupError as exc:
        print(exc, file=sys.stderr)
        return 1
    if args.cmd == "adopt":
        task = next((t for t in tasks if t["slug"] == args.slug), None)
        if not task:
            print(f"no active task {args.slug}", file=sys.stderr)
            return 1
        print("\n".join(driver.rename(tab.get("ref") or tab["name"], tab_label(task, cfg))))
        return 0
    print("\n".join(driver.send(tab.get("ref") or tab["name"], " ".join(args.text))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
