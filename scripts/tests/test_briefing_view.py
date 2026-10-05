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

