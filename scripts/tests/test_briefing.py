# SPDX-License-Identifier: MIT
"""Contract for scripts/briefing.py: a briefing is a profile file the Bridge executes.

Every person describes the briefing they want in workflow/briefings/<id>.yaml:
which sections, in which order, which tracker with which query, which rows
become inbox items. The script collects deterministically (a failing section is
an error line, never an abort) and the agent only advises on and renders the
result. Without any profile a built-in one keeps today's behaviour.

Trackers are tested against recorded CLI and HTTP answers under
scripts/tests/fixtures/briefing/<provider>/, never against a live service.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "scripts" / "tests" / "fixtures" / "briefing"
sys.dont_write_bytecode = True


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


bf = _load("briefing", ROOT / "scripts" / "briefing.py")
inbox = sys.modules.get("inbox") or _load("inbox", ROOT / "scripts" / "inbox.py")

NOW = dt.datetime(2026, 10, 4, 8, 0)


class FakeRun:
    """Answers argv by prefix from recorded output; records every call."""

    def __init__(self, answers: dict | None = None):
        self.answers = answers or {}
        self.calls: list = []

    def __call__(self, argv, timeout=30, cwd=None):
        self.calls.append(list(argv))
        for prefix, answer in self.answers.items():
            if tuple(argv[: len(prefix)]) == prefix:
                if isinstance(answer, Exception):
                    raise answer
                return answer(argv) if callable(answer) else answer
        raise bf.SourceError(f"no recorded answer for {argv[:4]}")


def bridge(tmp_path: Path, config: dict | None = None, profiles: dict | None = None) -> Path:
    root = tmp_path / "bridge"
    (root / "work" / "inbox").mkdir(parents=True)
    (root / "work" / "tasks").mkdir(parents=True)
    (root / "bridge-config.yaml").write_text(yaml.safe_dump(config or {}), encoding="utf-8")
    for pid, data in (profiles or {}).items():
        path = root / "workflow" / "briefings" / f"{pid}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump({"schema_version": 1, "scope": "user", "id": pid, **data}),
                        encoding="utf-8")
    return root


def task(root: Path, slug: str, **fm) -> None:
    d = root / "work" / "tasks" / slug
    d.mkdir(parents=True)
    fm = {"slug": slug, "status": "doing", "last_updated": "2026-10-03", **fm}
    (d / "STATUS.md").write_text(f"---\n{yaml.safe_dump(fm)}---\n\n# {slug}\n", encoding="utf-8")


def ctx(root: Path, run=None, **kw):
    return bf.Context(root, now=NOW, run=run or FakeRun(), **kw)


SECTIONS = [{"kind": "tasks", "status": ["doing"]}]


# ---------------------------------------------------------------- discovery

def test_list_finds_profiles_and_skips_reserved_files(tmp_path):
    root = bridge(tmp_path, profiles={"morning": {"sections": SECTIONS, "default": True},
                                      "customer-x": {"sections": SECTIONS, "title": "Customer X"}})
    (root / "workflow" / "briefings" / "_template.yaml").write_text("id: nope\n", encoding="utf-8")
    ids = [p["id"] for p in bf.load_profiles(root)]
    assert ids == ["customer-x", "morning"]


def test_select_prefers_default_flag_then_config_then_single(tmp_path):
    root = bridge(tmp_path, profiles={"a": {"sections": SECTIONS}, "b": {"sections": SECTIONS, "default": True}})
    assert bf.select(root, {})["id"] == "b"
    assert bf.select(root, {"briefing": {"default": "a"}})["id"] == "a"
    assert bf.select(root, {}, "a")["id"] == "a"
    one = bridge(tmp_path / "one", profiles={"only": {"sections": SECTIONS}})
    assert bf.select(one, {})["id"] == "only"


def test_select_without_a_default_among_several_names_the_choices(tmp_path):
    root = bridge(tmp_path, profiles={"a": {"sections": SECTIONS}, "b": {"sections": SECTIONS}})
    with pytest.raises(bf.Ambiguous) as exc:
        bf.select(root, {})
    assert exc.value.ids == ["a", "b"]
    with pytest.raises(bf.UnknownProfile):
        bf.select(root, {}, "c")


def test_without_profiles_the_builtin_keeps_todays_briefing(tmp_path):
    root = bridge(tmp_path, config={"integrations": {"github": {"enabled": True}}})
    profile = bf.select(root, {"integrations": {"github": {"enabled": True}}})
    assert profile["id"] == "builtin"
    kinds = [s["kind"] for s in profile["sections"]]
    assert kinds[:3] == ["inbox", "advise", "tasks"]
    assert "activity" in kinds and "calendar" in kinds
    assert any(s.get("provider") == "github-board" for s in profile["sections"])
    bare = bf.builtin_profile({})
    assert not any(s["kind"] == "tracker" for s in bare["sections"])


def test_offer_matches_the_profiles_vocabulary(tmp_path):
    root = bridge(tmp_path, profiles={
        "morning": {"sections": SECTIONS, "offer_on": ["good morning"]},
        "acme": {"sections": SECTIONS, "offer_on": ["acme", "customer review"]}})
    profiles = bf.load_profiles(root)
    assert bf.offer(profiles, "Good morning, what is up?") == ["morning"]
    assert bf.offer(profiles, "prep the ACME call") == ["acme"]
    assert bf.offer(profiles, "lunch") == []


# ---------------------------------------------------------------- validation

def test_validate_names_every_broken_profile(tmp_path):
    root = bridge(tmp_path, profiles={
        "good": {"sections": SECTIONS, "default": True},
        "also-default": {"sections": SECTIONS, "default": True},
        "wrongname": {"sections": SECTIONS},
        "bad-kind": {"sections": [{"kind": "weather"}]},
        "no-provider": {"sections": [{"kind": "tracker"}]},
        "odd-provider": {"sections": [{"kind": "tracker", "provider": "trello"}]},
        "bad-rule": {"sections": [{"kind": "tasks", "to_inbox": [{"urgency": "now"}]}]},
        "dup-ids": {"sections": [{"kind": "tasks"}, {"kind": "tasks"}]},
        "stray-key": {"sections": [{"kind": "tasks", "token": "abc"}]},
        "inline-secret": {"sections": [{"kind": "tracker", "provider": "jira",
                                        "query": {"jql": "x", "api_token": "s3cr3t"}}]},
    })
    path = root / "workflow" / "briefings" / "wrongname.yaml"
    data = yaml.safe_load(path.read_text())
    data["id"] = "other"
    path.write_text(yaml.safe_dump(data))
    problems = "\n".join(bf.validate(root))
    for pid in ("also-default", "wrongname", "bad-kind", "no-provider", "odd-provider", "bad-rule",
                "dup-ids", "stray-key", "inline-secret"):
        assert pid in problems, pid
    assert "good.yaml" not in problems


def test_validate_accepts_the_shipped_template_and_examples():
    template = ROOT / "workflow" / "briefings" / "_template.yaml"
    data = yaml.safe_load(template.read_text(encoding="utf-8"))
    assert bf.profile_problems(data, data["id"]) == []
    examples = sorted(ROOT.glob("examples/*/workflow/briefings/*.yaml"))
    assert examples, "ship at least one worked example profile"
    for path in examples:
        assert bf.profile_problems(yaml.safe_load(path.read_text(encoding="utf-8")), path.stem) == [], path


def test_template_satisfies_the_json_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = yaml.safe_load((ROOT / "workflow" / "briefings" / "_schema.yaml").read_text(encoding="utf-8"))
    data = yaml.safe_load((ROOT / "workflow" / "briefings" / "_template.yaml").read_text(encoding="utf-8"))
    jsonschema.validate(data, schema)


# ---------------------------------------------------------------- collecting

def test_tasks_section_filters_by_status_and_context(tmp_path):
    root = bridge(tmp_path)
    task(root, "alpha", context="acme")
    task(root, "beta", status="review", context="other")
    task(root, "gamma", status="backlog")
    profile = {"id": "p", "sections": [{"kind": "tasks", "status": ["doing", "review"]},
                                       {"kind": "tasks", "id": "acme", "contexts": ["acme"]}]}
    result = bf.collect(root, profile, ctx(root))
    first, second = result["sections"]
    assert [i["id"] for i in first["items"]] == ["alpha", "beta"]
    assert first["status"] == "ok"
    assert [i["id"] for i in second["items"]] == ["alpha"]


def test_a_failing_section_is_an_error_line_not_an_abort(tmp_path):
    root = bridge(tmp_path)
    task(root, "alpha")
    run = FakeRun({("gh",): bf.SourceError("gh: not logged in")})
    profile = {"id": "p", "sections": [
        {"kind": "tracker", "provider": "github", "query": {"assignee": "@me"}},
        {"kind": "tasks"}]}
    result = bf.collect(root, profile, ctx(root, run))
    gh, tasks = result["sections"]
    assert gh["status"] == "error" and "not logged in" in gh["reason"]
    assert tasks["status"] == "ok" and tasks["items"]


def test_an_unexpected_exception_in_a_section_is_contained(tmp_path, monkeypatch):
    root = bridge(tmp_path)
    monkeypatch.setitem(bf.KINDS, "tasks", lambda section, c: 1 / 0)
    result = bf.collect(root, {"id": "p", "sections": [{"kind": "tasks"}]}, ctx(root))
    assert result["sections"][0]["status"] == "error"
    assert "ZeroDivisionError" in result["sections"][0]["reason"]


def gh_answers():
    issues = (FIX / "github" / "search-issues.json").read_text()
    prs = (FIX / "github" / "search-prs.json").read_text()
    review = (FIX / "github" / "review-requested.json").read_text()
    return {("gh", "api", "user"): '{"login": "octo"}',
            ("gh", "search", "issues"): issues,
            ("gh", "search", "prs"): lambda argv: review if "--review-requested" in argv else prs}


def test_github_provider_normalizes_issues_prs_and_review_requests(tmp_path):
    root = bridge(tmp_path)
    run = FakeRun(gh_answers())
    section = {"kind": "tracker", "provider": "github",
               "query": {"assignee": "@me", "owners": ["example-org"], "kinds": ["issues", "prs"],
                         "review_requested": True}}
    result = bf.collect(root, {"id": "p", "sections": [section]}, ctx(root, run))
    items = {i["id"]: i for i in result["sections"][0]["items"]}
    assert set(items) == {"example-org/tool#12", "example-org/site#7", "example-org/tool#31",
                          "example-org/tool#33", "example-org/tool#40"}
    assert items["example-org/tool#12"]["state"] == "ready"
    assert items["example-org/site#7"]["state"] == "blocked"          # a `blocked` label
    assert items["example-org/tool#31"]["state"] == "review"
    assert items["example-org/tool#33"]["state"] == "in_progress"     # a draft PR
    assert items["example-org/tool#40"]["assigned_to_me"] is True     # asked to review it
    assert items["example-org/tool#40"]["category"] == "qa"
    assert all(i["tracker"] == "github" for i in items.values())
    search = [c for c in run.calls if c[:3] == ["gh", "search", "issues"]][0]
    assert "--owner" in search and "example-org" in search and "--assignee" in search
    # newest first
    assert result["sections"][0]["items"][0]["changed_at"] >= result["sections"][0]["items"][-1]["changed_at"]


def test_github_board_provider_reuses_tracker_sync_and_the_registry(tmp_path):
    root = bridge(tmp_path, config={"integrations": {"github": {"assignee_me": "octo"}}})
    (root / "ecosystem.yaml").write_text(yaml.safe_dump({"github_projects": [
        {"org": "example-org", "number": 3, "name": "Tool board"}]}), encoding="utf-8")
    run = FakeRun({("gh", "project", "item-list"): (FIX / "github-board" / "item-list.json").read_text()})
    section = {"kind": "tracker", "provider": "github-board", "query": {"assigned_to_me": True}}
    result = bf.collect(root, {"id": "p", "sections": [section]}, ctx(root, run))
    sec = result["sections"][0]
    assert sec["status"] == "ok", sec.get("reason")
    assert [i["id"] for i in sec["items"]] == ["example-org/tool#5"]     # done + others' cards filtered
    assert sec["items"][0]["state"] == "in_progress" and sec["items"][0]["project"] == "Tool board"
    every = dict(section, query={"include_done": True})
    states = {i["state"] for i in bf.collect(root, {"id": "p", "sections": [every]},
                                             ctx(root, run))["sections"][0]["items"]}
    assert states == {"in_progress", "done", "blocked"}


def test_section_state_map_overrides_the_provider(tmp_path):
    root = bridge(tmp_path)
    run = FakeRun(gh_answers())
    section = {"kind": "tracker", "provider": "github", "query": {"assignee": "@me", "kinds": ["issues"]},
               "state_map": {"open": "in_progress"}}
    items = bf.collect(root, {"id": "p", "sections": [section]}, ctx(root, run))["sections"][0]["items"]
    assert {i["id"]: i["state"] for i in items}["example-org/tool#12"] == "in_progress"


def test_command_section_reads_json_from_any_program(tmp_path):
    root = bridge(tmp_path)
    script = root / "source.py"
    script.write_text("import json; print(json.dumps([{'id': 'X-1', 'title': 'From my tool', 'state': 'ready'}]))")
    bad = root / "bad.py"
    bad.write_text("print('not json')")
    profile = {"id": "p", "sections": [
        {"kind": "command", "id": "mine", "argv": [sys.executable, "source.py"]},
        {"kind": "command", "id": "broken", "argv": [sys.executable, "bad.py"]}]}
    good, broken = bf.collect(root, profile, bf.Context(root, now=NOW))["sections"]
    assert good["items"][0]["title"] == "From my tool" and good["items"][0]["tracker"] == "mine"
    assert broken["status"] == "error"


def test_max_caps_items_but_keeps_the_total(tmp_path):
    root = bridge(tmp_path)
    for s in ("a", "b", "c"):
        task(root, s)
    sec = bf.collect(root, {"id": "p", "sections": [{"kind": "tasks", "max": 2}]}, ctx(root))["sections"][0]
    assert len(sec["items"]) == 2 and sec["total"] == 3


def test_inbox_section_lists_open_items(tmp_path):
    root = bridge(tmp_path)
    box = inbox.Inbox(root / "work" / "inbox", actor="t", clock=lambda: NOW)
    a = box.add(source="t", kind="decision", summary="Merge the fix?", urgency="now")
    b = box.add(source="t", kind="finding", summary="Old thing")
    box.close(b)
    sec = bf.collect(root, {"id": "p", "sections": [{"kind": "inbox"}]}, ctx(root))["sections"][0]
    assert [i["id"] for i in sec["items"]] == [a]
    assert sec["items"][0]["urgency"] == "now"


def test_activity_section_reads_recent_log_rows(tmp_path):
    root = bridge(tmp_path)
    (root / "work" / "log.md").write_text(textwrap.dedent("""\
        # Log

        ## Thursday 24.09
        | 2026-09-24 10:00 | 💻 | old | too old |

        ## Saturday 03.10
        | 2026-10-03 09:00 | 💻 | tool | shipped the parser |
        | 2026-10-03 11:00 | 📋 | site | planned the page |
        """), encoding="utf-8")
    sec = bf.collect(root, {"id": "p", "sections": [{"kind": "activity", "days": 7}]}, ctx(root))["sections"][0]
    assert [i["title"] for i in sec["items"]] == ["planned the page", "shipped the parser"]
    assert sec["items"][0]["project"] == "site"


def test_calendar_icalbuddy_and_ics(tmp_path):
    root = bridge(tmp_path)
    run = FakeRun({("icalBuddy",): (FIX / "calendar" / "icalbuddy.txt").read_text(encoding="utf-8")})
    sec = bf.collect(root, {"id": "p", "sections": [{"kind": "calendar", "provider": "icalbuddy", "days": 1}]},
                     ctx(root, run))["sections"][0]
    assert sec["status"] == "ok", sec.get("reason")
    assert [(i["title"], i["start"]) for i in sec["items"]] == [
        ("Standup", "2026-10-04T09:00"), ("Customer review", "2026-10-04T14:00"), ("Holiday", "2026-10-05")]
    call = run.calls[0]
    assert "-nrd" in call and "eventsToday+1" in call
    ics = {"kind": "calendar", "provider": "ics", "path": str(FIX / "calendar" / "sample.ics"), "days": 2}
    items = bf.collect(root, {"id": "p", "sections": [ics]}, ctx(root))["sections"][0]["items"]
    assert [i["title"] for i in items] == ["Planning", "All day"]


def test_calendar_auto_without_icalbuddy_is_skipped_not_an_error(tmp_path, monkeypatch):
    root = bridge(tmp_path)
    monkeypatch.setattr(bf.shutil, "which", lambda name: None)
    sec = bf.collect(root, {"id": "p", "sections": [{"kind": "calendar", "provider": "auto"}]},
                     ctx(root))["sections"][0]
    assert sec["status"] == "skipped"


def test_advise_section_sees_the_calendar_wherever_it_stands(tmp_path):
    root = bridge(tmp_path)
    box = inbox.Inbox(root / "work" / "inbox", actor="t", clock=lambda: NOW)
    box.add(source="t", kind="decision", summary="Call the vendor", due="2026-10-04T14:15")
    run = FakeRun({("icalBuddy",): (FIX / "calendar" / "icalbuddy.txt").read_text(encoding="utf-8")})
    profile = {"id": "p", "sections": [{"kind": "advise"},
                                       {"kind": "calendar", "provider": "icalbuddy", "days": 1}]}
    advice = bf.collect(root, profile, ctx(root, run))["sections"][0]
    assert any(i.get("check") == "collision" for i in advice["items"]), advice


def test_workplace_section_uses_the_none_driver_without_config(tmp_path):
    root = bridge(tmp_path)
    task(root, "alpha")
    sec = bf.collect(root, {"id": "p", "sections": [{"kind": "workplace"}]}, ctx(root))["sections"][0]
    assert sec["status"] == "ok", sec.get("reason")
    assert sec["plan"]["workspaces"] and sec["items"][0]["id"] == "alpha"


# ---------------------------------------------------------------- change marks and inbox

def test_rows_are_marked_new_or_changed_against_the_last_run(tmp_path):
    root = bridge(tmp_path)
    task(root, "alpha")
    task(root, "beta")
    profile = {"id": "p", "sections": [{"kind": "tasks", "status": ["doing", "review"]}]}
    first = bf.collect(root, profile, ctx(root))
    assert all(i["new"] for i in first["sections"][0]["items"])
    bf.save_snapshot(root, first)
    (root / "work" / "tasks" / "beta" / "STATUS.md").write_text(
        "---\nslug: beta\nstatus: review\nlast_updated: 2026-10-04\n---\n", encoding="utf-8")
    task(root, "gamma")
    second = bf.collect(root, profile, ctx(root), previous=bf.load_snapshot(root, "p"))
    marks = {i["id"]: (i["new"], i["changed"]) for i in second["sections"][0]["items"]}
    assert marks == {"alpha": (False, False), "beta": (False, True), "gamma": (True, False)}
    assert (root / ".bridge" / "briefings" / "p.last.json").is_file()


def test_to_inbox_files_matching_rows_and_closes_them_when_gone(tmp_path):
    root = bridge(tmp_path)
    run = FakeRun(gh_answers())
    section = {"kind": "tracker", "id": "gh", "provider": "github",
               "query": {"assignee": "@me", "kinds": ["issues"]},
               "to_inbox": [{"when": {"state": "blocked"}, "urgency": "now"}]}
    profile = {"id": "morning", "sections": [section]}
    box = inbox.Inbox(root / "work" / "inbox", actor="t", clock=lambda: NOW)
    filed, closed = bf.file_to_inbox(box, profile, bf.collect(root, profile, ctx(root, run)))
    assert (filed, closed) == (1, 0)
    item = box.open_items()[0]
    assert item.key == "briefing:morning:gh:example-org/site#7" and item.urgency == "now"
    assert "Write the onboarding page" in item.summary

    # a run where the section FAILED must not close it
    broken = FakeRun({("gh",): bf.SourceError("offline")})
    assert bf.file_to_inbox(box, profile, bf.collect(root, profile, ctx(root, broken))) == (0, 0)
    assert len(box.open_items()) == 1

    # the row is gone on a good run: closed
    clean = json.loads((FIX / "github" / "search-issues.json").read_text())[:1]
    run2 = FakeRun({**gh_answers(), ("gh", "search", "issues"): json.dumps(clean)})
    assert bf.file_to_inbox(box, profile, bf.collect(root, profile, ctx(root, run2))) == (0, 1)
    assert box.open_items() == []


def test_to_inbox_rule_matches_lists_and_booleans(tmp_path):
    assert bf.rule_matches({"state": ["review", "blocked"], "assigned_to_me": True},
                           {"state": "review", "assigned_to_me": True})
    assert not bf.rule_matches({"state": "review", "assigned_to_me": True},
                               {"state": "review", "assigned_to_me": False})
    assert not bf.rule_matches({"labels": "urgent"}, {"labels": ["later"]})
    assert bf.rule_matches({"labels": "urgent"}, {"labels": ["urgent", "x"]})


# ---------------------------------------------------------------- rendering and CLI

def test_render_shows_sections_in_order_with_marks_and_errors(tmp_path):
    result = {"profile": "p", "title": "Morning", "collected_at": "2026-10-04T08:00", "sections": [
        {"id": "gh", "kind": "tracker", "title": "GitHub", "status": "error", "reason": "gh: offline",
         "items": [], "total": 0},
        {"id": "tasks", "kind": "tasks", "title": "Tasks", "status": "ok", "total": 3, "items": [
            {"id": "alpha", "title": "alpha", "state": "doing", "new": True, "changed": False}]}]}
    text = bf.render(result)
    assert text.index("GitHub") < text.index("Tasks")
    assert "gh: offline" in text and "alpha" in text and "new" in text and "1 of 3" in text


def test_cli_collect_json_saves_a_snapshot_and_asks_when_ambiguous(tmp_path, capsys):
    root = bridge(tmp_path, profiles={"a": {"sections": SECTIONS}, "b": {"sections": SECTIONS}})
    task(root, "alpha")
    assert bf.main(["--root", str(root), "collect"]) == 2
    assert "a, b" in capsys.readouterr().err
    assert bf.main(["--root", str(root), "collect", "a", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["profile"] == "a" and data["sections"][0]["items"][0]["id"] == "alpha"
    assert (root / ".bridge" / "briefings" / "a.last.json").is_file()
    assert bf.main(["--root", str(root), "list"]) == 0
    assert "a" in capsys.readouterr().out
    assert bf.main(["--root", str(root), "validate"]) == 0


def test_cli_validate_fails_on_a_broken_profile(tmp_path, capsys):
    root = bridge(tmp_path, profiles={"bad": {"sections": [{"kind": "weather"}]}})
    assert bf.main(["--root", str(root), "validate"]) == 1
    assert "bad" in capsys.readouterr().out


def test_a_token_quoted_by_a_failing_adapter_is_redacted(tmp_path, monkeypatch):
    root = bridge(tmp_path)

    def leaky(section, c):
        token = c.secret("keychain://example/token")
        raise RuntimeError(f"request failed with Authorization: Bearer {token}")

    monkeypatch.setitem(bf.KINDS, "tasks", leaky)
    c = bf.Context(root, now=NOW, secret=lambda ref: "tok-very-secret")
    result = bf.collect(root, {"id": "p", "sections": [{"kind": "tasks"}]}, c)
    assert "tok-very-secret" not in json.dumps(result)
    assert "[redacted]" in result["sections"][0]["reason"]


def test_default_http_gets_the_profile_timeout(tmp_path, monkeypatch):
    root = bridge(tmp_path)
    seen = {}
    monkeypatch.setattr(bf, "_default_http", lambda m, u, h=None, b=None, timeout=None: seen.update(t=timeout))
    c = bf.Context(root, now=NOW)
    bf.collect(root, {"id": "p", "timeout_sec": 7, "sections": [{"kind": "tasks"}]}, c)
    c.http("GET", "https://example.invalid/x")
    assert seen["t"] == 7
