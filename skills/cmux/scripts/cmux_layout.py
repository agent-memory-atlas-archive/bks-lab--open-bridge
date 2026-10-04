#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""cmux layout snapshots: keep several generations of the workspace and tab
layout, and rebuild it after cmux loses workspaces.

cmux keeps exactly one backup generation (session-*-previous.json) and has lost
whole workspaces on relaunch without a trace in its closed-item history
(manaflow-ai/cmux #2387, #8267; multi-generation snapshots are the open request
#2086). This script reads cmux's own session file directly, so it runs from a
scheduled job without the cmuxOnly socket, and writes a compact snapshot only
when the structure changed.

    cmux_layout.py snapshot                 # scheduled: write if changed, prune old
    cmux_layout.py list                     # newest first, with counts
    cmux_layout.py show [SNAP]              # workspaces and tabs of one snapshot
    cmux_layout.py restore [SNAP]           # dry run: what would be rebuilt
    cmux_layout.py restore [SNAP] --apply   # run inside cmux (needs the socket)

SNAP is a file name, a path, or an index from `list` (0 = newest).

Environment:
    CMUX_SESSION_FILE   cmux's session file (default: the macOS location)
    CMUX_LAYOUT_DIR     where snapshots go (default ~/.local/state/cmux-layouts)
    CMUX_LAYOUT_NOTIFY  optional executable that delivers the loss alarm, called
                        with --what --where --do --detail (for example a thin
                        wrapper around one of the instance's infra/channels/)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

# skills/cmux/scripts/<this file> -> the Bridge root. A Claude session started
# outside the Bridge root does not load the Bridge's AGENTS.md and registries.
BRIDGE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOURCE = Path(os.environ.get(
    "CMUX_SESSION_FILE",
    Path.home() / "Library/Application Support/cmux/session-com.cmuxterm.app.json"))
DEFAULT_DIR = Path(os.environ.get("CMUX_LAYOUT_DIR", Path.home() / ".local/state/cmux-layouts"))
KEEP_DAYS = 7
MIN_KEEP = 20
UUID_RE = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
# A tab whose only process is the agent closes (and takes an otherwise empty
# workspace with it) when the agent exits; falling back to a login shell keeps it.
KEEP_SHELL = '; exec "${SHELL:-/bin/sh}" -l'


class CmuxUnavailable(RuntimeError):
    """The cmux CLI is not installed or could not be started."""


# --- extract -----------------------------------------------------------------

def strip_status_glyph(title: str) -> str:
    """Drop the leading state glyph cmux or the agent put in front of a tab title."""
    i = 0
    while i < len(title):
        ch = title[i]
        if ch.isspace() or 0x2800 <= ord(ch) <= 0x28FF or unicodedata.category(ch) in ("So", "Sm"):
            i += 1
            continue
        break
    return title[i:]


def _panel_ids_in_order(node) -> list[list[str]]:
    """Walk a cmux layout tree and return the panel ids per pane, left to right."""
    if not isinstance(node, dict):
        return []
    if node.get("type") == "pane" or "pane" in node:
        ids = (node.get("pane") or {}).get("panelIds") or []
        return [list(ids)] if ids else []
    panes: list[list[str]] = []
    for value in node.values():
        if isinstance(value, dict):
            children = value.get("children")
            if isinstance(children, list):
                for child in children:
                    panes.extend(_panel_ids_in_order(child))
            else:
                panes.extend(_panel_ids_in_order(value))
        elif isinstance(value, list):
            for child in value:
                panes.extend(_panel_ids_in_order(child))
    return panes


def _tab(panel: dict, tty_sessions: dict[str, str] | None = None) -> dict:
    kind = panel.get("type", "terminal")
    tab = {"kind": kind, "title": strip_status_glyph(panel.get("title") or "")}
    if kind == "browser":
        tab["url"] = (panel.get("browser") or {}).get("urlString")
    elif kind == "markdown":
        tab["path"] = (panel.get("markdown") or {}).get("filePath")
    else:
        term = panel.get("terminal") or {}
        agent = term.get("agent") or {}
        binding = term.get("resumeBinding") or {}
        tab["cwd"] = (agent.get("workingDirectory") or binding.get("cwd")
                      or term.get("workingDirectory") or panel.get("directory"))
        sid = agent.get("sessionId") or binding.get("checkpointId")
        if not ((agent.get("kind") or binding.get("kind")) == "claude" and sid):
            # cmux does not always bind a resumed claude; the tty still knows
            sid = (tty_sessions or {}).get(panel.get("ttyName") or "")
        if sid:
            tab["kind"] = "claude"
            tab["session_id"] = sid
        else:
            tab["kind"] = "terminal"
    return tab


def extract_layout(session: dict, tty_sessions: dict[str, str] | None = None) -> dict:
    windows = []
    for window in session.get("windows") or []:
        workspaces = []
        for ws in (window.get("tabManager") or {}).get("workspaces") or []:
            panels = {p.get("id"): p for p in ws.get("panels") or []}
            panes = _panel_ids_in_order(ws.get("layout") or {})
            seen = {pid for pane in panes for pid in pane}
            rest = [pid for pid in panels if pid not in seen]
            if rest:
                if panes:
                    panes[-1].extend(rest)
                else:
                    panes = [rest]
            tabs = [[_tab(panels[pid], tty_sessions) for pid in pane if pid in panels] for pane in panes]
            entry = {
                "title": ws.get("customTitle") or strip_status_glyph(ws.get("processTitle") or ""),
                "cwd": ws.get("currentDirectory"),
                "panes": [p for p in tabs if p],
            }
            if ws.get("customColor"):
                entry["color"] = ws["customColor"]
            if ws.get("customDescription"):
                entry["description"] = ws["customDescription"]
            workspaces.append(entry)
        windows.append({"workspaces": workspaces})
    return {"windows": windows}


def iter_workspaces(layout: dict):
    for window in layout.get("windows") or []:
        yield from window.get("workspaces") or []


def summarize(layout: dict) -> dict:
    tabs = [t for ws in iter_workspaces(layout) for pane in ws["panes"] for t in pane]
    return {"workspaces": sum(1 for _ in iter_workspaces(layout)),
            "tabs": len(tabs),
            "claude": sum(1 for t in tabs if t["kind"] == "claude")}


def fingerprint(layout: dict) -> str:
    """Structure only: tab titles churn with every agent turn and must not
    produce a snapshot on their own."""
    def strip(o):
        if isinstance(o, dict):
            return {k: strip(v) for k, v in o.items() if not (k == "title" and "kind" in o)}
        if isinstance(o, list):
            return [strip(v) for v in o]
        return o
    blob = json.dumps(strip(layout), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


# --- snapshot store ----------------------------------------------------------

def _snap_order(path: Path):
    # layout-YYYYmmdd-HHMMSS[-N].json: a plain name sort puts "-1" before ".json"
    parts = path.stem.split("-")
    n = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
    return (parts[1:3], n)


def _snap_files(out_dir: Path) -> list[Path]:
    return sorted(Path(out_dir).glob("layout-*.json"), key=_snap_order)


def _load(path: Path) -> dict | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_snapshots(out_dir: Path = DEFAULT_DIR) -> list[dict]:
    """All readable snapshots, newest first."""
    snaps = [s for s in (_load(p) for p in _snap_files(out_dir)) if s]
    snaps.sort(key=lambda s: s.get("taken_at") or 0, reverse=True)
    return snaps


def snapshot(src: Path, out_dir: Path, now: float | None = None,
             keep_days: int = KEEP_DAYS, min_keep: int = MIN_KEEP,
             ttys: dict[str, str] | None = None) -> Path | None:
    """Write a snapshot if the layout structure changed. Returns the new file."""
    now = time.time() if now is None else now
    session = _load(src)
    if not isinstance(session, dict) or "windows" not in session:
        return None
    layout = extract_layout(session, tty_sessions() if ttys is None else ttys)
    fp = fingerprint(layout)
    out_dir = Path(out_dir)
    files = _snap_files(out_dir)
    if files:
        last = _load(files[-1]) or {}
        if last.get("fingerprint") == fp:
            return None
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
    path = out_dir / f"layout-{stamp}.json"
    n = 1
    while path.exists():
        path = out_dir / f"layout-{stamp}-{n}.json"
        n += 1
    record = {"taken_at": now, "source": str(src), "fingerprint": fp,
              "summary": summarize(layout), "layout": layout}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)
    prune(out_dir, now, keep_days, min_keep)
    return path


def prune(out_dir: Path, now: float, keep_days: int = KEEP_DAYS, min_keep: int = MIN_KEEP) -> int:
    """Drop snapshots older than keep_days, but always keep the newest min_keep."""
    files = _snap_files(out_dir)
    cutoff = now - keep_days * 86_400
    removable = files[:-min_keep] if min_keep else files
    removed = 0
    for f in removable:
        rec = _load(f) or {}
        if rec.get("taken_at", 0) < cutoff:
            f.unlink(missing_ok=True)
            removed += 1
    return removed


def list_snapshots(out_dir: Path) -> list[dict]:
    rows = []
    for f in reversed(_snap_files(out_dir)):
        rec = _load(f) or {}
        rows.append({"path": f, "taken_at": rec.get("taken_at"), "summary": rec.get("summary") or {}})
    return rows


def resolve_snapshot(out_dir: Path, ref: str | None) -> Path:
    rows = list_snapshots(out_dir)
    if not rows:
        raise SystemExit(f"no snapshots in {out_dir}")
    if ref is None:
        return rows[0]["path"]
    if ref.isdigit():
        return rows[int(ref)]["path"]
    p = Path(ref)
    return p if p.exists() else Path(out_dir) / ref


# --- loss alarm --------------------------------------------------------------

MIN_CLAUDE_DROP = 3
MIN_WORKSPACE_DROP = 2


def _claude_tabs(layout: dict) -> list[dict]:
    return [dict(t, workspace=ws["title"]) for ws in iter_workspaces(layout)
            for pane in ws["panes"] for t in pane if t["kind"] == "claude"]


def detect_loss(before: dict, after: dict, min_claude: int = MIN_CLAUDE_DROP,
                min_workspaces: int = MIN_WORKSPACE_DROP) -> dict | None:
    """A sharp drop between two consecutive snapshots, or None."""
    b, a = summarize(before), summarize(after)
    if (b["claude"] - a["claude"] < min_claude
            and b["workspaces"] - a["workspaces"] < min_workspaces):
        return None
    still = {t["session_id"] for t in _claude_tabs(after)}
    return {"claude_before": b["claude"], "claude_after": a["claude"],
            "workspaces_before": b["workspaces"], "workspaces_after": a["workspaces"],
            "vanished": [t for t in _claude_tabs(before) if t["session_id"] not in still]}


def loss_message(loss: dict, script: str) -> dict:
    """What happened and what to do, in plain words (no variable names, no epochs)."""
    lines = [f"{t['workspace']}: {t['title'] or '(untitled)'} ({t['session_id'][:8]})"
             for t in loss["vanished"]]
    return {
        "what": (f"cmux: agent sessions {loss['claude_before']} -> {loss['claude_after']}, "
                 f"workspaces {loss['workspaces_before']} -> {loss['workspaces_after']} "
                 "since the previous snapshot"),
        "where": "cmux",
        "do": (f"If this was not intended: in a cmux tab run `python3 {script} restore 1` to check, "
               "then add --apply to rebuild. If it was intended: nothing to do."),
        "detail": "\n".join(lines) or "no agent tabs affected, only workspaces",
    }


def notify_channel(msg: dict) -> bool | None:
    """Deliver through CMUX_LAYOUT_NOTIFY. True delivered, False failed, None not configured."""
    command = os.environ.get("CMUX_LAYOUT_NOTIFY")
    if not command:
        return None
    try:
        res = subprocess.run([command, "--what", msg["what"], "--where", msg["where"],
                              "--do", msg["do"], "--detail", msg["detail"]],
                             capture_output=True, text=True, timeout=45)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"loss alarm: notifier failed to run: {exc}", file=sys.stderr)
        return False
    return res.returncode == 0


# --- restore -----------------------------------------------------------------

def tty_sessions_from_ps(ps_output: str) -> dict[str, str]:
    """Map tty -> claude session id from `ps -Ao pid,tty,command`."""
    found = {}
    for line in ps_output.splitlines():
        m = re.match(r"\s*\d+\s+(\S+)\s+(.*)", line)
        if not m or not m.group(1).startswith("tty"):
            continue
        sid = re.search(r"--(?:session-id|resume)[ =](" + UUID_RE + ")", m.group(2))
        if sid:
            found[m.group(1)] = sid.group(1)
    return found


def _ps(fields: str) -> str:
    try:
        return subprocess.run(["ps", "-Ao", fields], capture_output=True, text=True).stdout
    except OSError:
        return ""


def tty_sessions() -> dict[str, str]:
    return tty_sessions_from_ps(_ps("pid,tty,command"))


def running_sessions_from_ps(ps_output: str) -> set[str]:
    return set(re.findall(r"--(?:session-id|resume)[ =](" + UUID_RE + ")", ps_output))


def running_sessions() -> set[str]:
    return running_sessions_from_ps(_ps("pid,command"))


def present_sessions(current_layout: dict, running: set[str]) -> set[str]:
    """Sessions that need no restore: running, or still bound to a tab in cmux's
    current layout (a hibernated agent has no process but keeps its tab)."""
    return set(running) | {t["session_id"] for t in _claude_tabs(current_layout)}


def plan_restore(layout: dict, running_sessions: set[str], existing_workspaces: set[str],
                 include_files: bool = True) -> list[dict]:
    plan = []
    for ws in iter_workspaces(layout):
        tabs, skipped = [], []
        for pane in ws["panes"]:
            for tab in pane:
                if tab["kind"] == "claude" and tab.get("session_id") in running_sessions:
                    skipped.append(tab["session_id"])
                elif tab["kind"] in ("browser", "markdown") and not include_files:
                    continue
                else:
                    tabs.append(tab)
        exists = ws["title"] in existing_workspaces
        if not tabs or (exists and not any(t["kind"] == "claude" for t in tabs)):
            continue
        step = {"title": ws["title"], "cwd": ws.get("cwd"), "create": not exists,
                "tabs": tabs, "skipped_running": skipped}
        for key in ("color", "description"):
            if ws.get(key):
                step[key] = ws[key]
        plan.append(step)
    return plan


def _sq(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def ascii_command(command: str) -> str:
    """`cmux ... --command` re-encodes every non-ASCII byte (U+00DC arrives as two
    Latin-1 characters), while `cmux send` does not. A command with non-ASCII text
    is therefore written to a UTF-8 file and sourced, so only ASCII crosses the CLI."""
    if command.isascii():
        return command
    d = Path.home() / ".cmuxterm/commands"
    d.mkdir(parents=True, exist_ok=True)
    f = d / (hashlib.sha1(command.encode("utf-8")).hexdigest()[:16] + ".sh")
    f.write_text(command + "\n", encoding="utf-8")
    return f". {_sq(str(f))}"


def tab_command(tab: dict) -> str:
    cd = "cd -- " + _sq(tab.get("cwd") or str(BRIDGE_ROOT))
    if tab["kind"] == "claude":
        return f"{cd} && claude --resume {tab['session_id']}{KEEP_SHELL}"
    return cd


def decoration_commands(ws_ref: str, step: dict) -> list[list[str]]:
    """cmux calls that put a workspace's color and description back."""
    cmds = []
    if step.get("color"):
        cmds.append(["workspace-action", "--workspace", ws_ref, "--action", "set-color",
                     "--color", step["color"]])
    if step.get("description"):
        cmds.append(["workspace-action", "--workspace", ws_ref, "--action", "set-description",
                     "--description", step["description"]])
    return cmds


def parse_ref(output: str, kind: str) -> str | None:
    m = re.search(rf"\b{kind}:\d+\b", output or "")
    return m.group(0) if m else None


def _cmux(*args: str) -> str:
    """Run the cmux CLI and return stdout + stderr. Raises CmuxUnavailable when
    the binary is missing, so a caller can tell "no cmux" from "nothing there"."""
    try:
        res = subprocess.run(["cmux", *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CmuxUnavailable(f"cmux CLI not available: {exc}") from exc
    return (res.stdout or "") + (res.stderr or "")


def existing_workspace_titles() -> dict[str, str]:
    titles = {}
    for line in _cmux("workspace", "list").splitlines():
        m = re.match(r"\s*\*?\s*(workspace:\d+)\s+(.*?)(\s+\[selected\])?\s*$", line)
        if m:
            titles[strip_status_glyph(m.group(2)).strip()] = m.group(1)
    return titles


def _first_surface(ws_ref: str) -> str | None:
    return parse_ref(_cmux("tree", "--workspace", ws_ref), "surface")


def apply_plan(plan: list[dict], existing: dict[str, str], wait: float = 8.0) -> list[str]:
    """Rebuild the plan via the cmux CLI; returns a report. Needs the socket,
    so run it from a cmux tab."""
    report, started = [], []  # started: (session_id, surface_ref)
    for ws in plan:
        tabs = list(ws["tabs"])
        if ws["create"]:
            first = next((t for t in tabs if t["kind"] in ("claude", "terminal")), None)
            args = ["workspace", "create", "--name", ws["title"],
                    "--cwd", (first or {}).get("cwd") or ws.get("cwd") or str(BRIDGE_ROOT),
                    "--focus", "false"]
            if first:
                args += ["--command", ascii_command(tab_command(first))]
            ws_ref = parse_ref(_cmux(*args), "workspace")
            if not ws_ref:
                report.append(f"ERROR workspace {ws['title']} not created")
                continue
            if first:
                tabs.remove(first)
                if first["kind"] == "claude":
                    started.append((first["session_id"], _first_surface(ws_ref)))
            for cmd in decoration_commands(ws_ref, ws):
                _cmux(*cmd)
            report.append(f"created {ws['title']} ({ws_ref})")
        else:
            ws_ref = existing[ws["title"]]
            report.append(f"added to {ws['title']} ({ws_ref})")
        for tab in tabs:
            if tab["kind"] == "browser" and tab.get("url"):
                _cmux("new-surface", "--type", "browser", "--workspace", ws_ref,
                      "--url", tab["url"], "--focus", "false")
            elif tab["kind"] == "markdown" and tab.get("path"):
                _cmux("open", tab["path"], "--workspace", ws_ref, "--no-focus")
            else:
                sref = parse_ref(_cmux("new-surface", "--workspace", ws_ref,
                                       "--command", ascii_command(tab_command(tab)), "--focus", "false"),
                                 "surface")
                if tab["kind"] == "claude":
                    started.append((tab["session_id"], sref))
        if ws["skipped_running"]:
            report.append(f"  already running: {', '.join(s[:8] for s in ws['skipped_running'])}")
    if started:
        time.sleep(wait)
        alive = running_sessions()
        for sid, sref in started:
            if sid in alive:
                continue
            # a shell update prompt in the fresh tab can swallow the first character
            if sref:
                _cmux("send", "--surface", sref, f"claude --resume {sid}")
                _cmux("send-key", "--surface", sref, "Enter")
        if any(sid not in alive for sid, _ in started):
            time.sleep(wait)
            alive = running_sessions()
        missing = [sid for sid, _ in started if sid not in alive]
        report.append(f"agents running: {len(started) - len(missing)} of {len(started)}")
        report += [f"  MISSING {sid}" for sid in missing]
    return report


# --- CLI -----------------------------------------------------------------------

def _fmt_time(ts) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else "?"


def _cmux_reachable() -> bool:
    try:
        return _cmux("ping").strip() == "PONG"
    except CmuxUnavailable:
        return False


def main(argv=None, notifier=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    s.add_argument("--keep-days", type=int, default=KEEP_DAYS)
    s.add_argument("--min-claude", type=int, default=MIN_CLAUDE_DROP)
    s.add_argument("--min-workspaces", type=int, default=MIN_WORKSPACE_DROP)
    sub.add_parser("list")
    sh = sub.add_parser("show")
    sh.add_argument("snap", nargs="?")
    r = sub.add_parser("restore")
    r.add_argument("snap", nargs="?")
    r.add_argument("--apply", action="store_true")
    r.add_argument("--no-files", action="store_true", help="skip browser and markdown tabs")
    a = ap.parse_args(argv)

    if a.cmd == "snapshot":
        session = _load(a.source)
        if not isinstance(session, dict) or "windows" not in session:
            print(f"cmux session file not readable: {a.source}", file=sys.stderr)
            return 1
        path = snapshot(a.source, a.dir, keep_days=a.keep_days)
        print(f"snapshot {path.name}" if path else "unchanged")
        rows = list_snapshots(a.dir)
        if not path or len(rows) < 2:
            return 0
        before, after = (_load(rows[1]["path"]) or {}), (_load(rows[0]["path"]) or {})
        loss = detect_loss(before.get("layout") or {}, after.get("layout") or {},
                           a.min_claude, a.min_workspaces)
        if not loss:
            return 0
        msg = loss_message(loss, str(Path(__file__).resolve()))
        print(msg["what"])
        delivered = (notifier or notify_channel)(msg)
        if delivered is None:
            print("loss alarm: no notifier configured (CMUX_LAYOUT_NOTIFY), message above", file=sys.stderr)
            print(msg["do"])
            return 0
        if not delivered:
            print("loss alarm not delivered", file=sys.stderr)
            return 1
        return 0
    if a.cmd == "list":
        for i, row in enumerate(list_snapshots(a.dir)[:40]):
            s = row["summary"]
            print(f"{i:>3}  {_fmt_time(row['taken_at'])}  {s.get('workspaces', '?'):>2} workspaces  "
                  f"{s.get('tabs', '?'):>3} tabs  {s.get('claude', '?'):>3} agents  {row['path'].name}")
        return 0
    rec = _load(resolve_snapshot(a.dir, a.snap)) or {}
    layout = rec.get("layout") or {}
    if a.cmd == "show":
        print(f"Snapshot {_fmt_time(rec.get('taken_at'))}")
        for ws in iter_workspaces(layout):
            print(f"{ws['title']}  ({ws.get('cwd')})")
            for n, pane in enumerate(ws["panes"]):
                for t in pane:
                    ref = t.get("session_id") or t.get("url") or t.get("path") or t.get("cwd") or ""
                    split = f" [pane {n + 1}]" if len(ws["panes"]) > 1 else ""
                    print(f"   {t['kind']:<8} {t['title'][:50]:<50} {ref}{split}")
        return 0
    try:
        if a.apply:
            existing = existing_workspace_titles()
        else:
            existing = existing_workspace_titles() if _cmux_reachable() else {}
    except CmuxUnavailable as exc:
        print(exc, file=sys.stderr)
        return 1
    current = _load(DEFAULT_SOURCE) or {}
    present = present_sessions(extract_layout(current, tty_sessions()) if "windows" in current else {},
                               running_sessions())
    plan = plan_restore(layout, present, set(existing), include_files=not a.no_files)
    print(f"Snapshot {_fmt_time(rec.get('taken_at'))}: {len(plan)} workspaces to restore")
    for ws in plan:
        print(f"{'NEW ' if ws['create'] else 'ADD '} {ws['title']}")
        for t in ws["tabs"]:
            print(f"      {t['kind']:<8} {t['title'][:50]:<50} {t.get('session_id', '')}")
        for sid in ws["skipped_running"]:
            print(f"      already running {sid}")
    if not a.apply:
        print("(dry run; add --apply and run it from a cmux tab)")
        return 0
    for line in apply_plan(plan, existing):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
