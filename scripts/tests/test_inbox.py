# SPDX-License-Identifier: MIT
"""Contract for scripts/inbox.py: one place where everything that needs a person waits.

The properties that matter, in the order they bit before this file existed:

* an item knows when it is done (`closes_when`) and `check` closes it from the
  live source, so a solved thing never comes back in a briefing;
* two machines write the inbox through git and never conflict: an item is
  created once and every change is a NEW file, nothing is ever rewritten;
* state is derived from the events, never stored;
* a repeated finding (a watcher firing every five minutes) is one item, not fifty;
* `run` executes only what a person released, and never an `only-you` action.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "inbox.py"

spec = importlib.util.spec_from_file_location("inbox", SCRIPT)
assert spec is not None and spec.loader is not None
inbox = importlib.util.module_from_spec(spec)
sys.modules["inbox"] = inbox      # dataclasses resolve the module by name while loading
sys.dont_write_bytecode = True
spec.loader.exec_module(inbox)

NOW = dt.datetime(2026, 10, 4, 18, 0)


@pytest.fixture()
def box(tmp_path):
    return inbox.Inbox(tmp_path / "work" / "inbox", actor="laptop", clock=lambda: NOW)


def add(box, **kw):
    base = dict(source="homebox/issue-radar", kind="decision", summary="PR #70 is green and waits")
    base.update(kw)
    return box.add(**base)


# ---------------------------------------------------------------- creation

def test_add_creates_one_immutable_item_file(box):
    item_id = add(box)
    item_dir = box.root / item_id
    assert (item_dir / "item.yaml").is_file()
    assert box.get(item_id).state == "open"
    assert item_id.startswith("20261004-1800-")


def test_add_rejects_unknown_kind_gate_and_urgency(box):
    with pytest.raises(ValueError):
        add(box, kind="todo")
    with pytest.raises(ValueError):
        add(box, gate="maybe")
    with pytest.raises(ValueError):
        add(box, urgency="asap")


def test_same_key_while_open_is_one_item(box):
    first = add(box, key="backup-stale")
    second = add(box, key="backup-stale", summary="still stale")
    assert first == second
    assert len(box.items()) == 1
    # the repeat is recorded, so the item shows it is still firing
    assert [e.verb for e in box.get(first).events] == ["seen"]


def test_same_key_after_close_opens_a_new_item(box):
    first = add(box, key="backup-stale")
    box.close(first, note="fixed")
    second = add(box, key="backup-stale")
    assert second != first


def test_ids_never_collide_within_one_minute(box):
    ids = {add(box, summary=f"thing {i}") for i in range(5)}
    assert len(ids) == 5


# ---------------------------------------------------------------- events, never rewrites

def test_every_change_is_a_new_file_and_item_yaml_never_changes(box):
    item_id = add(box)
    before = (box.root / item_id / "item.yaml").read_bytes()
    box.note(item_id, "looked at it")
    box.approve(item_id)
    box.close(item_id)
    assert (box.root / item_id / "item.yaml").read_bytes() == before
    assert len(list((box.root / item_id / "events").glob("*.yaml"))) == 3


def test_two_machines_writing_at_once_produce_disjoint_files(tmp_path):
    root = tmp_path / "work" / "inbox"
    laptop = inbox.Inbox(root, actor="laptop", clock=lambda: NOW)
    homebox = inbox.Inbox(root, actor="homebox", clock=lambda: NOW)
    item_id = laptop.add(source="laptop", kind="decision", summary="x")
    laptop.note(item_id, "a")
    homebox.note(item_id, "b")
    names = sorted(p.name for p in (root / item_id / "events").iterdir())
    assert len(names) == 2 and len(set(names)) == 2
    assert any("laptop" in n for n in names) and any("homebox" in n for n in names)


# ---------------------------------------------------------------- derived state

@pytest.mark.parametrize(
    "steps, state",
    [
        ([], "open"),
        ([("approve", {})], "approved"),
        ([("approve", {"when": {"after": "2099-01-01T00:00"}})], "waiting"),
        ([("defer", {"until": "2099-01-01"})], "deferred"),
        ([("defer", {"until": "2000-01-01"})], "open"),
        ([("reject", {})], "dropped"),
        ([("close", {})], "done"),
        ([("approve", {}), ("executed", {})], "done"),
        ([("approve", {}), ("failed", {})], "open"),
    ],
)
def test_state_is_derived_from_events(box, steps, state):
    item_id = add(box)
    for verb, kw in steps:
        box.event(item_id, verb, **kw)
    assert box.get(item_id).state == state


def test_open_list_hides_done_and_dropped_and_deferred(box):
    a = add(box, summary="a")
    b = add(box, summary="b")
    c = add(box, summary="c")
    add(box, summary="d")
    box.close(a)
    box.reject(b)
    box.event(c, "defer", until="2099-01-01")
    assert [i.summary for i in box.open_items()] == ["d"]


# ---------------------------------------------------------------- probes and check

def test_check_closes_an_item_whose_closes_when_holds(box, tmp_path):
    marker = tmp_path / "token-ok"
    item_id = add(box, closes_when={"path_exists": str(marker)})
    assert box.check() == []
    marker.write_text("ok")
    closed = box.check()
    assert closed == [item_id]
    item = box.get(item_id)
    assert item.state == "done"
    assert item.events[-1].by == "check"


def test_probe_command_and_after(box):
    assert inbox.probe({"command": ["true"]}) is True
    assert inbox.probe({"command": ["false"]}) is False
    assert inbox.probe({"after": "2000-01-01T00:00"}, now=NOW) is True
    assert inbox.probe({"after": "2099-01-01T00:00"}, now=NOW) is False


def test_unknown_or_broken_probe_is_unknown_never_true(box):
    assert inbox.probe({"no_such_probe": 1}) is None
    assert inbox.probe({"command": ["/definitely/not/here"]}) is None
    item_id = add(box, closes_when={"no_such_probe": 1})
    assert box.check() == []
    assert box.get(item_id).state == "open"


def test_gh_probe_reads_state_through_a_runner(box):
    calls = []

    def fake_gh(args):
        calls.append(args)
        return json.dumps({"state": "MERGED", "statusCheckRollup": []})

    assert inbox.probe({"gh_pr": "org/repo#70", "state": "merged"}, gh=fake_gh) is True
    assert calls and calls[0][:3] == ["pr", "view", "70"]


def test_gh_probe_green_needs_every_check_successful():
    def runner(rollup):
        return lambda args: json.dumps({"state": "OPEN", "statusCheckRollup": rollup})

    green = [{"conclusion": "SUCCESS"}, {"conclusion": "SKIPPED"}]
    red = [{"conclusion": "SUCCESS"}, {"conclusion": "FAILURE"}]
    pending = [{"conclusion": "", "status": "IN_PROGRESS"}]
    assert inbox.probe({"gh_pr": "o/r#1", "state": "green"}, gh=runner(green)) is True
    assert inbox.probe({"gh_pr": "o/r#1", "state": "green"}, gh=runner(red)) is False
    assert inbox.probe({"gh_pr": "o/r#1", "state": "green"}, gh=runner(pending)) is False
    assert inbox.probe({"gh_pr": "o/r#1", "state": "green"}, gh=runner([])) is False


# ---------------------------------------------------------------- run: only what a person released

def test_run_executes_an_approved_your_yes_action(box, tmp_path):
    out = tmp_path / "ran"
    item_id = add(box, gate="your-yes", action={"argv": ["touch", str(out)]})
    assert box.run() == []          # not approved yet
    box.approve(item_id)
    assert box.run() == [item_id]
    assert out.exists()
    assert box.get(item_id).state == "done"


def test_run_waits_for_the_condition_of_a_conditional_yes(box, tmp_path):
    out = tmp_path / "ran"
    cond = tmp_path / "green"
    item_id = add(box, gate="your-yes", action={"argv": ["touch", str(out)]})
    box.approve(item_id, when={"path_exists": str(cond)})
    assert box.run() == []
    assert box.get(item_id).state == "waiting"
    cond.write_text("")
    assert box.run() == [item_id]
    assert out.exists()


def test_run_never_executes_only_you_even_when_approved(box, tmp_path):
    out = tmp_path / "sent"
    item_id = add(box, gate="only-you", action={"argv": ["touch", str(out)]})
    with pytest.raises(PermissionError):
        box.approve(item_id, when={"after": "2000-01-01T00:00"})
    box.approve(item_id)            # a plain yes is recorded ...
    assert box.run() == []          # ... but run refuses to act on it
    assert not out.exists()


def test_run_executes_free_actions_without_approval(box, tmp_path):
    out = tmp_path / "regen"
    item_id = add(box, gate="free", action={"argv": ["touch", str(out)]})
    assert box.run() == [item_id]
    assert out.exists()


def test_failed_action_records_exit_code_and_stays_open(box):
    item_id = add(box, gate="free", action={"argv": ["false"]})
    assert box.run() == []
    item = box.get(item_id)
    assert item.state == "open"
    assert item.events[-1].verb == "failed"
    assert item.events[-1].data.get("exit") == 1


def test_action_must_be_an_argv_list_never_a_shell_string(box):
    with pytest.raises(ValueError):
        add(box, action={"argv": "rm -rf /"})
    with pytest.raises(ValueError):
        add(box, action={"shell": "echo hi"})


# ---------------------------------------------------------------- ordering and rendering

def test_first_thing_is_the_most_urgent_decision(box):
    add(box, summary="later finding", kind="finding", urgency="later")
    add(box, summary="today decision", kind="decision", urgency="today")
    add(box, summary="now finding", kind="finding", urgency="now")
    add(box, summary="today finding", kind="finding", urgency="today")
    order = [i.summary for i in box.open_items()]
    assert order == ["now finding", "today decision", "today finding", "later finding"]


def test_render_writes_a_generated_view(box):
    add(box, summary="PR #70 waits", task="a2a")
    text = box.render()
    assert "GENERATED" in text and "PR #70 waits" in text and "a2a" in text


def test_validate_reports_a_hand_edited_broken_item(box):
    item_id = add(box)
    (box.root / item_id / "item.yaml").write_text("kind: nonsense\n")
    problems = box.validate()
    assert problems and item_id in problems[0]


# ---------------------------------------------------------------- CLI

def run_cli(tmp_path, *args):
    env_root = tmp_path / "repo"
    (env_root / "work" / "inbox").mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(env_root), "--by", "test", *args],
        capture_output=True, text=True,
    )


def test_cli_add_list_close_roundtrip(tmp_path):
    r = run_cli(tmp_path, "add", "--from", "cli", "--kind", "finding", "--summary", "disk 91 %")
    assert r.returncode == 0, r.stderr
    item_id = r.stdout.strip()
    r = run_cli(tmp_path, "list", "--json")
    assert json.loads(r.stdout)[0]["id"] == item_id
    r = run_cli(tmp_path, "close", item_id[:15], "--note", "cleaned")
    assert r.returncode == 0, r.stderr
    r = run_cli(tmp_path, "list", "--json")
    assert json.loads(r.stdout) == []


def test_cli_unknown_command_exits_2_without_writing(tmp_path):
    r = run_cli(tmp_path, "frobnicate")
    assert r.returncode == 2
    assert not any((tmp_path / "repo" / "work" / "inbox").iterdir())


def test_due_is_validated_and_orders_within_the_same_urgency(box):
    with pytest.raises(ValueError):
        add(box, due="next tuesday")
    add(box, summary="later due", due="2026-10-09")
    add(box, summary="sooner due", due="2026-10-06T15:00")
    assert [i.summary for i in box.open_items()] == ["sooner due", "later due"]


def test_approve_can_release_an_edited_text(box):
    item_id = add(box, kind="draft")
    box.approve(item_id, text="shorter answer")
    assert box.get(item_id).approved_text == "shorter answer"
