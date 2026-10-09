# SPDX-License-Identifier: MIT
"""Contract for the dashboard pages of a briefing (scripts/lib/briefing_view.py `pages`).

A dashboard shows the briefing's sections as tabs beside the briefing itself. Which
section sits on which tab, and which item field fills which column, differs per person:
one has health probes and GitHub, another a Jira board and no calendar. So the profile
says it (`view.pages`), and without that the pages follow from each section's kind, so
that no section the person collects is left without a place.

Every row carries the same four columns, whatever its kind: when, title, detail, link.
A column stays empty only when the item has nothing for it.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


bf = sys.modules.get("briefing") or _load("briefing", ROOT / "scripts" / "briefing.py")
bv = sys.modules.get("briefing_view") or _load("briefing_view", ROOT / "scripts" / "lib" / "briefing_view.py")

NOW = "2026-10-08T12:00"


def _sec(sid, kind, items, status="ok", **extra):
    return {"id": sid, "kind": kind, "title": sid.capitalize(), "status": status, "items": items,
            "total": len(items), **extra}


def _result():
    return {"collected_at": NOW, "sections": [
        _sec("inbox", "inbox", [{"id": "1", "title": "Answer the vendor"}]),
        _sec("probes", "command", [{"id": "p1", "title": "Backup stale", "state": "blocked", "raw_state": "stale"},
                                   {"id": "p2", "title": "Disk at 85 %", "state": "in_progress"}]),
        _sec("mine", "tracker", [
            {"id": "acme/app#7", "title": "Fix login", "type": "pr", "raw_state": "open", "project": "acme/app",
             "url": "https://example.test/acme/app/pull/7", "changed_at": "2026-10-08T09:30:00"},
            {"id": "acme/app#3", "title": "Old bug", "type": "issue", "raw_state": "open", "project": "Roadmap",
             "url": "https://example.test/acme/app/issues/3", "changed_at": "2026-10-05T10:00:00", "priority": "P1"}]),
        _sec("cal", "calendar", [
            {"id": "a", "title": "Standup", "start": "2026-10-08T09:00", "end": "2026-10-08T09:15"},
            {"id": "b", "title": "Review", "start": "2026-10-08T15:00", "end": "2026-10-08T16:00"},
            {"id": "c", "title": "Dentist", "start": "2026-10-09T08:00", "end": "2026-10-09T09:00", "info": True}]),
        _sec("commits", "commits", [
            {"id": "quiet", "title": "quiet", "counts": [3, 0], "spark": "▂▁", "branch": "main"},
            {"id": "busy", "title": "busy", "counts": [1, 5], "spark": "▁█", "branch": "dev"}]),
        _sec("log", "activity", [
            {"id": "x", "title": "Shipped it", "project": "app", "changed_at": "2026-10-08T11:00"},
            {"id": "y", "title": "Planned it", "project": "app", "changed_at": "2026-10-06T10:00"}]),
        _sec("workplace", "workplace", [{"id": "t", "title": "Tab one", "project": "Area", "state": "new"}]),
    ]}


def _profile(view=None):
    return {"id": "morning", "view": view or {}}


def _page(pages, pid):
    return next(p for p in pages if p["id"] == pid)


def _section(pages, sid):
    return next(s for p in pages for s in p["sections"] if s["id"] == sid)


# ---------------------------------------------------------------- default pages

def test_without_a_pages_block_every_section_finds_a_page_by_its_kind():
    pages = bv.pages(_result(), _profile())
    assert [p["id"] for p in pages] == ["status", "dates", "trackers", "today", "more"]
    assert [s["id"] for s in _page(pages, "status")["sections"]] == ["probes"]
    assert [s["id"] for s in _page(pages, "today")["sections"]] == ["commits", "log"]
    # a kind the defaults do not know still shows, on the last page
    assert [s["id"] for s in _page(pages, "more")["sections"]] == ["workplace"]


def test_the_briefing_page_keeps_its_own_kinds():
    ids = {s["id"] for p in bv.pages(_result(), _profile()) for s in p["sections"]}
    assert "inbox" not in ids


def test_a_page_without_a_section_is_left_out():
    result = _result()
    result["sections"] = [s for s in result["sections"] if s["kind"] != "calendar"]
    assert "dates" not in [p["id"] for p in bv.pages(result, _profile())]


def test_page_titles_come_from_the_labels():
    pages = bv.pages(_result(), _profile({"labels": {"page_dates": "Termine"}}))
    assert _page(pages, "dates")["title"] == "Termine"
    assert _page(pages, "status")["title"] == "Status"


# ---------------------------------------------------------------- the profile decides

def test_the_profile_places_sections_on_its_own_pages():
    view = {"pages": [
        {"id": "ops", "title": "Ops", "sections": ["probes", "mine"]},
        {"id": "week", "title": "Week", "sections": ["cal"]},
    ]}
    pages = bv.pages(_result(), _profile(view))
    assert [p["id"] for p in pages][:2] == ["ops", "week"]
    assert [s["id"] for s in _page(pages, "ops")["sections"]] == ["probes", "mine"]
    assert _page(pages, "ops")["title"] == "Ops"


def test_a_section_no_page_names_lands_on_the_rest_page():
    pages = bv.pages(_result(), _profile({"pages": [{"id": "ops", "sections": ["probes"]}]}))
    assert [s["id"] for s in _page(pages, "more")["sections"]] == ["mine", "cal", "commits", "log", "workplace"]


def test_the_rest_page_can_be_switched_off():
    pages = bv.pages(_result(), _profile({"pages": [{"id": "ops", "sections": ["probes"]}], "page_rest": "hide"}))
    assert [p["id"] for p in pages] == ["ops"]


def test_a_page_may_also_show_a_briefing_kind_when_the_profile_asks():
    pages = bv.pages(_result(), _profile({"pages": [{"id": "ops", "sections": ["inbox"]}], "page_rest": "hide"}))
    assert [s["id"] for s in _page(pages, "ops")["sections"]] == ["inbox"]


# ---------------------------------------------------------------- columns

def test_tracker_rows_fill_every_column():
    rows = _section(bv.pages(_result(), _profile()), "mine")["items"]
    pr, old = rows
    assert pr == {"title": "acme/app#7 Fix login", "when": "09:30", "detail": "PR · open",
                  "tone": None, "url": "https://example.test/acme/app/pull/7", "task": None, "ask": True, "mark": None}
    # a project that the id already names is not repeated; another one is
    assert old["detail"] == "open · Roadmap · P1"
    assert old["when"] == "05.10"


def test_calendar_rows_say_until_when_and_mark_what_is_past_or_only_info():
    rows = _section(bv.pages(_result(), _profile()), "cal")["items"]
    assert [r["when"] for r in rows] == ["09:00", "15:00", "tomorrow 08:00"]
    assert rows[0]["detail"] == "until 09:15" and rows[0]["tone"] == "dim"
    assert rows[1]["tone"] is None
    assert rows[2]["detail"] == "until 09:00 · info"


def test_command_findings_are_warnings_and_blocked_ones_are_bad():
    rows = _section(bv.pages(_result(), _profile()), "probes")["items"]
    assert [r["tone"] for r in rows] == ["bad", "warn"]
    assert rows[0]["detail"] == "stale"
    assert rows[1]["detail"] == "in_progress"


def test_commits_lead_with_todays_count_busiest_first():
    rows = _section(bv.pages(_result(), _profile()), "commits")["items"]
    assert [r["title"] for r in rows] == ["busy", "quiet"]
    assert rows[0]["when"] == "5 today" and rows[0]["detail"] == "▁█ dev"
    assert rows[1]["tone"] == "dim"


def test_activity_from_earlier_days_is_dimmed():
    rows = _section(bv.pages(_result(), _profile()), "log")["items"]
    assert [r["when"] for r in rows] == ["11:00", "06.10"]
    assert [r["tone"] for r in rows] == [None, "dim"]
    assert rows[0]["detail"] == "app"


def test_a_page_entry_names_the_fields_for_its_columns():
    view = {"pages": [{"id": "ops", "sections": [
        {"id": "mine", "when": "changed_at", "detail": ["priority", "type"], "link": "none"}]}], "page_rest": "hide"}
    rows = _section(bv.pages(_result(), _profile(view)), "mine")["items"]
    assert rows[1]["detail"] == "P1 · issue"
    assert rows[1]["when"] == "05.10"
    assert rows[1]["url"] is None


def test_only_a_web_address_becomes_a_link():
    result = _result()
    result["sections"][-2]["items"][0]["url"] = "work/tasks/x/STATUS.md"
    rows = _section(bv.pages(result, _profile()), "log")["items"]
    assert rows[0]["url"] is None


def test_alarm_makes_every_finding_bad_and_says_so_on_the_section():
    view = {"pages": [{"id": "ops", "sections": [{"id": "probes", "alarm": True, "empty": "all green"}]}],
            "page_rest": "hide"}
    sec = _section(bv.pages(_result(), _profile(view)), "probes")
    assert sec["alarm"] is True and sec["empty"] == "all green"
    assert [r["tone"] for r in sec["items"]] == ["bad", "bad"]
    assert sec["bad"] == 2


# ---------------------------------------------------------------- what the tab bar counts

def test_each_section_says_what_it_adds_to_its_tab_badge():
    pages = bv.pages(_result(), _profile())
    assert _section(pages, "cal")["weight"] == 2          # the past standup does not count
    assert _section(pages, "commits")["weight"] == 5      # today's commits, not repositories
    assert _section(pages, "probes")["bad"] == 1


def test_badge_false_keeps_a_section_out_of_the_tab_number():
    view = {"pages": [{"id": "day", "sections": ["commits", {"id": "log", "badge": False}]}], "page_rest": "hide"}
    pages = bv.pages(_result(), _profile(view))
    assert _section(pages, "log")["weight"] == 0
    assert _section(pages, "commits")["weight"] == 5


def test_a_skipped_section_keeps_its_place_and_says_why():
    result = _result()
    result["sections"][2] = _sec("mine", "tracker", [], status="skipped", reason="quick mode")
    sec = _section(bv.pages(result, _profile()), "mine")
    assert sec["status"] == "skipped" and sec["items"] == []
    assert sec["empty"] == "nothing"


# ---------------------------------------------------------------- validation

def test_a_good_pages_block_passes():
    view = {"pages": [{"id": "ops", "title": "Ops", "sections": [
        "probes", {"id": "mine", "when": "changed_at", "detail": ["priority"], "link": "url", "empty": "-", "alarm": False}]}],
        "page_rest": "show"}
    assert bv.problems(view, None) == []


def test_a_broken_pages_block_is_named():
    bad = bv.problems({"pages": [{"title": "x"}, {"id": "briefing", "sections": []},
                                 {"id": "a", "sections": [{"id": "s", "colour": "red"}, {"id": "t", "alarm": "yes"}]},
                                 {"id": "a", "sections": ["u"]}],
                       "page_rest": "maybe"}, None)
    text = " | ".join(bad)
    assert "view.pages 1: needs an id" in text
    assert "view.pages 2: briefing is the briefing itself" in text
    assert "view.pages 2: sections must be a non-empty list" in text
    assert "view.pages 3, section s: unknown key colour" in text
    assert "view.pages 3, section t: alarm must be true or false" in text
    assert "view.pages 4: page a listed twice" in text
    assert "view.page_rest must be show or hide" in text


def test_validate_names_a_page_section_the_profile_does_not_have():
    profile = {"schema_version": 1, "scope": "user", "id": "morning",
               "sections": [{"kind": "inbox"}], "view": {"pages": [{"id": "ops", "sections": ["nope"]}]}}
    assert any("view.pages 1: no section 'nope' in this profile" in p for p in bf.profile_problems(profile, "morning"))


def test_an_empty_section_still_carries_every_field():
    profile = {"id": "p", "sections": [{"kind": "command", "id": "probe", "argv": ["true"]}]}
    result = {"collected_at": NOW, "sections": [_sec("probe", "command", [])]}
    assert bv.pages(result, profile) == [{"id": "status", "title": "Status", "sections": [
        {"id": "probe", "kind": "command", "title": "Probe", "status": "ok", "reason": "", "alarm": False, "empty": "nothing",
         "items": [], "total": 0, "weight": 0, "bad": 0, "as_of": None}]}]


def test_collect_json_carries_the_pages(tmp_path, capsys):
    root = tmp_path / "b"
    (root / "work" / "inbox").mkdir(parents=True)
    (root / "work" / "tasks").mkdir(parents=True)
    (root / "bridge-config.yaml").write_text("{}\n", encoding="utf-8")
    path = root / "workflow" / "briefings" / "morning.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump({
        "schema_version": 1, "scope": "user", "id": "morning", "default": True,
        "sections": [{"kind": "tasks"}, {"kind": "command", "id": "probe", "title": "Probe",
                                         "argv": [sys.executable, "-c", "print('[]')"]}],
        "view": {"style": "triage", "pages": [{"id": "ops", "title": "Ops", "sections": ["probe"]}]}}),
        encoding="utf-8")
    assert bf.main(["--root", str(root), "collect", "--json", "--no-save"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert [(p["id"], [s["id"] for s in p["sections"]]) for p in data["pages"]] == [("ops", ["probe"])]


# ---------------------------------------------------------------- links and actions

def test_a_local_file_becomes_a_file_link_when_the_root_is_known(tmp_path):
    (tmp_path / "work" / "tasks" / "x").mkdir(parents=True)
    (tmp_path / "work" / "tasks" / "x" / "STATUS.md").write_text("x", encoding="utf-8")
    result = _result()
    result["sections"][-2]["items"][0]["url"] = "work/tasks/x/STATUS.md"
    rows = _section(bv.pages(result, _profile(), root=tmp_path), "log")["items"]
    assert rows[0]["url"] == (tmp_path / "work" / "tasks" / "x" / "STATUS.md").as_uri()
    # a path that does not exist stays without a link
    result["sections"][-2]["items"][0]["url"] = "work/tasks/gone/STATUS.md"
    assert _section(bv.pages(result, _profile(), root=tmp_path), "log")["items"][0]["url"] is None


def test_a_row_names_its_task_so_a_dashboard_can_open_or_jump_to_its_tab():
    result = _result()
    result["sections"][-2]["items"][0]["task"] = "alpha"
    pages = bv.pages(result, _profile())
    assert _section(pages, "log")["items"][0]["task"] == "alpha"
    assert _section(pages, "log")["items"][1]["task"] is None
    assert _section(pages, "workplace")["items"][0]["task"] == "t"     # a proposed tab is its task


def test_findings_and_tracker_rows_can_be_asked_about_the_rest_not():
    pages = bv.pages(_result(), _profile())
    assert all(r["ask"] for r in _section(pages, "probes")["items"])
    assert all(r["ask"] for r in _section(pages, "mine")["items"])
    assert not any(r["ask"] for r in _section(pages, "cal")["items"] + _section(pages, "commits")["items"])


# ---------------------------------------------------------------- inbox, tasks, a source's own tone

def test_a_source_may_set_the_tone_of_its_rows():
    result = _result()
    result["sections"][1]["items"][0]["tone"] = "none"     # a probe that is information, not a finding
    result["sections"][1]["items"][1]["tone"] = "dim"
    rows = _section(bv.pages(result, _profile()), "probes")["items"]
    assert [r["tone"] for r in rows] == [None, "dim"]


def test_pages_show_every_row_not_only_the_briefings_first_few():
    result = _result()
    result["sections"][-2]["all"] = result["sections"][-2]["items"] + [
        {"id": "z", "title": "Older", "project": "app", "changed_at": "2026-10-01T10:00"}]
    assert len(_section(bv.pages(result, _profile()), "log")["items"]) == 3


def test_inbox_and_task_rows_fill_their_columns_when_a_page_names_them():
    result = _result()
    result["sections"].append(_sec("tasks", "tasks", [
        {"id": "alpha", "title": "Alpha", "state": "doing", "priority": "P1", "project": "acme",
         "blocked_by": "waits for the vendor", "changed_at": "2026-10-07", "url": "work/tasks/alpha/STATUS.md"}]))
    result["sections"][0]["items"][0].update(due="2026-10-08", gate="only-you", kind="decision", task="alpha",
                                             urgency="now")
    view = {"pages": [{"id": "work", "sections": ["inbox", "tasks"]}], "page_rest": "hide"}
    pages = bv.pages(result, _profile(view))
    inbox = _section(pages, "inbox")["items"][0]
    assert inbox["when"] == "today" and inbox["detail"] == "decision · only-you"
    assert inbox["task"] == "alpha" and inbox["ask"] is True and inbox["tone"] == "warn"
    task = _section(pages, "tasks")["items"][0]
    assert task["when"] == "07.10" and task["detail"] == "P1 · acme · waits for the vendor"
    assert task["task"] == "alpha" and task["tone"] == "warn"


# ---------------------------------------------------------------- what a link may be

def test_a_file_link_never_leaves_the_bridge(tmp_path):
    root = tmp_path / "b"
    (root / "work").mkdir(parents=True)
    (tmp_path / "secret").write_text("x", encoding="utf-8")
    result = _result()
    for path in ("../secret", str(tmp_path / "secret")):
        result["sections"][-2]["items"][0]["url"] = path
        assert _section(bv.pages(result, _profile(), root=root), "log")["items"][0]["url"] is None, path


def test_a_web_link_loses_credentials_and_one_with_a_key_in_its_query_is_dropped():
    result = _result()
    items = result["sections"][2]["items"]
    items[0]["url"] = "https://x-access-token:ghp_SECRET@github.com/o/r/pull/7"
    items[1]["url"] = "https://fn.example.test/api/run?code=abc123&x=1"
    rows = _section(bv.pages(result, _profile()), "mine")["items"]
    assert rows[0]["url"] == "https://github.com/o/r/pull/7"
    assert rows[1]["url"] is None


def test_the_rest_page_id_is_reserved_and_a_section_stands_on_one_page_only():
    bad = " | ".join(bv.problems({"pages": [{"id": "more", "sections": ["a"]},
                                            {"id": "x", "sections": ["b"]}, {"id": "y", "sections": ["b"]}]}, None))
    assert "view.pages 1: more is the page for the rest, pick another id" in bad
    assert "view.pages 3: section b already stands on page x" in bad


# ---------------------------------------------------------------- speed

def test_sections_run_side_by_side_and_keep_their_order(tmp_path):
    import time as _time
    root = tmp_path / "b"
    (root / "work" / "inbox").mkdir(parents=True)
    slow = [sys.executable, "-c", "import time, json; time.sleep(1); print('[]')"]
    profile = {"id": "p", "sections": [{"kind": "command", "id": f"s{n}", "argv": slow} for n in range(4)]}
    started = _time.monotonic()
    result = bf.collect(root, profile, bf.Context(root, cfg={}))
    assert _time.monotonic() - started < 2.5          # four seconds one after the other
    assert [s["id"] for s in result["sections"]] == ["s0", "s1", "s2", "s3"]
    assert all(s["status"] == "ok" for s in result["sections"])


def test_only_runs_the_named_kinds_and_marks_the_rest_skipped(tmp_path, capsys):
    root = tmp_path / "b"
    (root / "work" / "inbox").mkdir(parents=True)
    (root / "work" / "tasks").mkdir(parents=True)
    (root / "bridge-config.yaml").write_text("{}\n", encoding="utf-8")
    path = root / "workflow" / "briefings" / "morning.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump({"schema_version": 1, "scope": "user", "id": "morning", "default": True,
                                    "sections": [{"kind": "tasks"}, {"kind": "command", "id": "probe",
                                                                     "argv": [sys.executable, "-c", "print('[]')"]}]}),
                    encoding="utf-8")
    assert bf.main(["--root", str(root), "collect", "--json", "--no-save", "--only", "command"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert {s["id"]: s["status"] for s in data["sections"]} == {"tasks": "skipped", "probe": "ok"}


def test_a_failed_section_tells_its_reason_on_the_page():
    result = _result()
    result["sections"][2] = _sec("mine", "tracker", [], status="error", reason="gh: token invalid")
    assert _section(bv.pages(result, _profile()), "mine")["reason"] == "gh: token invalid"


def test_two_sections_loading_the_same_module_at_once_both_get_it_whole(tmp_path):
    root = tmp_path / "b"
    (root / "work" / "inbox").mkdir(parents=True)
    profile = {"id": "p", "sections": [{"kind": "inbox", "id": f"in{n}"} for n in range(6)]}
    for _ in range(5):
        saved = sys.modules.pop("inbox", None)
        try:
            result = bf.collect(root, profile, bf.Context(root, cfg={}))
        finally:
            if saved is not None:
                sys.modules["inbox"] = saved
        assert [s["status"] for s in result["sections"]] == ["ok"] * 6, [s.get("reason") for s in result["sections"]]



def test_an_advise_section_takes_the_inbox_from_the_briefings_loader(tmp_path, monkeypatch):
    """advise reads the inbox too. Its own loader takes no lock, so beside an inbox section
    it could publish a half-loaded copy over the one that section is loading: inside a
    briefing it must use the module the briefing's loader hands it."""
    root = tmp_path / "b"
    (root / "work" / "inbox").mkdir(parents=True)
    advise = bf._load_module("briefing_advise", ROOT / "skills" / "briefing" / "scripts" / "advise.py")

    def unlocked():
        raise AssertionError("advise loaded the inbox itself, outside the briefing's lock")

    monkeypatch.setattr(advise, "_load_inbox", unlocked)
    profile = {"id": "p", "sections": [{"kind": "inbox", "id": "in"}, {"kind": "advise", "id": "adv"}]}
    result = bf.collect(root, profile, bf.Context(root, cfg={}))
    assert [s["status"] for s in result["sections"]] == ["ok", "ok"], [s.get("reason") for s in result["sections"]]

# ---------------------------------------------------------------- cache

def _cached_profile(argv, minutes=5):
    return {"id": "p", "sections": [{"kind": "command", "id": "slow", "argv": argv, "cache_minutes": minutes}]}


def test_a_section_with_cache_minutes_answers_from_its_last_run_until_they_pass(tmp_path):
    import datetime as _dt
    root = tmp_path / "b"
    (root / "work" / "inbox").mkdir(parents=True)
    marker = tmp_path / "runs"
    argv = [sys.executable, "-c", f"open({str(marker)!r}, 'a').write('x'); print('[{{\"id\": \"1\", \"title\": \"t\"}}]')"]
    at = _dt.datetime(2026, 10, 8, 12, 0)
    first = bf.collect(root, _cached_profile(argv), bf.Context(root, cfg={}, now=at))
    again = bf.collect(root, _cached_profile(argv), bf.Context(root, cfg={}, now=at + _dt.timedelta(minutes=4)))
    assert marker.read_text() == "x"                          # the second run did not ask
    assert [i["title"] for i in again["sections"][0]["items"]] == ["t"]
    assert again["sections"][0]["cached_at"] == "2026-10-08T12:00:00"
    assert "cached_at" not in first["sections"][0]
    bf.collect(root, _cached_profile(argv), bf.Context(root, cfg={}, now=at + _dt.timedelta(minutes=6)))
    assert marker.read_text() == "xx"                         # five minutes passed: asked again


def test_fresh_or_a_changed_section_asks_the_source_again(tmp_path):
    import datetime as _dt
    root = tmp_path / "b"
    (root / "work" / "inbox").mkdir(parents=True)
    marker = tmp_path / "runs"
    argv = [sys.executable, "-c", f"open({str(marker)!r}, 'a').write('x'); print('[]')"]
    at = _dt.datetime(2026, 10, 8, 12, 0)
    bf.collect(root, _cached_profile(argv), bf.Context(root, cfg={}, now=at))
    ctx = bf.Context(root, cfg={}, now=at)
    ctx.fresh = True
    bf.collect(root, _cached_profile(argv), ctx)
    assert marker.read_text() == "xx"
    bf.collect(root, _cached_profile(argv, minutes=9), bf.Context(root, cfg={}, now=at))   # other config: void
    assert marker.read_text() == "xxx"


def test_a_failure_is_never_kept(tmp_path):
    import datetime as _dt
    root = tmp_path / "b"
    (root / "work" / "inbox").mkdir(parents=True)
    at = _dt.datetime(2026, 10, 8, 12, 0)
    failing = bf.collect(root, _cached_profile([sys.executable, "-c", "import sys; sys.exit(3)"]),
                         bf.Context(root, cfg={}, now=at))
    assert failing["sections"][0]["status"] == "error"
    assert not (root / ".bridge" / "briefing-cache").exists()


def test_cache_minutes_is_validated():
    profile = {"schema_version": 1, "scope": "user", "id": "morning",
               "sections": [{"kind": "inbox", "cache_minutes": 0}]}
    assert any("cache_minutes must be a positive whole number" in p for p in bf.profile_problems(profile, "morning"))


def test_a_cached_section_says_when_its_source_last_answered():
    result = _result()
    result["sections"][2]["cached_at"] = "2026-10-08T11:55:00"
    assert _section(bv.pages(result, _profile()), "mine")["as_of"] == "11:55"
    assert _section(bv.pages(_result(), _profile()), "mine")["as_of"] is None


# ---------------------------------------------------------------- marks

def _marked(marks):
    profile = _profile()
    profile["view"] = {**profile.get("view", {}), "marks": marks}
    return profile


def test_a_mark_labels_every_row_that_names_one_of_its_words():
    profile = _marked([{"label": "ACME", "match": ["acme/"], "color": "magenta"}, {"label": "Login", "match": "login"}])
    rows = _section(bv.pages(_result(), profile), "mine")["items"]
    assert rows[0]["mark"] == {"label": "ACME", "color": "magenta"}    # first mark wins over Login
    assert rows[1]["mark"] == {"label": "ACME", "color": "magenta"}    # matched through its url
    assert _section(bv.pages(_result(), profile), "probes")["items"][0]["mark"] is None


def test_marks_reach_the_briefing_rows_too():
    profile = _marked([{"label": "VENDOR", "match": "vendor"}])
    rows = [r for b in bv.build(_result(), profile)["buckets"] for r in b["items"]]
    marked = [r for r in rows if r.get("mark")]
    assert [r["title"] for r in marked] == ["Answer the vendor"]
    assert marked[0]["mark"] == {"label": "VENDOR", "color": None}


def test_marks_are_validated():
    view = {"marks": [{"label": "", "match": []}, {"label": "X", "match": "x", "color": "pink", "extra": 1}, "nope"]}
    problems = bv.problems(view, None)
    assert "view.marks[0].label must be text of 1 to 16 characters" in problems
    assert "view.marks[0].match must be text or a list of text" in problems
    assert any(p.startswith("view.marks[1].color must be one of") for p in problems)
    assert "view.marks[1]: unknown key extra" in problems
    assert "view.marks[2] must be a mapping" in problems


def test_the_text_views_put_the_mark_in_front_of_the_title():
    profile = _marked([{"label": "VENDOR", "match": "vendor"}])
    for style in ("triage", "report"):
        text = bf.render_view(_result(), profile, style=style)
        assert "[VENDOR] " in text and "Answer the vendor" in text, style


def test_a_cached_answer_never_crosses_midnight(tmp_path):
    import datetime as _dt
    root = tmp_path / "b"
    (root / "work" / "inbox").mkdir(parents=True)
    marker = tmp_path / "runs"
    argv = [sys.executable, "-c", f"open({str(marker)!r}, 'a').write('x'); print('[]')"]
    bf.collect(root, _cached_profile(argv, minutes=60), bf.Context(root, cfg={}, now=_dt.datetime(2026, 10, 8, 23, 50)))
    bf.collect(root, _cached_profile(argv, minutes=60), bf.Context(root, cfg={}, now=_dt.datetime(2026, 10, 9, 0, 5)))
    assert marker.read_text() == "xx"
