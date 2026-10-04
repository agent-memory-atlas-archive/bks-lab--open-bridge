# SPDX-License-Identifier: MIT
"""Contract for scripts/workplace.py: plan the day's tabs from the tasks, act through a driver.

The plan (which task gets a tab, in which workspace, new or resumed) is CORE and
knows no terminal. Everything a terminal does goes through a driver command that
speaks JSON on stdin/stdout, the same shape as agents/_runtime/approval.py. With
no driver configured the built-in `none` driver prints what to start by hand, so
a Bridge without any multiplexer gets the same plan.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("workplace", ROOT / "scripts" / "workplace.py")
assert spec is not None and spec.loader is not None
wp = importlib.util.module_from_spec(spec)
sys.modules["workplace"] = wp
sys.dont_write_bytecode = True
spec.loader.exec_module(wp)

TODAY = dt.date(2026, 10, 4)
CFG = {
    "workspaces": [
        {"name": "Bigcorp", "contexts": ["bigcorp"], "color": "#1565C0"},
        {"name": "Platform", "slugs": ["platform-*"]},
        {"name": "Misc", "default": True},
    ],
    "limits": {"max_workspaces": 2, "max_tabs": 2, "stale_days": 10, "activity_days": 7},
}


def task(root: Path, slug: str, **fm) -> None:
    d = root / "work" / "tasks" / slug
    d.mkdir(parents=True)
    fields = {"slug": slug, "status": "doing", "last_updated": "2026-10-03", **fm}
    body = "\n".join(f"{k}: {json.dumps(v) if isinstance(v, str) and ':' in v else v}" for k, v in fields.items())
    (d / "STATUS.md").write_text(f"---\n{body}\n---\n\n# {slug.replace('-', ' ').title()}\n", encoding="utf-8")


@pytest.fixture()
def repo(tmp_path):
    task(tmp_path, "payments-incident", context="bigcorp", priority="P0")
    task(tmp_path, "bigcorp-report", context="bigcorp")
    task(tmp_path, "bigcorp-old", context="bigcorp", last_updated="2026-08-01")
    task(tmp_path, "platform-upgrade")
    task(tmp_path, "waiting-on-vendor", blocked_by="vendor answers")
    task(tmp_path, "parked", status="backlog")
    (tmp_path / "work" / "log.md").write_text(textwrap.dedent("""\
        | 2026-10-04 09:00 | 🐛 | bigcorp | payments-incident triaged |
        | 2026-10-04 10:00 | 🐛 | bigcorp | payments-incident fix on a branch |
        | 2026-10-03 10:00 | 📝 | bigcorp | bigcorp-report drafted |
        """), encoding="utf-8")
    return tmp_path


def test_plan_groups_tasks_into_workspaces_by_slug_then_context_then_default(repo):
    plan = wp.build_plan(repo, CFG, TODAY, wp.NoneDriver())
    names = [w["name"] for w in plan["workspaces"]]
    assert names[0] == "Bigcorp"
    bigcorp = plan["workspaces"][0]
    assert [t["slug"] for t in bigcorp["tabs"]] == ["payments-incident", "bigcorp-report"]
    assert "Platform" in names


def test_blocked_stale_and_backlog_get_no_tab(repo):
    plan = wp.build_plan(repo, CFG, TODAY, wp.NoneDriver())
    tabbed = {t["slug"] for w in plan["workspaces"] for t in w["tabs"]}
    assert "waiting-on-vendor" not in tabbed and "parked" not in tabbed and "bigcorp-old" not in tabbed
    assert [t["slug"] for t in plan["blocked"]] == ["waiting-on-vendor"]
    assert [t["slug"] for t in plan["stale"]] == ["bigcorp-old"]


def test_open_tab_from_the_driver_is_reused_and_a_known_session_is_resumed(repo):
    class Fake(wp.NoneDriver):
        def tabs(self):
            return [{"name": "payments-incident", "workspace": "Bigcorp", "ref": "s:1", "state": "waiting"}]

        def sessions(self):
            return {"bigcorp-report": "abc-123"}

    plan = wp.build_plan(repo, CFG, TODAY, Fake())
    tabs = {t["slug"]: t for t in plan["workspaces"][0]["tabs"]}
    assert tabs["payments-incident"]["action"] == "open"
    assert tabs["payments-incident"]["ref"] == "s:1"
    assert tabs["bigcorp-report"]["action"] == "resume"
    assert "abc-123" in tabs["bigcorp-report"]["command"]


def test_every_new_tab_carries_the_command_that_starts_its_agent(repo):
    plan = wp.build_plan(repo, CFG, TODAY, wp.NoneDriver())
    tab = plan["workspaces"][0]["tabs"][0]
    assert tab["action"] == "new"
    assert "payments-incident" in tab["command"] and "claude" in tab["command"]


def test_agent_command_is_configurable(repo):
    cfg = {**CFG, "agent": {"new": "codex {prompt}", "resume": "codex resume {session}"}}
    plan = wp.build_plan(repo, cfg, TODAY, wp.NoneDriver())
    assert plan["workspaces"][0]["tabs"][0]["command"].startswith("cd ")
    assert "codex " in plan["workspaces"][0]["tabs"][0]["command"]


def test_none_driver_opens_nothing_and_says_what_to_start(repo, capsys):
    plan = wp.build_plan(repo, CFG, TODAY, wp.NoneDriver())
    report = wp.NoneDriver().open(plan, only=None, resume=False, here=None)
    text = "\n".join(report)
    assert "payments-incident" in text and "no driver" in text.lower()


def test_command_driver_speaks_json_on_stdin_and_stdout(tmp_path):
    script = tmp_path / "driver.py"
    script.write_text(textwrap.dedent("""\
        import json, sys
        req = json.load(sys.stdin)
        if req["verb"] == "tabs":
            print(json.dumps({"tabs": [{"name": "x", "workspace": "W", "ref": "r", "state": "working"}]}))
        elif req["verb"] == "send":
            print(json.dumps({"report": ["sent " + req["text"] + " to " + req["tab"]]}))
        else:
            print(json.dumps({}))
        """))
    drv = wp.CommandDriver([sys.executable, str(script)])
    assert drv.tabs()[0]["state"] == "working"
    assert drv.send("x", "go on") == ["sent go on to x"]
    assert drv.sessions() == {}


def test_command_driver_failure_is_reported_not_raised(tmp_path):
    drv = wp.CommandDriver(["/definitely/not/here"])
    assert drv.tabs() == []
    assert "failed" in " ".join(drv.send("x", "y")).lower()


def test_driver_from_config():
    assert isinstance(wp.driver_from(None), wp.NoneDriver)
    assert isinstance(wp.driver_from("none"), wp.NoneDriver)
    assert isinstance(wp.driver_from({"command": ["true"]}), wp.CommandDriver)
    with pytest.raises(ValueError):
        wp.driver_from({"command": "not a list"})


def test_status_joins_driver_tabs_with_tasks_and_the_inbox(repo):
    class Fake(wp.NoneDriver):
        def tabs(self):
            return [{"name": "payments-incident", "workspace": "Bigcorp", "ref": "s:1", "state": "needs-you",
                     "last": "allow deploy?"}]

    rows = wp.status_rows(repo, CFG, Fake())
    assert rows[0]["slug"] == "payments-incident" and rows[0]["state"] == "needs-you"


def test_load_config_reads_the_workplace_block(tmp_path):
    (tmp_path / "bridge-config.yaml").write_text("workplace:\n  driver: none\n  limits: {max_tabs: 1}\n")
    cfg = wp.load_cfg(tmp_path)
    assert cfg["driver"] == "none" and cfg["limits"]["max_tabs"] == 1
    assert wp.load_cfg(tmp_path / "missing") == {}


def test_a_failed_driver_is_unknown_not_empty(tmp_path):
    drv = wp.CommandDriver(["/definitely/not/here"])
    assert drv.tabs_or_none() is None
    assert drv.sessions_or_none() is None


def test_plan_with_an_unknown_tab_view_says_so_and_refuses_to_open(repo):
    class Broken(wp.NoneDriver):
        name = "broken"

        def tabs_or_none(self):
            return None

    plan = wp.build_plan(repo, CFG, TODAY, Broken())
    assert plan["driver_error"]
    assert wp.main(["--root", str(repo), "open", "--yes"]) in (0, 1)   # smoke: never raises


def test_open_yes_is_refused_when_open_tabs_are_unknown(repo, capsys):
    (repo / "bridge-config.yaml").write_text("workplace:\n  driver: {command: ['/definitely/not/here']}\n")
    assert wp.main(["--root", str(repo), "open", "--yes"]) == 1
    assert "unknown" in capsys.readouterr().err.lower()


def test_status_prints_the_driver_error(repo, capsys):
    (repo / "bridge-config.yaml").write_text("workplace:\n  driver: {command: ['/definitely/not/here']}\n")
    assert wp.main(["--root", str(repo), "status"]) == 1
    assert "failed" in capsys.readouterr().err.lower()


def test_sessions_that_are_not_a_mapping_are_unknown(tmp_path):
    script = tmp_path / "d.py"
    script.write_text("import json,sys; json.load(sys.stdin); print(json.dumps({'sessions': ['x']}))")
    assert wp.CommandDriver([sys.executable, str(script)]).sessions_or_none() is None


def _scripted_driver(repo, tmp_path, answer: str, exit_code: int = 0):
    """A driver that lists no tabs and answers every other verb with `answer`."""
    script = tmp_path / "drv.py"
    script.write_text(
        "import json, sys\n"
        "req = json.load(sys.stdin)\n"
        "if req['verb'] == 'tabs':\n    print(json.dumps({'tabs': []})); sys.exit(0)\n"
        "if req['verb'] == 'sessions':\n    print(json.dumps({'sessions': {}})); sys.exit(0)\n"
        f"print({answer!r}); sys.exit({exit_code})\n")
    (repo / "bridge-config.yaml").write_text(
        f"workplace:\n  driver: {{command: ['{sys.executable}', '{script}']}}\n")


@pytest.mark.parametrize("answer, code, expected", [
    ('{"report": ["opened alpha"]}', 0, 0),
    ('{"report": ["opened alpha", "ERROR move alpha: refused"]}', 0, 1),
    ('{"error": "cmux refused"}', 1, 1),
])
def test_open_send_adopt_exit_non_zero_when_the_driver_failed(repo, tmp_path, answer, code, expected):
    """A workload or script must see the failure a person reads, not exit 0."""
    _scripted_driver(repo, tmp_path, answer, code)
    assert wp.main(["--root", str(repo), "open", "--yes"]) == expected
    assert wp.main(["--root", str(repo), "send", "some-tab", "hello"]) == expected
