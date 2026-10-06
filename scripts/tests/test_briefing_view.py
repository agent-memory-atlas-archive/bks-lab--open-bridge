# SPDX-License-Identifier: MIT
"""Contract for scripts/lib/briefing_view.py: how a briefing is shown, chosen per profile.

The sections of a profile say where the data comes from. The `view:` block says how
the reader sees it. `style: sources` (the default) prints one block per section, the
briefing as it always was. `triage` sorts every row by what to DO with it (do, plan,
delegate, waiting, drop), shows a thing once even when two sources carry it, and puts
housekeeping last. `brevity` is the bottom line plus the top three with why they
matter. `plan` lays the day's work into the free gaps of the calendar.

All of it is computed here, deterministically, so the shape does not depend on which
agent renders it or what that agent remembered.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import re
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
bv = _load("briefing_view", ROOT / "scripts" / "lib" / "briefing_view.py")
inbox = sys.modules.get("inbox") or _load("inbox", ROOT / "scripts" / "inbox.py")

NOW = dt.datetime(2026, 10, 5, 7, 45)
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def sec(sid, kind, items, status="ok", title=None, **extra):
    return {"id": sid, "kind": kind, "title": title or sid, "status": status, "items": items, "all": items,
            "total": len(items), **extra}


def result(*sections, previous_at=None):
    out = {"profile": "morning", "title": "Morning", "collected_at": NOW.isoformat(timespec="minutes"),
           "sections": list(sections)}
    if previous_at:
        out["previous_at"] = previous_at
    return out


def profile(view=None, mutes=None, sections=None, **extra):
    p = {"schema_version": 1, "scope": "user", "id": "morning", "for": "alice",
         "sections": sections or [{"kind": "inbox"}, {"kind": "advise"}, {"kind": "tasks"},
                                  {"kind": "tracker", "id": "gh", "provider": "github"},
                                  {"kind": "tracker", "id": "board", "provider": "github-board"},
                                  {"kind": "calendar"}, {"kind": "activity"}, {"kind": "workplace"}]}
    if view is not None:
        p["view"] = view
    if mutes is not None:
        p["mutes"] = mutes
    return {**p, **extra}


def inbox_item(iid, title, urgency="today", kind="decision", gate="your-yes", due=None, **kw):
    return {"id": iid, "title": title, "state": kw.pop("state", "open"), "urgency": urgency, "kind": kind,
            "gate": gate, "due": due, "task": kw.pop("task", None), **kw}


def task_item(slug, title=None, nxt=None, blocked_by=None, changed_at="2026-10-04", state="doing"):
    return {"id": slug, "title": title or slug, "state": state, "next": nxt, "blocked_by": blocked_by,
            "changed_at": changed_at, "url": f"work/tasks/{slug}/STATUS.md"}


def buckets(view):
    return {b["id"]: [i["title"] for i in b["items"]] for b in view["buckets"]}


def sample():
    return result(
        sec("inbox", "inbox", [inbox_item("i1", "Post the launch note", gate="only-you", due="2026-10-06T15:00"),
                               inbox_item("i2", "Reschedule the sparring", urgency="later", kind="question")]),
        sec("advise", "advise", [
            {"id": "advise:quiet:keys", "title": "keys untouched for 7 days (park?)", "check": "quiet",
             "urgency": "later", "task": "keys"},
            {"id": "advise:wip:cap", "title": "9 tasks active, cap 8: close or park one", "check": "wip",
             "urgency": "later"}]),
        sec("tasks", "tasks", [
            task_item("typesafe", "CV matching", nxt={"what": "Draft the TypeSafe request", "who": "bridge"}),
            task_item("timesheet", "Time tracking", nxt={"what": "Sketch the data model", "who": "me"}),
            task_item("austria", "Austria onboarding", blocked_by="test run at the customer",
                      changed_at="2026-09-18"),
            task_item("a2a", "Bridge to bridge", nxt={"what": "Free up the mini", "who": "axel"},
                      changed_at="2026-10-01"),
            task_item("keys", "Keychain backup", nxt={"what": "Restore test", "who": "me"}),
            task_item("bare", "Task without next step")]),
        sec("gh", "tracker", [{"id": "acme/infra#17", "title": "Time tracking requirements", "state": "new",
                               "category": "open", "url": "https://github.com/acme/infra/issues/17"}]),
        sec("board", "tracker", [{"id": "acme/infra#17", "title": "Time tracking requirements", "state": "new",
                                  "category": "open", "url": "https://github.com/acme/infra/issues/17"}]),
        sec("calendar", "calendar", [{"id": "c1", "title": "Football training", "start": "2026-10-05T16:30",
                                      "end": "2026-10-05T18:00"},
                                     {"id": "c2", "title": "Mini review", "start": "2026-10-06T16:00",
                                      "end": "2026-10-06T17:00"}]),
        sec("activity", "activity", [{"id": "x", "title": "rebuilt the daemon", "changed_at": "2026-10-04T22:59",
                                      "project": "k2a", "new": True}]),
        sec("workplace", "workplace", [{"id": "a2a", "title": "Bridge to bridge", "state": "resume"},
                                       {"id": "typesafe", "title": "CV matching", "state": "new"}]),
    )


# ---------------------------------------------------------------- the choice

def test_without_a_view_block_the_briefing_is_the_one_it_always_was():
    r = result(sec("tasks", "tasks", [task_item("alpha")]))
    assert bv.style_of(profile()) == "sources"
    assert bf.render_view(r, profile()) == bf.render(bf._public(r))


def test_style_comes_from_the_profile_and_a_flag_overrides_it_once():
    p = profile(view={"style": "triage"})
    assert bv.style_of(p) == "triage"
    assert bv.style_of(p, "brevity") == "brevity"


def test_the_view_block_is_validated():
    assert bv.problems({"style": "triage", "max_items": 10, "buckets": [{"id": "do", "title": "Do"}]}, []) == []
    bad = bv.problems({"style": "fancy", "max_items": 0, "colour": "x", "buckets": [{"id": "later"}],
                       "plan": {"workday": {"start": "8"}}}, [{"section": "advise"}])
    text = " | ".join(bad)
    for needle in ("style", "max_items", "colour", "later", "workday", "mutes"):
        assert needle in text, needle


def test_profile_validation_knows_view_mutes_and_section_bucket(tmp_path):
    data = profile(view={"style": "triage"}, mutes=[{"section": "advise", "when": {"check": "quiet"}}])
    data["sections"][1]["bucket"] = "drop"
    assert bf.profile_problems(data, "morning") == []
    data["sections"][1]["bucket"] = "someday"
    assert any("bucket" in p for p in bf.profile_problems(data, "morning"))


# ---------------------------------------------------------------- triage: one place per thing

def test_triage_sorts_every_row_by_what_to_do_with_it():
    view = bv.build(sample(), profile(view={"style": "triage"}))
    b = buckets(view)
    assert "Post the launch note" in b["do"]                    # only you, due tomorrow
    assert "Reschedule the sparring" in b["plan"]               # yours, no date
    assert "Sketch the data model" in b["plan"]                 # next step who: me
    assert "Draft the TypeSafe request" in b["delegate"]        # next step who: bridge
    assert "Austria onboarding" in b["waiting"]                 # blocked_by
    assert "Free up the mini" in b["waiting"]                   # next step at another person
    assert any("keys" in t for t in b["drop"])                  # quiet task: park?
    assert not any("Restore test" in t for t in b["plan"])      # a quiet task is shown once, under drop


def test_a_thing_two_sources_carry_is_shown_once_with_both_sources():
    view = bv.build(sample(), profile(view={"style": "triage"}))
    rows = [i for b in view["buckets"] for i in b["items"] if i["title"] == "Time tracking requirements"]
    assert len(rows) == 1
    assert rows[0]["sources"] == ["gh", "board"]


def test_housekeeping_goes_last_and_names_tasks_without_a_next_step():
    view = bv.build(sample(), profile(view={"style": "triage"}))
    text = " | ".join(view["hygiene"])
    assert "9 tasks active" in text
    assert "bare" in text                                        # no next step: said, not hidden
    out = ANSI.sub("", bv.draw(view))
    assert out.index("Waiting") < out.index("9 tasks active")


def test_waiting_shows_how_long_and_nudges_after_the_threshold():
    view = bv.build(sample(), profile(view={"style": "triage",
                                            "buckets": [{"id": "waiting", "nudge_after_days": 7}]}))
    row = next(i for b in view["buckets"] for i in b["items"] if i["title"] == "Austria onboarding")
    assert any("17" in w for w in row["why"])
    assert row.get("nudge") is True


def test_a_failed_section_is_a_housekeeping_line_not_a_hole():
    r = sample()
    r["sections"][3] = sec("gh", "tracker", [], status="error", reason="API rate limit")
    view = bv.build(r, profile(view={"style": "triage"}))
    assert any("API rate limit" in h for h in view["hygiene"])


def test_mutes_hide_matching_rows_and_say_how_many():
    view = bv.build(sample(), profile(view={"style": "triage"},
                                      mutes=[{"section": "advise", "when": {"check": "quiet"}}]))
    assert not any("keys" in t for t in buckets(view).get("drop", []))
    assert "Restore test" in buckets(view)["plan"]               # the task itself is back in its bucket
    assert any("1 muted" in h for h in view["hygiene"])


def test_a_section_can_force_its_bucket():
    p = profile(view={"style": "triage"})
    p["sections"][3]["bucket"] = "delegate"
    assert "Time tracking requirements" in buckets(bv.build(sample(), p))["delegate"]


def test_a_bucket_left_out_of_the_list_is_hidden_and_counted():
    view = bv.build(sample(), profile(view={"style": "triage", "buckets": [{"id": "do"}, {"id": "plan"}]}))
    assert [b["id"] for b in view["buckets"]] == ["do", "plan"]
    assert any("hidden" in h for h in view["hygiene"])


def test_bucket_titles_order_and_labels_come_from_the_profile():
    view = bv.build(sample(), profile(view={
        "style": "triage", "labels": {"end": "Das war's für heute."},
        "buckets": [{"id": "delegate", "title": "Mache ich"}, {"id": "do", "title": "Tun (du, heute)"},
                    {"id": "plan"}, {"id": "waiting"}, {"id": "drop"}]}))
    out = ANSI.sub("", bv.draw(view))
    assert out.index("Mache ich") < out.index("Tun (du, heute)")
    assert out.rstrip().endswith("Das war's für heute.")


# ---------------------------------------------------------------- the top and the frame

def test_headline_says_what_is_yours_how_long_you_are_free_and_the_next_hard_date():
    view = bv.build(sample(), profile(view={"style": "triage"}))
    h = view["headline"]
    assert "16:30" in h                                           # free until the training
    assert "Post the launch note" in h or "06.10" in h            # the next hard date


def test_since_last_names_what_changed_since_the_previous_run():
    r = sample()
    r["previous_at"] = "2026-10-05T07:18"
    r["sections"][0]["items"][0]["new"] = True
    view = bv.build(r, profile(view={"style": "triage", "since_last": True}))
    assert "07:18" in view["since"] and "1 new" in view["since"]


def test_activity_is_not_a_bucket_and_tabs_are_one_line():
    view = bv.build(sample(), profile(view={"style": "triage"}))
    assert not any(i["title"] == "rebuilt the daemon" for b in view["buckets"] for i in b["items"])
    assert "2" in view["workplace"]


def test_max_items_caps_the_whole_briefing_and_it_ends():
    view = bv.build(sample(), profile(view={"style": "triage", "max_items": 3}))
    shown = sum(len(b["items"]) for b in view["buckets"])
    assert shown == 3 and view["more"] > 0
    out = ANSI.sub("", bv.draw(view))
    assert f"+{view['more']}" in out and "That's all for today." in out


def test_answer_keys_number_rows_across_buckets_and_name_the_letters():
    view = bv.build(sample(), profile(view={"style": "triage", "answer_keys": True}))
    out = ANSI.sub("", bv.draw(view))
    numbers = [int(n) for n in re.findall(r"^\s+(\d+)\s", out, flags=re.M)]
    assert numbers == list(range(1, len(numbers) + 1)) and numbers
    assert "a " in out and "b " in out


def test_long_rows_wrap_at_a_word_and_are_never_cut():
    r = result(sec("inbox", "inbox", [inbox_item(
        "i1", "Unsubscribe the radar mail once the inbox carries the findings (wrapper: --email gone) "
              "and confirm it on the next morning run")]))
    out = ANSI.sub("", bv.draw(bv.build(r, profile(view={"style": "triage", "width": 60}))))
    assert all(len(line) <= 60 for line in out.splitlines())
    assert "--email gone" in out.replace("\n", " ").replace("  ", " ") or "--email" in out


def test_color_only_with_meaning_and_never_when_off():
    view = bv.build(sample(), profile(view={"style": "triage"}))
    assert not ANSI.search(bv.draw(view, color=False))
    assert ANSI.search(bv.draw(view, color=True))
    off = bv.build(sample(), profile(view={"style": "triage", "color": "none"}))
    assert not ANSI.search(bv.draw(off, color=True))


# ---------------------------------------------------------------- the other two styles

def test_brevity_is_the_bottom_line_plus_three_with_why():
    view = bv.build(sample(), profile(view={"style": "brevity"}))
    assert len(view["top"]) == 3
    assert view["top"][0]["title"] == "Post the launch note"
    assert all(t["why"] for t in view["top"])
    out = ANSI.sub("", bv.draw(view))
    assert view["headline"] in out and "+" in out


def test_plan_lays_your_work_into_the_free_gaps_and_ends_the_day():
    view = bv.build(sample(), profile(view={"style": "plan", "plan": {"workday": {"start": "08:00", "end": "17:00"},
                                                                   "default_minutes": 30}}))
    slots = view["plan"]["slots"]
    starts = [s["start"] for s in slots]
    assert starts == sorted(starts) and starts[0] >= "08:00"
    assert any(s["title"] == "Football training" and s["start"] == "16:30" for s in slots)
    mine = [s for s in slots if s.get("kind") == "work"]
    assert mine and all(s["end"] <= "16:30" or s["start"] >= "18:00" for s in mine)
    assert view["plan"]["parallel"]                               # what the bridge does meanwhile
    assert view["plan"]["shutdown"] == "17:00"


# ---------------------------------------------------------------- through the engine

def test_tasks_carry_their_next_step_from_the_frontmatter(tmp_path):
    root = tmp_path / "b"
    d = root / "work" / "tasks" / "alpha"
    d.mkdir(parents=True)
    (root / "work" / "inbox").mkdir(parents=True)
    fm = {"slug": "alpha", "status": "doing", "last_updated": "2026-10-04",
          "next": {"what": "Write the draft", "who": "bridge", "due": "2026-10-06"}}
    (d / "STATUS.md").write_text(f"---\n{yaml.safe_dump(fm)}---\n\n# Alpha\n", encoding="utf-8")
    c = bf.Context(root, now=NOW, cfg={})
    r = bf.collect(root, {"id": "p", "sections": [{"kind": "tasks"}]}, c)
    assert r["sections"][0]["items"][0]["next"]["who"] == "bridge"


def test_a_deferred_item_coming_back_within_the_lookahead_is_shown(tmp_path):
    root = tmp_path / "b"
    (root / "work" / "inbox").mkdir(parents=True)
    box = inbox.Inbox(root / "work" / "inbox", actor="test", clock=lambda: NOW)
    soon = box.add(source="t", kind="decision", summary="Post the launch note", gate="only-you",
                   due="2026-10-06T15:00")
    box.event(soon, "defer", until="2026-10-06")
    late = box.add(source="t", kind="decision", summary="Far away", gate="only-you")
    box.event(late, "defer", until="2026-10-20")
    p = profile(view={"style": "triage", "lookahead_days": 1}, sections=[{"kind": "inbox"}])
    r = bf.collect(root, p, bf.Context(root, now=NOW, cfg={}))
    titles = [i["title"] for i in r["sections"][0]["items"]]
    assert "Post the launch note" in titles and "Far away" not in titles
    row = next(i for b in bv.build(r, p)["buckets"] for i in b["items"] if i["title"] == "Post the launch note")
    assert any("06.10" in w for w in row["why"])
    # Without a view asking for it the inbox section stays what it was: open items only.
    plain = bf.collect(root, {"id": "p", "sections": [{"kind": "inbox"}]}, bf.Context(root, now=NOW, cfg={}))
    assert plain["sections"][0]["items"] == []


def test_cli_render_takes_a_style_once_and_collect_json_carries_the_view(tmp_path, capsys):
    root = tmp_path / "b"
    (root / "work" / "inbox").mkdir(parents=True)
    (root / "work" / "tasks").mkdir(parents=True)
    (root / "bridge-config.yaml").write_text("{}\n", encoding="utf-8")
    path = root / "workflow" / "briefings" / "morning.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump(profile(view={"style": "triage"}, sections=[{"kind": "tasks"}])),
                    encoding="utf-8")
    assert bf.main(["--root", str(root), "render", "--style", "sources", "--no-save"]) == 0
    assert "── tasks" in capsys.readouterr().out.lower()
    assert bf.main(["--root", str(root), "collect", "--json", "--no-save"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["view"]["style"] == "triage"


def test_waiting_counts_from_blocked_since_and_shortens_the_reason_at_a_word():
    t = task_item("austria", "Austria onboarding", changed_at="2026-10-04",
                  blocked_by="test run at the customer, the team waits for the result of the second sandbox round")
    t["blocked_since"] = "2026-09-18"
    view = bv.build(result(sec("tasks", "tasks", [t])), profile(view={"style": "triage"}))
    row = view["buckets"][0]["items"][0]
    assert any("17" in w for w in row["why"])
    reason = next(w for w in row["why"] if w.startswith("test run"))
    assert reason.endswith("…") and reason[:-1].rstrip() in t["blocked_by"]
    assert t["blocked_by"].split()[len(reason[:-1].split()) - 1] == reason[:-1].split()[-1]


def test_the_headline_shortens_a_long_title_at_a_word():
    r = result(sec("inbox", "inbox", [inbox_item("i1", "Post the launch note and the first comment right after "
                                                       "it, drafts cleaned", due="2026-10-06T15:00")]))
    h = bv.build(r, profile(view={"style": "triage"}))["headline"]
    assert "…" in h and "drafts cleaned" not in h



# ---------------------------------------------------------------- findings of the independent review

def test_rows_with_local_ids_from_different_sections_never_merge():
    r = result(sec("backups", "command", [{"id": "1", "title": "A"}, {"id": "2", "title": "B"}]),
               sec("deploys", "command", [{"id": "1", "title": "C"}, {"id": "2", "title": "D"}]))
    titles = sorted(i["title"] for b in bv.build(r, profile(view={"style": "triage"}))["buckets"] for i in b["items"])
    assert titles == ["A", "B", "C", "D"]


def test_a_tracker_row_filed_to_the_inbox_is_one_row():
    r = result(
        sec("inbox", "inbox", [inbox_item("i9", "Board: o/r#5 Fix login (blocked)", urgency="now",
                                          key="briefing:morning:board:o/r#5")]),
        sec("board", "tracker", [{"id": "o/r#5", "title": "Fix login", "state": "blocked", "category": "open"}]))
    rows = [i for b in bv.build(r, profile(view={"style": "triage"}))["buckets"] for i in b["items"]]
    assert len(rows) == 1 and rows[0]["bucket"] == "do"


def test_a_merged_row_takes_the_more_urgent_bucket():
    r = result(sec("board", "tracker", [{"id": "o/r#5", "title": "X", "state": "in_progress", "category": "open"}]),
               sec("gh", "tracker", [{"id": "o/r#5", "title": "X", "state": "review", "category": "qa"}]))
    assert buckets(bv.build(r, profile(view={"style": "triage"}))) == {"do": ["X"]}


def test_a_label_with_an_unknown_placeholder_is_refused_and_never_crashes():
    assert any("anzahl" in p for p in bv.problems({"labels": {"yours_today": "{anzahl} für dich"}}, None))
    assert any("end" in p for p in bv.problems({"labels": {"end": "Fertig :-}"}}, None))
    view = bv.build(sample(), profile(view={"style": "triage", "labels": {"yours_today": "{anzahl} für dich"}}))
    assert "for you today" in view["headline"]           # falls back to the default wording


def test_brevity_still_says_what_failed_and_what_was_muted():
    r = sample()
    r["sections"][3] = sec("gh", "tracker", [], status="error", reason="API rate limit")
    view = bv.build(r, profile(view={"style": "brevity"}, mutes=[{"section": "advise", "when": {"check": "quiet"}}]))
    out = ANSI.sub("", bv.draw(view))
    assert "API rate limit" in out and "1 muted" in out


def test_plan_shows_drop_rows_and_no_false_more():
    view = bv.build(sample(), profile(view={"style": "plan", "max_items": 2}))
    out = ANSI.sub("", bv.draw(view))
    assert "keys untouched" in out
    assert view["more"] == 0 and "+" not in out


def test_plan_fills_an_earlier_gap_with_a_row_that_fits():
    r = result(sec("inbox", "inbox", [inbox_item("a", "A"), inbox_item("b", "B"), inbox_item("c", "C")]),
               sec("calendar", "calendar", [{"id": "e", "title": "Meeting", "start": "2026-10-05T09:00",
                                             "end": "2026-10-05T10:00"}]))
    p = profile(view={"style": "plan", "plan": {"workday": {"start": "08:00", "end": "11:00"}, "default_minutes": 60}})
    r["sections"][0]["items"][0]["estimate_min"] = 90
    view = bv.build(r, p)
    work = {s["title"]: s["start"] for s in view["plan"]["slots"] if s["kind"] == "work"}
    assert work.get("B") == "08:00" or work.get("C") == "08:00"


def test_an_event_running_since_yesterday_makes_you_busy_now():
    r = result(sec("calendar", "calendar", [{"id": "e", "title": "Night shift", "start": "2026-10-04T22:00",
                                             "end": "2026-10-05T10:00"}]),
               sec("inbox", "inbox", [inbox_item("a", "A")]))
    view = bv.build(r, profile(view={"style": "plan", "plan": {"workday": {"start": "08:00", "end": "18:00"}}}))
    assert "Night shift" in view["headline"] and "10:00" in view["headline"]
    first = next(s for s in view["plan"]["slots"] if s["kind"] == "work")
    assert first["start"] >= "10:00"


def test_advice_without_a_row_to_carry_it_is_shown():
    r = result(sec("advise", "advise", [{"id": "advise:due:z", "title": "due 06.10: Z", "check": "due",
                                         "urgency": "today", "task": None}]))
    rows = [i["title"] for b in bv.build(r, profile(view={"style": "triage"}))["buckets"] for i in b["items"]]
    assert rows == ["due 06.10: Z"]


def test_an_advise_section_left_out_does_not_hide_the_quiet_task():
    p = profile(view={"style": "triage"})
    p["sections"][1]["bucket"] = "none"
    assert "Restore test" in buckets(bv.build(sample(), p))["plan"]


def test_plan_uses_the_profiles_waiting_title():
    view = bv.build(sample(), profile(view={"style": "plan", "buckets": [
        {"id": "do"}, {"id": "plan"}, {"id": "delegate"}, {"id": "waiting", "title": "Wartet"}, {"id": "drop"}]}))
    out = ANSI.sub("", bv.draw(view))
    assert "Wartet:" in out and "Waiting on others" not in out


def test_build_survives_values_validation_would_refuse():
    view = bv.build(sample(), profile(view={"style": "triage", "lookahead_days": "2", "width": -5,
                                            "buckets": [{"id": "waiting", "nudge_after_days": "7"}]}))
    assert bv.draw(view)


def test_events_sort_by_time_not_by_spelling():
    r = result(sec("calendar", "calendar", [{"id": "x", "title": "Late", "start": "2026-10-05 14:00"},
                                            {"id": "y", "title": "Early", "start": "2026-10-05T09:00"}]))
    assert "09:00" in bv.build(r, profile(view={"style": "triage"}))["headline"]


def test_validation_matches_the_schema_on_nulls_order_and_notes(tmp_path):
    data = profile(view=None)
    data["view"] = None
    assert any("view" in p for p in bf.profile_problems(data, "morning"))
    assert any("workday" in p for p in bv.problems({"plan": {"workday": {"start": "18:00", "end": "08:00"}}}, None))
    assert any("note" in p for p in bv.problems(None, [{"section": "advise", "when": {"check": "x"}, "note": 3}]))


def test_a_sections_max_still_caps_its_rows_in_a_view():
    rows = [{"id": f"o/r#{n}", "title": f"T{n}", "state": "new", "category": "open"} for n in range(10)]
    s = sec("gh", "tracker", rows[:3], all_rows=None)
    s["all"] = rows
    view = bv.build(result(s), profile(view={"style": "triage"}))
    assert sum(len(b["items"]) for b in view["buckets"]) == 3 and view["more"] == 0


def test_a_full_view_profile_passes_the_json_schema_too():
    import pytest
    jsonschema = pytest.importorskip("jsonschema")
    schema = yaml.safe_load((ROOT / "workflow" / "briefings" / "_schema.yaml").read_text(encoding="utf-8"))
    data = profile(view={"style": "triage", "headline": True, "since_last": True, "lookahead_days": 1,
                         "max_items": 12, "answer_keys": True, "hygiene": "bottom", "color": "auto", "width": 100,
                         "labels": {"end": "Das war's für heute.", "yours_today": "{n} für dich heute"},
                         "buckets": [{"id": "do", "title": "Tun", "options": ["ja"]},
                                     {"id": "waiting", "nudge_after_days": 7}],
                         "plan": {"workday": {"start": "08:00", "end": "17:00"}, "default_minutes": 30}},
                   mutes=[{"section": "advise", "when": {"check": "quiet"}, "note": "never"}])
    data["sections"][1]["bucket"] = "none"
    jsonschema.validate(data, schema)
    assert bf.profile_problems(data, "morning") == []
    bad = dict(data, view={"labels": {"nonsense": "x"}})
    try:
        jsonschema.validate(bad, schema)
        raise AssertionError("schema accepted an unknown label")
    except jsonschema.ValidationError:
        pass
    assert bf.profile_problems(bad, "morning")



# ---------------------------------------------------------------- visual aids

def test_the_day_line_shows_the_workday_with_busy_time_and_now():
    view = bv.build(sample(), profile(view={"style": "triage", "plan": {"workday": {"start": "08:00",
                                                                                    "end": "18:00"}}}))
    line = view["dayline"]
    assert line.startswith("08:00 ") and line.endswith(" 18:00")
    bar = line[6:-6]
    assert "█" in bar and "·" in bar
    # 16:30 of 08:00-18:00 is 85 % of the bar: the training starts there.
    assert abs(bar.index("█") / len(bar) - 0.85) < 0.05
    out = ANSI.sub("", bv.draw(view))
    assert line in out


def test_the_day_line_marks_now_inside_the_day_and_can_be_turned_off():
    r = sample()
    r["collected_at"] = "2026-10-05T13:00"
    view = bv.build(r, profile(view={"style": "triage"}))
    bar = view["dayline"][6:-6]
    assert abs(bar.index("▲") / len(bar) - 0.5) < 0.05
    off = bv.build(sample(), profile(view={"style": "triage", "dayline": False}))
    assert off["dayline"] is None
    assert bv.problems({"dayline": "yes"}, None)


def test_bucket_headers_say_how_many_rows_they_hold():
    view = bv.build(sample(), profile(view={"style": "triage", "max_items": 2}))
    out = ANSI.sub("", bv.draw(view))
    plan = next(b for b in view["buckets"] if b["id"] == "plan") if any(
        b["id"] == "plan" for b in view["buckets"]) else None
    do = view["buckets"][0]
    assert f"── {do['title']} · {do['total']} ──" in out
    assert plan is None or plan["total"] >= len(plan["items"])


def test_issue_ids_become_clickable_links_only_with_colour():
    r = result(sec("gh", "tracker", [{"id": "acme/infra#17", "title": "Time tracking", "state": "review",
                                      "category": "qa", "url": "https://github.com/acme/infra/issues/17"}]))
    view = bv.build(r, profile(view={"style": "triage"}))
    linked = bv.draw(view, color=True)
    assert "\x1b]8;;https://github.com/acme/infra/issues/17\x1b\\acme/infra#17\x1b]8;;\x1b\\" in linked
    assert "\x1b]8" not in bv.draw(view, color=False)


def test_without_a_previous_run_nothing_is_marked_new():
    r = sample()
    r["sections"][0]["items"][0]["new"] = True
    p = profile(view={"style": "triage", "labels": {"new": "FRESH"}})
    assert "FRESH" not in bv.draw(bv.build(r, p))
    r["previous_at"] = "2026-10-05T07:18"
    assert "FRESH" in bv.draw(bv.build(r, p))


# ---------------------------------------------------------------- agenda, clashes, all clear
# A briefing that only says "free until 16:00" hides what is at 16:00, and a clash
# tomorrow evening was invisible because nothing compared the events with each other.
# A source that is green must be able to SAY so: silence reads the same as "never ran".

def _cal(*events):
    return sec("calendar", "calendar", [{"id": f"e{n}", "title": t, "start": s, "end": e}
                                        for n, (t, s, e) in enumerate(events)])


def test_agenda_lists_events_from_now_through_the_lookahead():
    r = result(_cal(("Standup", "2026-10-05T07:00", "2026-10-05T07:15"),
                    ("Review", "2026-10-05T16:00", "2026-10-05T16:45"),
                    ("Weekly", "2026-10-06T18:00", "2026-10-06T18:45"),
                    ("Far away", "2026-10-09T10:00", "2026-10-09T11:00")))
    v = bv.build(r, profile(view={"style": "triage", "lookahead_days": 1}))
    assert [a["title"] for a in v["agenda"]] == ["Review", "Weekly"]
    assert v["agenda"][0]["when"] == "today 16:00-16:45"
    assert v["agenda"][1]["when"] == "tomorrow 18:00-18:45"
    text = bv.draw(v)
    assert "── Calendar ──" in text and "today 16:00-16:45  Review" in text


def test_running_event_stays_in_the_agenda():
    r = result(_cal(("Call", "2026-10-05T07:30", "2026-10-05T08:30")))
    v = bv.build(r, profile(view={"style": "triage"}))
    assert [a["title"] for a in v["agenda"]] == ["Call"]


def test_overlapping_events_become_a_do_row_and_are_marked_in_the_agenda():
    r = result(_cal(("Weekly", "2026-10-06T18:00", "2026-10-06T18:45"),
                    ("Ballet", "2026-10-06T18:05", "2026-10-06T19:05")))
    v = bv.build(r, profile(view={"style": "triage", "lookahead_days": 1}))
    marks = {a["title"]: a.get("clash") for a in v["agenda"]}
    assert marks == {"Weekly": "Ballet", "Ballet": "Weekly"}
    do = next(b for b in v["buckets"] if b["id"] == "do")
    assert any("Weekly" in i["title"] and "Ballet" in i["title"] for i in do["items"])
    assert "overlaps Ballet" in bv.draw(v)


def test_back_to_back_events_do_not_clash():
    r = result(_cal(("A", "2026-10-05T10:00", "2026-10-05T11:00"),
                    ("B", "2026-10-05T11:00", "2026-10-05T12:00")))
    v = bv.build(r, profile(view={"style": "triage"}))
    assert not any(a.get("clash") for a in v["agenda"])


def test_agenda_can_be_switched_off_and_relabelled():
    r = result(_cal(("Review", "2026-10-05T16:00", "2026-10-05T16:45")))
    off = bv.build(r, profile(view={"style": "triage", "agenda": False}))
    assert off["agenda"] == [] and "Calendar" not in bv.draw(off)
    de = bv.build(r, profile(view={"style": "triage", "labels": {"agenda_title": "Termine"}}))
    assert "── Termine ──" in bv.draw(de)


def test_report_ok_section_says_all_clear_when_empty():
    sections = [{"kind": "inbox"}, {"kind": "command", "id": "systems", "title": "Systems", "argv": ["x"],
                                    "report_ok": True}]
    r = result(sec("inbox", "inbox", []), sec("systems", "command", [], title="Systems"))
    v = bv.build(r, profile(view={"style": "triage"}, sections=sections))
    assert v["clear"] == ["Systems: all clear"]
    assert "Systems: all clear" in bv.draw(v)


def test_report_ok_section_with_findings_is_not_all_clear():
    sections = [{"kind": "command", "id": "systems", "title": "Systems", "argv": ["x"], "report_ok": True}]
    item = {"id": "disk", "title": "Disk 99% full", "state": "in_progress", "raw_state": "warn"}
    r = result(sec("systems", "command", [item], title="Systems"))
    v = bv.build(r, profile(view={"style": "triage"}, sections=sections))
    assert v["clear"] == []
    assert any(i["title"] == "Disk 99% full" for b in v["buckets"] for i in b["items"])


def test_report_ok_never_claims_clear_for_a_failed_or_skipped_section():
    sections = [{"kind": "command", "id": "systems", "title": "Systems", "argv": ["x"], "report_ok": True}]
    for status in ("error", "skipped"):
        r = result(sec("systems", "command", [], status=status, title="Systems", reason="boom"))
        assert bv.build(r, profile(view={"style": "triage"}, sections=sections))["clear"] == []


def test_profile_accepts_report_ok_and_agenda():
    p = profile(view={"style": "triage", "agenda": True},
                sections=[{"kind": "command", "id": "s", "argv": ["x"], "report_ok": True}])
    assert bf.profile_problems(p, "morning") == []
    bad = profile(view={"agenda": "yes"}, sections=[{"kind": "command", "id": "s", "argv": ["x"], "report_ok": 1}])
    msgs = bf.profile_problems(bad, "morning")
    assert any("report_ok" in m for m in msgs) and any("agenda" in m for m in msgs)



def test_plan_style_makes_no_clash_work_slot():
    r = result(_cal(("A", "2026-10-05T10:00", "2026-10-05T11:00"), ("B", "2026-10-05T10:30", "2026-10-05T11:30")))
    v = bv.build(r, profile(view={"style": "plan"}))
    assert not any("overlap" in s["title"] for s in v["plan"]["slots"] if s["kind"] == "work")


def test_the_same_event_from_two_calendars_is_no_clash():
    r = result(_cal(("A", "2026-10-05T10:00", "2026-10-05T11:00"), ("A", "2026-10-05T10:00", "2026-10-05T11:00")))
    v = bv.build(r, profile(view={"style": "triage"}))
    assert len(v["agenda"]) == 1 and not v["agenda"][0].get("clash")


def test_three_overlapping_events_are_one_row_naming_all():
    r = result(_cal(("A", "2026-10-05T10:00", "2026-10-05T11:00"), ("B", "2026-10-05T10:30", "2026-10-05T11:30"),
                    ("C", "2026-10-05T10:45", "2026-10-05T12:00")))
    v = bv.build(r, profile(view={"style": "triage"}))
    do = next(b for b in v["buckets"] if b["id"] == "do")["items"]
    clash = [i for i in do if "overlap" in i["title"]]
    assert len(clash) == 1 and all(t in clash[0]["title"] for t in "ABC")
    assert {a["title"]: a["clash"] for a in v["agenda"]}["C"] == "A, B"


def test_an_event_past_midnight_names_its_end_day():
    r = result(_cal(("Night", "2026-10-05T23:30", "2026-10-06T00:30")))
    v = bv.build(r, profile(view={"style": "triage"}))
    assert v["agenda"][0]["when"] == "today 23:30-tomorrow 00:30"


def test_a_filed_row_shows_the_sources_current_title_not_the_filed_one():
    # The inbox keeps the summary from the day it was filed; the source says it better today.
    sections = [{"kind": "inbox"}, {"kind": "command", "id": "systems", "argv": ["x"]}]
    filed = inbox_item("i1", "Disk over 90%", key="briefing:morning:systems:disk")
    fresh = {"id": "disk", "title": "Disk over 90% (measured 99)", "state": "in_progress"}
    r = result(sec("inbox", "inbox", [filed]), sec("systems", "command", [fresh]))
    v = bv.build(r, profile(view={"style": "triage"}, sections=sections))
    titles = [i["title"] for b in v["buckets"] for i in b["items"]]
    assert titles == ["Disk over 90% (measured 99)"]


# ---------------------------------------------------------------- overview: file
# An agent copies the view into the chat by hand, and a long overview block is where a
# copy went wrong (a line invented, five dropped). `overview: file` keeps Boards and
# Activity out of the printed text; the engine writes them to a file and names it.

def _with_overview(view):
    sections = [{"kind": "commits", "id": "commits"}]
    rows = [{"id": "repo-a", "branch": "main", "spark": "▁▃█", "total": 4, "counts": [1, 1, 2]}]
    r = result(sec("commits", "commits", rows))
    return bv.build(r, profile(view=view, sections=sections))


def test_overview_inline_by_default():
    text = bv.draw(_with_overview({"style": "triage"}))
    assert "repo-a" in text


def test_overview_file_leaves_it_out_of_the_text_and_draws_it_separately():
    v = _with_overview({"style": "triage", "overview": "file"})
    text = bv.draw(v)
    assert "repo-a" not in text
    assert "repo-a" in bv.draw_overview(v)


def test_overview_value_is_validated():
    assert any("overview" in m for m in bv.problems({"overview": "elsewhere"}, None))


# ---------------------------------------------------------------- style: report
# A person asked for the briefing to read like a report: levels, tables, and what to
# act on at the bottom, instead of a wall of text. Markdown, since chats render it.

def _report(view=None, sections=None, *secs):
    v = {"style": "report", **(view or {})}
    return bv.build(result(*secs), profile(view=v, sections=sections))


def test_report_has_status_details_and_actions_in_that_order():
    sections = [{"kind": "inbox"}, {"kind": "command", "id": "systems", "title": "Systems", "argv": ["x"]},
                {"kind": "command", "id": "pipeline", "title": "Pipeline", "argv": ["x"]},
                {"kind": "calendar"}]
    text = bv.draw(_report(None, sections,
                           sec("inbox", "inbox", [inbox_item("i1", "Answer the client", due="2026-10-05")]),
                           sec("systems", "command", [], title="Systems"),
                           sec("pipeline", "command", [], status="error", title="Pipeline", reason="timeout"),
                           _cal(("Review", "2026-10-05T16:00", "2026-10-05T16:45"))))
    assert text.index("### Status") < text.index("### Calendar") < text.index("### To act on")
    assert "| Systems | ✓ all clear |" in text
    assert "| Pipeline | ✗ failed: timeout |" in text
    assert "| Inbox | 1 open |" in text
    assert "| today 16:00-16:45 | Review |" in text
    assert "| 1 | Answer the client |" in text


def test_report_escapes_pipes_in_cells():
    sections = [{"kind": "inbox"}]
    text = bv.draw(_report(None, sections, sec("inbox", "inbox", [inbox_item("i1", "A | B", urgency="today")])))
    assert "A \\| B" in text


def test_report_draws_boards_and_activity_as_tables_unless_in_a_file():
    sections = [{"kind": "commits", "id": "commits"}]
    rows = [{"id": "repo-a", "branch": "main", "spark": "▁▃█", "total": 4, "counts": [1, 1, 2]}]
    inline = bv.draw(_report(None, sections, sec("commits", "commits", rows)))
    assert "| repo-a | main | ▁▃█ | 4 |" in inline
    filed = bv.draw(_report({"overview": "file"}, sections, sec("commits", "commits", rows)))
    assert "repo-a" not in filed


def test_report_is_a_valid_style_and_its_labels_relabel():
    assert bf.profile_problems(profile(view={"style": "report"}), "morning") == []
    v = _report({"labels": {"status_title": "Lage", "act_title": "Angehen"}}, [{"kind": "inbox"}],
                sec("inbox", "inbox", []))
    text = bv.draw(v)
    assert "### Lage" in text and "Angehen" not in text or "### Angehen" in text


def test_report_why_has_no_internal_ids_and_links_issue_refs():
    sections = [{"kind": "command", "id": "up", "argv": ["x"]},
                {"kind": "tracker", "id": "gh", "provider": "github"}]
    up = {"id": "upstream:bks", "title": "Overlay bks: sync due", "state": "ready", "raw_state": "drift"}
    pr = {"id": "acme/app#7", "title": "Fix it", "state": "ready", "raw_state": "your PR, open 8 days",
          "url": "https://github.com/acme/app/pull/7"}
    text = bv.draw(_report(None, sections, sec("up", "command", [up]), sec("gh", "tracker", [pr])))
    assert "upstream:bks" not in text
    assert "| Overlay bks: sync due | drift |" in text
    assert "[acme/app#7](https://github.com/acme/app/pull/7) · your PR, open 8 days" in text
