#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""cmux as a workplace driver for scripts/workplace.py.

The plan (which task, which workspace, new or resumed) belongs to CORE
(scripts/workplace.py, docs/workplace.md). This script is only what cmux can do:
list the tabs, open the plan, type into a tab, rename a tab. It speaks the CORE
JSON protocol: one request on stdin, one answer on stdout.

    {"verb": "tabs"}       -> {"tabs": [{"name", "workspace", "ref", "ws_ref", "state", "last"}]}
    {"verb": "sessions"}   -> {"sessions": {"<tab title>": "<agent session id>"}}
    {"verb": "open", "plan": {...}, "only": [...] | null, "resume": bool, "here": ref | null}
    {"verb": "send", "tab": ref, "text": "..."}
    {"verb": "rename", "tab": ref, "title": "..."}

Wire it in bridge-config.yaml:

    workplace:
      driver: {command: ["python3", "${root}/skills/cmux/scripts/cmux_driver.py"]}

Rules: it never closes a tab or a workspace. A tab already open is reused, never
opened twice. When cmux is missing or gives no readable answer, the driver exits
non-zero with {"error": "..."} on stdout and the reason on stderr, so CORE reads
the tab view as UNKNOWN, never as "no tab is open".
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cmux_layout as cl  # noqa: E402

ROOT = cl.BRIDGE_ROOT
HOOKS_FILE = Path(os.environ.get("CMUX_HOOKS_FILE", Path.home() / ".cmuxterm/claude-hook-sessions.json"))
PERMISSION_EVENTS = ("Notification", "PermissionRequest")
SPINNER = set("◐◓◑◒")   # quarter-circle spinner; Braille is matched by range
IDLE_GLYPH = "✳"                        # eight-spoked asterisk: the agent is idle
KEEP_SHELL = cl.KEEP_SHELL


class DriverError(RuntimeError):
    """cmux gave no answer the driver can trust."""


# ---------------------------------------------------------------- reading cmux

def _load_json(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _glyph(title: str) -> str | None:
    head = (title or "").lstrip()[:1]
    if head == IDLE_GLYPH:
        return "idle"
    if head in SPINNER or (head and 0x2800 <= ord(head) <= 0x28FF):
        return "busy"
    return None


def live_tabs(session: dict, hooks: dict) -> list[dict]:
    """Terminal tabs from cmux's session file, with state and last line from the hook file.

    The state is in the CORE vocabulary: needs-you, waiting, working, shell.
    """
    by_surface = hooks.get("activeSessionsBySurface") or {}
    sessions = hooks.get("sessions") or {}
    tabs = []
    for window in session.get("windows") or []:
        for ws in (window.get("tabManager") or {}).get("workspaces") or []:
            ws_title = ws.get("customTitle") or cl.strip_status_glyph(ws.get("processTitle") or "")
            panels = {p.get("id"): p for p in ws.get("panels") or []}
            order = [pid for pane in cl._panel_ids_in_order(ws.get("layout") or {}) for pid in pane]
            order += [pid for pid in panels if pid not in order]
            for pid in order:
                p = panels.get(pid)
                if not p or p.get("type", "terminal") != "terminal":
                    continue
                raw = p.get("title") or ""
                hook = sessions.get((by_surface.get(pid) or {}).get("sessionId") or "") or {}
                glyph = _glyph(raw)
                if glyph is None:
                    state = "shell"
                elif hook.get("hookEventName") in PERMISSION_EVENTS:
                    state = "needs-you"
                else:
                    state = "waiting" if glyph == "idle" else "working"
                tabs.append({"workspace": ws_title, "ws_ref": ws.get("workspaceId"),
                             "surface": pid, "state": state,
                             "title": p.get("customTitle") or cl.strip_status_glyph(raw),
                             "last": (hook.get("lastBody") or "").replace("\n", " ")[:90]})
    return tabs


def socket_tabs(tree: dict) -> list[dict]:
    """Terminal tabs from `cmux tree --json`: live, unlike the session file,
    which cmux writes with a delay."""
    tabs = []
    for window in tree.get("windows") or []:
        for ws in window.get("workspaces") or []:
            for pane in ws.get("panes") or []:
                for sf in pane.get("surfaces") or []:
                    if sf.get("type") != "terminal":
                        continue
                    tabs.append({"workspace": ws.get("title") or "", "ws_ref": ws.get("ref"),
                                 "surface": sf.get("ref"),
                                 "title": cl.strip_status_glyph(sf.get("title") or "")})
    return tabs


def current_tabs() -> list[dict]:
    """Live tab refs from the socket; the session file only when the socket gives no JSON.

    Neither readable raises DriverError: an empty list would claim no tab is open.
    """
    try:
        tree = json.loads(cl._cmux("tree", "--json"))
    except ValueError:
        tree = None
    if isinstance(tree, dict) and "windows" in tree:
        return socket_tabs(tree)
    session = _load_json(cl.DEFAULT_SOURCE)
    if "windows" not in session:
        raise DriverError("cmux socket gave no tab tree and the session file is not readable")
    return live_tabs(session, {})


def _key(tab: dict) -> tuple[str, str]:
    return (tab.get("workspace") or "", cl.strip_status_glyph(tab.get("title") or "").strip())


def tabs() -> list[dict]:
    """Live refs from the socket, state and last line from the session file and hooks.

    The socket calls a tab `surface:91`, the session file calls the same tab by a
    UUID: joining by ref matches nothing, so every tab would read as a shell.
    Tabs are joined by (workspace, title without status glyph) instead.
    """
    live = {_key(t): t for t in live_tabs(_load_json(cl.DEFAULT_SOURCE), _load_json(HOOKS_FILE))}
    out = []
    for t in current_tabs():
        info = live.get(_key(t), {})
        out.append({"name": t["title"], "workspace": t["workspace"], "ref": t["surface"],
                    "ws_ref": t.get("ws_ref"), "state": info.get("state", "shell"),
                    "last": info.get("last", "")})
    return out


def sessions_by_title(snapshots: list[dict]) -> dict[str, str]:
    """Tab title -> agent session id, the newest snapshot (first in the list) wins."""
    found: dict[str, str] = {}
    for snap in snapshots:
        for ws in cl.iter_workspaces(snap.get("layout") or {}):
            for pane in ws.get("panes") or []:
                for tab in pane:
                    if tab.get("kind") == "claude" and tab.get("session_id"):
                        found.setdefault(tab.get("title") or "", tab["session_id"])
    return found


def sessions() -> dict[str, str]:
    return sessions_by_title(cl.load_snapshots(cl.DEFAULT_DIR))


# ---------------------------------------------------------------- opening the plan

def to_cmux_plan(plan: dict) -> dict:
    """CORE plan -> the shape apply_calls expects: open tabs carry `surface`, and
    every command keeps its tab alive when the agent exits."""
    converted = {**plan, "workspaces": []}
    for ws in plan.get("workspaces") or []:
        new_tabs = []
        for t in ws.get("tabs") or []:
            tab = dict(t)
            if tab.get("action") == "open":
                tab["surface"] = tab.get("ref")
            elif tab.get("command") and not tab["command"].endswith(KEEP_SHELL):
                tab["command"] = tab["command"] + KEEP_SHELL
            new_tabs.append(tab)
        converted["workspaces"].append({**ws, "tabs": new_tabs})
    return converted


def resolve_workspace(ws: dict, existing: dict[str, str]) -> str | None:
    for name in [ws["name"], *(ws.get("aliases") or [])]:
        if name in existing:
            return existing[name]
    return None


def apply_calls(plan: dict, existing: dict[str, str], root: str, only: set[str] | None = None,
                here: str | None = None, resume: bool = False) -> list[dict]:
    """The cmux calls, in order. There is no close operation, on purpose.

    `ws` names a workspace created earlier in the list. `here` is the calling
    tab: it moves into the control workspace last, after every other workspace
    has its tabs, so no workspace is ever left empty. Tabs that would resume an
    earlier session open only when `resume` is set.
    """
    calls = []
    ctl = plan.get("control") or {"name": "Control"}
    if not resolve_workspace(ctl, existing):
        calls.append({"op": "create", "ws": ctl["name"], "cwd": root, "command": None})
    calls.append({"op": "decorate", "ws": ctl["name"], "color": ctl.get("color"),
                  "description": ctl.get("description")})
    calls.append({"op": "order", "ws": ctl["name"], "index": 0})
    for pos, ws in enumerate(plan.get("workspaces") or [], 1):
        if only and ws["name"] not in only:
            continue
        cwd = ws.get("cwd") or root
        names = {ws["name"], *(ws.get("aliases") or [])}
        opened = [t for t in ws["tabs"] if t["action"] == "open"]
        wanted = [t for t in ws["tabs"] if resume or t["action"] != "resume"]
        new = [t for t in wanted if t["action"] != "open" and t.get("command")]
        ref = resolve_workspace(ws, existing)
        if not ref and new:
            first, new = new[0], new[1:]
            calls.append({"op": "create", "ws": ws["name"], "cwd": cwd, "slug": first["slug"],
                          "command": first["command"], "tab": first["label"]})
        calls.append({"op": "decorate", "ws": ws["name"], "ref": ref, "color": ws.get("color"),
                      "description": ws.get("description")})
        calls.append({"op": "order", "ws": ws["name"], "ref": ref, "index": pos})
        for t in opened:
            moved = t.get("workspace") not in names
            if moved:
                calls.append({"op": "move", "ws": ws["name"], "ref": ref, "surface": t["surface"],
                              "tab": t["label"], "from": t.get("workspace")})
            rename = {"op": "rename", "ws": ws["name"], "surface": t["surface"], "tab": t["label"]}
            if not moved and t.get("ws_ref"):
                rename["ws_ref"] = t["ws_ref"]
            calls.append(rename)
        for t in new:
            calls.append({"op": "tab", "ws": ws["name"], "ref": ref, "slug": t["slug"],
                          "command": t["command"], "tab": t["label"]})
        calls.append({"op": "tab_order", "ws": ws["name"], "ref": ref,
                      "slugs": [t["slug"] for t in wanted],
                      "known": {t["slug"]: t["surface"] for t in opened}})
    if here:
        calls.append({"op": "move", "ws": ctl["name"], "surface": here, "tab": ctl["name"],
                      "from": "this tab"})
        calls.append({"op": "rename", "ws": ctl["name"], "surface": here, "tab": ctl["name"]})
    return calls


def rename_tab(surface: str, ws_ref: str | None, title: str) -> str:
    """cmux resolves a tab relative to a workspace (default: the caller's), so a
    tab in another workspace is only renamed with --workspace."""
    args = ["tab-action", "--action", "rename", "--tab", surface, "--title", title]
    if ws_ref:
        args += ["--workspace", ws_ref]
    return cl._cmux(*args)


def run_calls(calls: list[dict], existing: dict[str, str]) -> list[str]:
    refs = dict(existing)
    surfaces: dict[str, str] = {}  # slug -> surface ref of tabs created here
    report = []
    for c in calls:
        ws_ref = c.get("ref") or refs.get(c["ws"])
        if c["op"] == "create":
            args = ["workspace", "create", "--name", c["ws"], "--cwd", c["cwd"], "--focus", "false"]
            if c.get("command"):
                args += ["--command", cl.ascii_command(c["command"])]
            out = cl._cmux(*args)
            ws_ref = cl.parse_ref(out, "workspace")
            if not ws_ref:
                report.append(f"ERROR workspace {c['ws']} not created: {out.strip()[:120]}")
                continue
            refs[c["ws"]] = ws_ref
            if c.get("tab"):
                sref = cl._first_surface(ws_ref)
                if sref:
                    rename_tab(sref, ws_ref, c["tab"])
                    surfaces[c["slug"]] = sref
            report.append(f"created {c['ws']} ({ws_ref})" + (f" with {c['tab']}" if c.get("tab") else ""))
        elif c["op"] == "rename":
            rename_tab(c["surface"], c.get("ws_ref") or refs.get(c["ws"]), c["tab"])
        elif not ws_ref:
            report.append(f"skipped {c['op']} {c['ws']}: workspace missing")
        elif c["op"] == "decorate":
            cl._cmux("workspace", "rename", ws_ref, "--title", c["ws"])
            for cmd in cl.decoration_commands(ws_ref, c):
                cl._cmux(*cmd)
        elif c["op"] == "move":
            cl._cmux("move-surface", "--surface", c["surface"], "--workspace", ws_ref, "--focus", "false")
            report.append(f"  moved {c['tab']}: {c.get('from')} -> {c['ws']}")
        elif c["op"] == "tab_order":
            known = {**c.get("known", {}), **surfaces}
            for i, slug in enumerate(s for s in c["slugs"] if s in known):
                cl._cmux("reorder-surface", "--surface", known[slug], "--index", str(i))
        elif c["op"] == "order":
            cl._cmux("reorder-workspace", "--workspace", ws_ref, "--index", str(c["index"]))
        elif c["op"] == "tab":
            sref = cl.parse_ref(cl._cmux("new-surface", "--workspace", ws_ref, "--command",
                                         cl.ascii_command(c["command"]), "--focus", "false"), "surface")
            if sref:
                rename_tab(sref, ws_ref, c["tab"])
                surfaces[c["slug"]] = sref
                report.append(f"  tab {c['tab']} in {c['ws']} ({sref})")
            else:
                report.append(f"  ERROR tab {c['tab']} in {c['ws']}")
    return report


# ---------------------------------------------------------------- verbs

def open_plan(req: dict) -> list[str]:
    plan = to_cmux_plan(req.get("plan") or {})
    existing = cl.existing_workspace_titles()
    only = set(req["only"]) if req.get("only") else None
    calls = apply_calls(plan, existing, str(ROOT), only, req.get("here"), bool(req.get("resume")))
    return run_calls(calls, existing)


def _ws_ref_of(surface: str) -> str | None:
    return next((t.get("ws_ref") for t in current_tabs() if t["surface"] == surface), None)


def send(req: dict) -> list[str]:
    surface, text = req["tab"], req["text"]
    ws_ref = _ws_ref_of(surface)
    where = ["--workspace", ws_ref] if ws_ref else []
    cl._cmux("send", *where, "--surface", surface, text)
    cl._cmux("send-key", *where, "--surface", surface, "Enter")
    return [f"sent to {surface}"]


def rename(req: dict) -> list[str]:
    rename_tab(req["tab"], _ws_ref_of(req["tab"]), req["title"])
    return [f"{req['tab']} is now named {req['title']!r}"]


def handle(req: dict) -> dict:
    if shutil.which("cmux") is None:
        raise DriverError("cmux is not installed (no `cmux` on PATH)")
    verb = req.get("verb")
    if verb == "tabs":
        return {"tabs": tabs()}
    if verb == "sessions":
        return {"sessions": sessions()}
    if verb == "open":
        return {"report": open_plan(req)}
    if verb == "send":
        return {"report": send(req)}
    if verb == "rename":
        return {"report": rename(req)}
    raise ValueError(f"unknown verb {verb!r}")


def main() -> int:
    try:
        req = json.loads(sys.stdin.read() or "{}")
        if not isinstance(req, dict):
            raise ValueError("request is not a JSON object")
        answer = handle(req)
    except (DriverError, cl.CmuxUnavailable, ValueError, KeyError) as exc:
        message = f"cmux_driver: {exc}"
        print(json.dumps({"error": message}))
        print(message, file=sys.stderr)
        return 1
    print(json.dumps(answer, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
