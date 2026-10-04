# SPDX-License-Identifier: MIT
"""Contract for skills/cmux/scripts/cmux_driver.py, the cmux workplace driver.

The driver speaks the JSON protocol of scripts/workplace.py. Every test runs
against a FAKE `cmux` executable put first on PATH in a temp dir, which logs its
argv and answers from fixture files; the real cmux is never called. HOME and all
cmux file locations point into the temp dir too.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
SKILL = HERE.parents[1]
REPO = HERE.parents[3]
DRIVER = SKILL / "scripts" / "cmux_driver.py"

sys.path.insert(0, str(SKILL / "scripts"))
import cmux_driver as drv  # noqa: E402


def load_core():
    spec = importlib.util.spec_from_file_location("workplace_core", REPO / "scripts" / "workplace.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["workplace_core"] = module
    spec.loader.exec_module(module)
    return module


FAKE_CMUX = textwrap.dedent("""\
    import json, os, sys
    args = sys.argv[1:]
    with open(os.environ["FAKE_CMUX_LOG"], "a") as log:
        log.write(json.dumps(args) + "\\n")
    def answer(name):
        path = os.environ.get(name)
        return open(path).read() if path and os.path.exists(path) else ""
    if args[:2] == ["tree", "--json"]:
        print(answer("FAKE_CMUX_TREE"))
    elif args[:1] == ["tree"]:
        print("surface:61")
    elif args[:2] == ["workspace", "list"]:
        print(answer("FAKE_CMUX_WS"))
    elif args[:2] == ["workspace", "create"]:
        print("OK workspace:50")
    elif args[:1] == ["new-surface"]:
        print("OK surface:60 pane:1 workspace:50")
    else:
        print("OK")
    """)

TREE = {"windows": [{"workspaces": [
    {"title": "Platform", "ref": "workspace:3", "panes": [{"surfaces": [
        {"ref": "surface:91", "type": "terminal", "title": "✳ Fix login"},
        {"ref": "surface:92", "type": "terminal", "title": "user@host:~"},
        {"ref": "surface:7", "type": "browser", "title": "Docs"}]}]},
    {"title": "Customer A", "ref": "workspace:4", "panes": [{"surfaces": [
        {"ref": "surface:95", "type": "terminal", "title": "Invoice export"}]}]},
]}]}

SESSION = {"windows": [{"tabManager": {"workspaces": [
    {"customTitle": "Platform", "workspaceId": "WS-UUID-1",
     "panels": [{"id": "1C53A0D3", "type": "terminal", "title": "✳ Fix login", "terminal": {}},
                {"id": "2B000000", "type": "terminal", "title": "user@host:~", "terminal": {}}],
     "layout": {"type": "pane", "pane": {"panelIds": ["1C53A0D3", "2B000000"]}}},
]}}]}

HOOKS = {"activeSessionsBySurface": {"1C53A0D3": {"sessionId": "s1"}},
         "sessions": {"s1": {"hookEventName": "Stop", "lastBody": "Login fixed, tests green"}}}


@pytest.fixture
def fake(tmp_path, monkeypatch):
    """A temp world: fake cmux on PATH, cmux files in tmp, nothing of the real machine."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    cmux = bin_dir / "cmux"
    cmux.write_text(f"#!{sys.executable}\n" + FAKE_CMUX)
    cmux.chmod(0o755)
    files = {
        "FAKE_CMUX_LOG": tmp_path / "cmux.log",
        "FAKE_CMUX_TREE": tmp_path / "tree.json",
        "FAKE_CMUX_WS": tmp_path / "ws.txt",
        "CMUX_SESSION_FILE": tmp_path / "session.json",
        "CMUX_HOOKS_FILE": tmp_path / "hooks.json",
        "CMUX_LAYOUT_DIR": tmp_path / "layouts",
    }
    files["FAKE_CMUX_TREE"].write_text(json.dumps(TREE))
    files["FAKE_CMUX_WS"].write_text("  workspace:3 Platform\n* workspace:4 Customer A [selected]\n")
    files["CMUX_SESSION_FILE"].write_text(json.dumps(SESSION))
    files["CMUX_HOOKS_FILE"].write_text(json.dumps(HOOKS))
    env = {**os.environ, "PATH": str(bin_dir), "HOME": str(tmp_path),
           **{k: str(v) for k, v in files.items()}}

    class World:
        def call(self, request: dict) -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, str(DRIVER)], input=json.dumps(request),
                                  capture_output=True, text=True, env=env, timeout=60)

        def answer(self, request: dict) -> dict:
            done = self.call(request)
            assert done.returncode == 0, done.stderr
            return json.loads(done.stdout)

        def argv(self) -> list:
            log = files["FAKE_CMUX_LOG"]
            return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    world = World()
    world.files = files
    world.env = env
    return world


# ---------------------------------------------------------------- verbs over the protocol

def test_tabs_join_socket_refs_with_session_state_by_stripped_title(fake):
    tabs = fake.answer({"verb": "tabs"})["tabs"]
    by_name = {t["name"]: t for t in tabs}
    login = by_name["Fix login"]
    # ref from the socket (surface:91), state and last line from the session file (UUID 1C53A0D3)
    assert login["ref"] == "surface:91" and login["ws_ref"] == "workspace:3"
    assert login["state"] == "waiting" and login["last"] == "Login fixed, tests green"
    assert by_name["Invoice export"]["state"] == "shell"
    assert "Docs" not in by_name   # browser tabs are not agent tabs
    assert all(t["state"] in ("working", "waiting", "needs-you", "shell") for t in tabs)


def test_sessions_come_from_layout_snapshots(fake):
    snap_dir = fake.files["CMUX_LAYOUT_DIR"]
    snap_dir.mkdir()
    layout = {"windows": [{"workspaces": [{"title": "Platform", "panes": [[
        {"kind": "claude", "title": "Fix login", "session_id": "aaaaaaaa-1111-2222-3333-444444444444"}]]}]}]}
    (snap_dir / "layout-20260101-120000.json").write_text(json.dumps({"taken_at": 1, "layout": layout}))
    assert fake.answer({"verb": "sessions"}) == {
        "sessions": {"Fix login": "aaaaaaaa-1111-2222-3333-444444444444"}}


def test_open_reuses_open_tabs_creates_new_ones_and_never_closes(fake):
    plan = {"control": {"name": "Control"}, "workspaces": [
        {"name": "Platform", "cwd": "/repo", "tabs": [
            {"slug": "fix-login", "label": "Fix login", "action": "open", "ref": "surface:95",
             "workspace": "Customer A", "ws_ref": "workspace:4"},
            {"slug": "new-api", "label": "New API", "action": "new",
             "command": "cd -- /repo && my-agent -n new-api 'go'"},
            {"slug": "old-one", "label": "Old one", "action": "resume",
             "command": "cd -- /repo && my-agent --resume abc"}]}]}
    report = fake.answer({"verb": "open", "plan": plan, "only": None, "resume": False, "here": None})["report"]
    argv = fake.argv()
    assert not any("close" in " ".join(a) for a in argv)
    new_tabs = [a for a in argv if a[0] == "new-surface"]
    assert len(new_tabs) == 1                            # the open tab is reused, resume is not asked
    command = new_tabs[0][new_tabs[0].index("--command") + 1]
    assert command.startswith("cd -- /repo && my-agent -n new-api") and command.endswith(drv.KEEP_SHELL)
    assert ["move-surface", "--surface", "surface:95", "--workspace", "workspace:3", "--focus", "false"] in argv
    assert any(a[:2] == ["workspace", "create"] and "Control" in a for a in argv)
    assert any("New API" in line for line in report)


def test_open_with_here_moves_the_calling_tab_into_control_last(fake):
    plan = {"control": {"name": "Control"}, "workspaces": [
        {"name": "Platform", "cwd": "/repo", "tabs": [
            {"slug": "a", "label": "A", "action": "new", "command": "cd -- /repo && my-agent"}]}]}
    fake.answer({"verb": "open", "plan": plan, "only": None, "resume": False, "here": "surface:92"})
    moves = [a for a in fake.argv() if a[0] == "move-surface"]
    assert moves[-1][:3] == ["move-surface", "--surface", "surface:92"]
    create = next(a for a in fake.argv() if a[:2] == ["workspace", "create"])
    assert "--command" not in create          # the control tab is the caller, no extra agent


def test_send_types_text_then_enter_in_the_tabs_workspace(fake):
    assert fake.answer({"verb": "send", "tab": "surface:91", "text": "go on"})["report"]
    argv = fake.argv()
    assert ["send", "--workspace", "workspace:3", "--surface", "surface:91", "go on"] in argv
    assert ["send-key", "--workspace", "workspace:3", "--surface", "surface:91", "Enter"] in argv


def test_rename_addresses_the_tab_in_its_workspace(fake):
    fake.answer({"verb": "rename", "tab": "surface:95", "title": "Invoices"})
    assert ["tab-action", "--action", "rename", "--tab", "surface:95", "--title", "Invoices",
            "--workspace", "workspace:4"] in fake.argv()


# ---------------------------------------------------------------- failure is unknown, not empty

def test_without_cmux_the_driver_answers_a_json_error_not_a_traceback(fake, tmp_path):
    env = {**fake.env, "PATH": str(tmp_path / "empty")}
    done = subprocess.run([sys.executable, str(DRIVER)], input='{"verb": "tabs"}',
                          capture_output=True, text=True, env=env, timeout=60)
    assert done.returncode == 1
    assert "cmux" in json.loads(done.stdout)["error"]
    assert "Traceback" not in done.stderr


def test_core_reads_a_failed_driver_as_unknown(monkeypatch, tmp_path):
    core = load_core()
    monkeypatch.setenv("PATH", str(tmp_path))       # no cmux anywhere
    driver = core.CommandDriver([sys.executable, str(DRIVER)])
    assert driver.tabs_or_none() is None
    assert driver.sessions_or_none() is None
    assert "cmux" in driver.error


def test_no_tree_and_no_session_file_is_an_error_not_an_empty_list(fake):
    fake.files["FAKE_CMUX_TREE"].write_text("Failed to write to socket (Broken pipe, errno 32)")
    fake.files["CMUX_SESSION_FILE"].unlink()
    done = fake.call({"verb": "tabs"})
    assert done.returncode == 1 and "error" in json.loads(done.stdout)


def test_socket_down_falls_back_to_the_session_file(fake):
    fake.files["FAKE_CMUX_TREE"].write_text("not json")
    tabs = fake.answer({"verb": "tabs"})["tabs"]
    assert {t["name"] for t in tabs} == {"Fix login", "user@host:~"}


def test_unknown_verb_is_an_error(fake):
    done = fake.call({"verb": "close"})
    assert done.returncode == 1 and "unknown verb" in json.loads(done.stdout)["error"]


# ---------------------------------------------------------------- pure functions

def test_live_tabs_states_in_core_vocabulary():
    hooks = {"activeSessionsBySurface": {"A": {"sessionId": "s"}},
             "sessions": {"s": {"hookEventName": "PermissionRequest"}}}
    session = {"windows": [{"tabManager": {"workspaces": [{"customTitle": "W", "panels": [
        {"id": "A", "type": "terminal", "title": "✳ asks"},
        {"id": "B", "type": "terminal", "title": "⠋ busy"},
        {"id": "C", "type": "terminal", "title": "✳ idle"},
        {"id": "D", "type": "terminal", "title": "user@host:~"}]}]}}]}
    states = {t["surface"]: t["state"] for t in drv.live_tabs(session, hooks)}
    assert states == {"A": "needs-you", "B": "working", "C": "waiting", "D": "shell"}


def test_apply_calls_has_no_close_operation_for_any_plan():
    plan = drv.to_cmux_plan({"control": {"name": "Control"}, "workspaces": [
        {"name": "W", "tabs": [
            {"slug": "a", "label": "A", "action": "open", "ref": "surface:1", "workspace": "X"},
            {"slug": "b", "label": "B", "action": "new", "command": "my-agent"},
            {"slug": "c", "label": "C", "action": "resume", "command": "my-agent --resume c"}]}]})
    ops = {c["op"] for c in drv.apply_calls(plan, {}, "/repo", here="surface:9", resume=True)}
    assert ops <= {"create", "decorate", "order", "move", "rename", "tab", "tab_order"}


def test_to_cmux_plan_keeps_the_shell_once():
    core = {"workspaces": [{"name": "W", "tabs": [{"slug": "b", "label": "B", "action": "new",
                                                   "command": "my-agent"}]}]}
    twice = drv.to_cmux_plan(drv.to_cmux_plan(core))
    assert twice["workspaces"][0]["tabs"][0]["command"].count("exec") == 1


def test_workspace_resolves_through_aliases():
    existing = {"example-org": "workspace:28"}
    assert drv.resolve_workspace({"name": "Platform", "aliases": ["example-org"]}, existing) == "workspace:28"
    assert drv.resolve_workspace({"name": "Misc"}, existing) is None
