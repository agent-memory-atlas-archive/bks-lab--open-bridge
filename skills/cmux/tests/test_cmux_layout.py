# SPDX-License-Identifier: MIT
"""Tests for cmux_layout: snapshot, prune, list and restore planning.

The fixture mirrors the shape of cmux's own session file
(session-com.cmuxterm.app.json under cmux's Application Support folder, cmux 0.64.25).
No test calls the real cmux or reads the real process table.
"""

import json
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import cmux_layout as cl  # noqa: E402


@pytest.fixture(autouse=True)
def no_process_table(monkeypatch):
    """Keep the real `ps` out of the tests: fast and machine independent."""
    monkeypatch.setattr(cl, "tty_sessions", lambda: {})


SID_A = "aaaaaaaa-1111-2222-3333-444444444444"
SID_B = "bbbbbbbb-1111-2222-3333-444444444444"
SID_C = "cccccccc-1111-2222-3333-444444444444"


def claude_panel(pid, title, cwd, sid):
    return {
        "id": pid,
        "type": "terminal",
        "title": title,
        "directory": cwd,
        "terminal": {
            "agent": {"kind": "claude", "sessionId": sid, "workingDirectory": cwd},
            "resumeBinding": {"kind": "claude", "checkpointId": sid, "cwd": cwd},
            "workingDirectory": cwd,
        },
    }


def shell_panel(pid, cwd):
    return {
        "id": pid,
        "type": "terminal",
        "title": f"user@host:{cwd}",
        "directory": cwd,
        "terminal": {"workingDirectory": cwd},
    }


def session_file():
    ws_alpha = {
        "customTitle": "Alpha",
        "currentDirectory": "/repo",
        "panels": [
            # deliberately out of order: layout decides the tab order
            {"id": "P3", "type": "markdown", "title": "notes.md",
             "markdown": {"filePath": "/repo/notes.md"}},
            claude_panel("P1", "✳ First task", "/repo", SID_A),
            {"id": "P2", "type": "browser", "title": "Plan",
             "browser": {"urlString": "file:///repo/plan.html"}},
        ],
        "layout": {"type": "pane", "pane": {"panelIds": ["P1", "P2", "P3"]}},
    }
    ws_beta = {
        "customTitle": "",
        "processTitle": "◑ Beta work",
        "currentDirectory": "/other",
        "panels": [
            claude_panel("Q1", "⠀ Beta one", "/other", SID_B),
            shell_panel("Q2", "/other"),
            claude_panel("Q3", "Beta three", "/other", SID_C),
        ],
        "layout": {
            "type": "split",
            "split": {"children": [
                {"type": "pane", "pane": {"panelIds": ["Q1", "Q2"]}},
                {"type": "pane", "pane": {"panelIds": ["Q3"]}},
            ]},
        },
    }
    return {"version": 1, "windows": [{"tabManager": {"workspaces": [ws_alpha, ws_beta]}}]}


# --- extract -------------------------------------------------------------

def test_extract_orders_tabs_by_layout_and_keeps_kinds():
    layout = cl.extract_layout(session_file())
    ws = layout["windows"][0]["workspaces"]
    assert [w["title"] for w in ws] == ["Alpha", "Beta work"]
    alpha_tabs = [t for pane in ws[0]["panes"] for t in pane]
    assert [t["kind"] for t in alpha_tabs] == ["claude", "browser", "markdown"]
    assert alpha_tabs[0]["session_id"] == SID_A
    assert alpha_tabs[0]["title"] == "First task"  # status glyph stripped
    assert alpha_tabs[1]["url"] == "file:///repo/plan.html"
    assert alpha_tabs[2]["path"] == "/repo/notes.md"


def test_extract_keeps_split_panes_and_plain_shells():
    ws = cl.extract_layout(session_file())["windows"][0]["workspaces"][1]
    assert len(ws["panes"]) == 2
    assert [t["kind"] for t in ws["panes"][0]] == ["claude", "terminal"]
    assert ws["panes"][0][1]["cwd"] == "/other"
    assert ws["panes"][1][0]["session_id"] == SID_C


def test_extract_appends_panels_missing_from_layout():
    data = session_file()
    data["windows"][0]["tabManager"]["workspaces"][0]["layout"] = {}
    tabs = [t for p in cl.extract_layout(data)["windows"][0]["workspaces"][0]["panes"] for t in p]
    assert len(tabs) == 3


def test_summary_counts():
    assert cl.summarize(cl.extract_layout(session_file())) == {
        "workspaces": 2, "tabs": 6, "claude": 3}


# --- snapshot + prune ------------------------------------------------------

def write_src(tmp_path, data):
    src = tmp_path / "session.json"
    src.write_text(json.dumps(data))
    return src


def test_snapshot_writes_once_and_skips_unchanged(tmp_path):
    src = write_src(tmp_path, session_file())
    out = tmp_path / "layouts"
    first = cl.snapshot(src, out, now=1_000_000)
    assert first is not None and first.exists()
    assert cl.snapshot(src, out, now=1_000_120) is None


def test_snapshot_ignores_title_only_changes(tmp_path):
    out = tmp_path / "layouts"
    data = session_file()
    cl.snapshot(write_src(tmp_path, data), out, now=1_000_000)
    data["windows"][0]["tabManager"]["workspaces"][0]["panels"][1]["title"] = "⠁ Other title"
    assert cl.snapshot(write_src(tmp_path, data), out, now=1_000_120) is None


def test_snapshot_writes_on_structural_change(tmp_path):
    out = tmp_path / "layouts"
    data = session_file()
    cl.snapshot(write_src(tmp_path, data), out, now=1_000_000)
    data["windows"][0]["tabManager"]["workspaces"].pop()
    assert cl.snapshot(write_src(tmp_path, data), out, now=1_000_120) is not None
    assert len(cl.list_snapshots(out)) == 2


def test_snapshot_of_missing_or_broken_source_is_none(tmp_path):
    assert cl.snapshot(tmp_path / "nope.json", tmp_path / "l", now=1) is None
    bad = tmp_path / "bad.json"
    bad.write_text("{half")
    assert cl.snapshot(bad, tmp_path / "l", now=1) is None


def test_prune_drops_old_but_keeps_minimum(tmp_path):
    out = tmp_path / "layouts"
    data = session_file()
    day = 86_400
    for i in range(6):
        data["windows"][0]["tabManager"]["workspaces"][0]["customTitle"] = f"Alpha {i}"
        cl.snapshot(write_src(tmp_path, data), out, now=1_000_000 + i * day)
    removed = cl.prune(out, now=1_000_000 + 11 * day, keep_days=7, min_keep=2)
    assert removed == 4
    assert len(cl.list_snapshots(out)) == 2


def test_same_second_snapshots_keep_their_order(tmp_path):
    out = tmp_path / "layouts"
    data = session_file()
    cl.snapshot(write_src(tmp_path, data), out, now=1_000_000)
    for i in range(11):
        data["windows"][0]["tabManager"]["workspaces"][0]["customTitle"] = f"Alpha {i}"
        cl.snapshot(write_src(tmp_path, data), out, now=1_000_000)
    rows = cl.list_snapshots(out)
    newest = cl._load(rows[0]["path"])["layout"]
    assert newest["windows"][0]["workspaces"][0]["title"] == "Alpha 10"


def test_list_reports_counts_newest_first(tmp_path):
    out = tmp_path / "layouts"
    data = session_file()
    cl.snapshot(write_src(tmp_path, data), out, now=1_000_000)
    data["windows"][0]["tabManager"]["workspaces"].pop()
    cl.snapshot(write_src(tmp_path, data), out, now=1_000_500)
    rows = cl.list_snapshots(out)
    assert [r["summary"]["workspaces"] for r in rows] == [1, 2]


# --- restore plan ----------------------------------------------------------

def test_plan_skips_running_sessions_and_reuses_existing_workspace():
    layout = cl.extract_layout(session_file())
    plan = cl.plan_restore(layout, running_sessions={SID_B}, existing_workspaces={"Alpha"})
    by_ws = {p["title"]: p for p in plan}
    assert by_ws["Alpha"]["create"] is False
    assert by_ws["Beta work"]["create"] is True
    beta_tabs = by_ws["Beta work"]["tabs"]
    assert SID_B not in [t.get("session_id") for t in beta_tabs]
    assert [t["kind"] for t in beta_tabs] == ["terminal", "claude"]
    assert by_ws["Beta work"]["skipped_running"] == [SID_B]


def test_plan_drops_workspace_with_nothing_left():
    layout = cl.extract_layout(session_file())
    plan = cl.plan_restore(layout, running_sessions={SID_A},
                           existing_workspaces={"Alpha"}, include_files=False)
    assert "Alpha" not in [p["title"] for p in plan]


def test_resume_command_quotes_cwd_and_keeps_a_shell():
    # A tab whose only process is claude takes its workspace down when claude
    # exits, so the command must fall back to a shell.
    tab = {"kind": "claude", "cwd": "/with space/it's", "session_id": SID_A}
    cmd = cl.tab_command(tab)
    assert cmd == ("cd -- '/with space/it'\"'\"'s' && claude --resume " + SID_A
                   + "; exec \"${SHELL:-/bin/sh}\" -l")


def test_shell_tab_command_only_changes_directory():
    assert cl.tab_command({"kind": "terminal", "cwd": "/repo"}) == "cd -- '/repo'"


def test_running_sessions_from_ps_output():
    ps = (
        "123 /home/x/.local/bin/claude --session-id " + SID_A + " --settings /tmp/s\n"
        "456 claude --resume " + SID_B + "\n"
        "789 vim notes.md\n"
    )
    assert cl.running_sessions_from_ps(ps) == {SID_A, SID_B}


def test_parse_ref():
    assert cl.parse_ref("OK workspace:12", "workspace") == "workspace:12"
    assert cl.parse_ref("OK surface:27 pane:15 workspace:13", "surface") == "surface:27"
    assert cl.parse_ref("error", "surface") is None


def test_tty_lookup_fills_claude_session_cmux_did_not_bind():
    # cmux sometimes records a resumed claude tab as a plain terminal; the
    # process table still knows which session runs on that tty.
    data = session_file()
    shell = data["windows"][0]["tabManager"]["workspaces"][1]["panels"][1]
    shell["ttyName"] = "ttys007"
    layout = cl.extract_layout(data, tty_sessions={"ttys007": SID_A})
    tab = layout["windows"][0]["workspaces"][1]["panes"][0][1]
    assert tab["kind"] == "claude" and tab["session_id"] == SID_A


def test_tty_sessions_from_ps_output():
    ps = (
        "  PID TTY      COMMAND\n"
        "  123 ttys007  /home/x/.local/bin/claude --resume " + SID_A + "\n"
        "  124 ttys008  claude --session-id " + SID_B + " --settings /tmp/x\n"
        "  125 ??       node server.js\n"
    )
    assert cl.tty_sessions_from_ps(ps) == {"ttys007": SID_A, "ttys008": SID_B}


def test_cli_snapshot_fails_loudly_on_unreadable_source(tmp_path, capsys):
    # "unchanged" and "could not read" must not both look like a clean run
    rc = cl.main(["--dir", str(tmp_path / "l"), "snapshot", "--source", str(tmp_path / "nope.json")])
    assert rc == 1
    assert "not readable" in capsys.readouterr().err


def test_cli_snapshot_reports_unchanged(tmp_path, capsys):
    src = write_src(tmp_path, session_file())
    args = ["--dir", str(tmp_path / "l"), "snapshot", "--source", str(src)]
    assert cl.main(args) == 0
    assert cl.main(args) == 0
    assert "unchanged" in capsys.readouterr().out


# --- loss alarm --------------------------------------------------------------

def _drop_beta(data):
    data["windows"][0]["tabManager"]["workspaces"].pop()  # Beta: 2 claude tabs
    return data


def test_detect_loss_names_vanished_claude_tabs():
    before = cl.extract_layout(session_file())
    after = cl.extract_layout(_drop_beta(session_file()))
    loss = cl.detect_loss(before, after, min_claude=2)
    assert loss["claude_before"] == 3 and loss["claude_after"] == 1
    assert loss["workspaces_before"] == 2 and loss["workspaces_after"] == 1
    assert [(t["workspace"], t["session_id"]) for t in loss["vanished"]] == [
        ("Beta work", SID_B), ("Beta work", SID_C)]


def test_detect_loss_ignores_small_changes():
    before = cl.extract_layout(session_file())
    after = cl.extract_layout(_drop_beta(session_file()))
    assert cl.detect_loss(before, after, min_claude=3, min_workspaces=2) is None
    assert cl.detect_loss(before, before) is None


def test_cli_notifies_once_on_loss(tmp_path):
    calls = []
    out = tmp_path / "l"
    args = ["--dir", str(out), "snapshot", "--source"]
    src = write_src(tmp_path, session_file())
    assert cl.main(args + [str(src)], notifier=calls.append) == 0
    src = write_src(tmp_path, _drop_beta(session_file()))
    for _ in range(2):  # the second run sees no change and stays silent
        assert cl.main(args + [str(src), "--min-claude", "2"], notifier=lambda m: calls.append(m) or True) == 0
    assert len(calls) == 1
    msg = calls[0]
    assert "3 -> 1" in msg["what"] and "Beta work" in msg["detail"]
    assert "restore 1" in msg["do"]


def test_cli_fails_when_alarm_cannot_be_delivered(tmp_path):
    out = tmp_path / "l"
    args = ["--dir", str(out), "snapshot", "--min-claude", "2", "--source"]
    cl.main(args + [str(write_src(tmp_path, session_file()))], notifier=lambda m: True)
    rc = cl.main(args + [str(write_src(tmp_path, _drop_beta(session_file())))], notifier=lambda m: False)
    assert rc == 1


def test_hibernated_sessions_count_as_present():
    # cmux Agent Hibernation kills an idle claude but keeps its tab bound; such a
    # session has no process and must not be restored a second time.
    current = cl.extract_layout(session_file())
    present = cl.present_sessions(current, running={SID_C})
    assert present == {SID_A, SID_B, SID_C}


def test_color_and_description_are_kept_and_restored():
    data = session_file()
    ws = data["windows"][0]["tabManager"]["workspaces"][0]
    ws["customColor"] = "#3E4B5E"
    ws["customDescription"] = "Customer A: proposal"
    layout = cl.extract_layout(data)
    alpha = layout["windows"][0]["workspaces"][0]
    assert alpha["color"] == "#3E4B5E" and alpha["description"] == "Customer A: proposal"
    assert "color" not in layout["windows"][0]["workspaces"][1]
    plan = cl.plan_restore(layout, running_sessions=set(), existing_workspaces=set())
    assert plan[0]["color"] == "#3E4B5E" and plan[0]["description"] == "Customer A: proposal"
    assert cl.decoration_commands("workspace:9", plan[0]) == [
        ["workspace-action", "--workspace", "workspace:9", "--action", "set-color", "--color", "#3E4B5E"],
        ["workspace-action", "--workspace", "workspace:9", "--action", "set-description",
         "--description", "Customer A: proposal"],
    ]


def test_color_change_alone_makes_a_snapshot(tmp_path):
    out = tmp_path / "layouts"
    data = session_file()
    cl.snapshot(write_src(tmp_path, data), out, now=1_000_000)
    data["windows"][0]["tabManager"]["workspaces"][0]["customColor"] = "#FF0000"
    assert cl.snapshot(write_src(tmp_path, data), out, now=1_000_100) is not None


def test_ascii_command_keeps_umlauts_out_of_the_cli(tmp_path, monkeypatch):
    # `cmux --command` double-encodes non-ASCII, `send` does not.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(cl.Path, "home", classmethod(lambda c: tmp_path))
    assert cl.ascii_command("cd -- '/repo'") == "cd -- '/repo'"
    cmd = "echo 'caf\u00e9 na\u00efve \u00fcber'"
    out = cl.ascii_command(cmd)
    assert out.isascii() and out.startswith(". '")
    f = tmp_path / ".cmuxterm/commands"
    assert next(f.iterdir()).read_text(encoding="utf-8").strip() == cmd


def test_cli_without_notifier_prints_the_alarm_and_succeeds(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("CMUX_LAYOUT_NOTIFY", raising=False)
    args = ["--dir", str(tmp_path / "l"), "snapshot", "--min-claude", "2", "--source"]
    cl.main(args + [str(write_src(tmp_path, session_file()))])
    rc = cl.main(args + [str(write_src(tmp_path, _drop_beta(session_file())))])
    captured = capsys.readouterr()
    assert rc == 0
    assert "3 -> 1" in captured.out and "no notifier configured" in captured.err


def test_notifier_executable_gets_plain_flags(tmp_path, monkeypatch):
    log = tmp_path / "args.txt"
    script = tmp_path / "notify"
    script.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$@\" > '{log}'\n")
    script.chmod(0o755)
    monkeypatch.setenv("CMUX_LAYOUT_NOTIFY", str(script))
    msg = {"what": "w", "where": "cmux", "do": "d", "detail": "x"}
    assert cl.notify_channel(msg) is True
    assert log.read_text().split() == ["--what", "w", "--where", "cmux", "--do", "d", "--detail", "x"]


def test_cmux_missing_raises_a_distinct_error(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(cl.CmuxUnavailable):
        cl._cmux("ping")


def _failing_cmux(tmp_path, monkeypatch, code=1, text="Error: not_found: Workspace not found"):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "cmux"
    fake.write_text(f"#!/bin/sh\necho '{text}' >&2\nexit {code}\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))


def test_checked_call_fails_on_error_exit(tmp_path, monkeypatch):
    # cmux signals errors with exit 1 and an `Error: ...` line, never by silence.
    _failing_cmux(tmp_path, monkeypatch)
    with pytest.raises(cl.CmuxError, match="not_found"):
        cl.cmux_checked("send", "--surface", "surface:1", "x")


def test_checked_call_fails_on_error_text_even_with_exit_zero(tmp_path, monkeypatch):
    _failing_cmux(tmp_path, monkeypatch, code=0)
    with pytest.raises(cl.CmuxError):
        cl.cmux_checked("workspace", "list")


def test_unreadable_workspace_list_is_an_error_not_empty(tmp_path, monkeypatch):
    _failing_cmux(tmp_path, monkeypatch)
    with pytest.raises(cl.CmuxError):
        cl.existing_workspace_titles()
