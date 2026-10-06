# SPDX-License-Identifier: MIT
"""Contract for skills/briefing/scripts/upstream_items.py: inbound drift as briefing rows.

A `command` section with `covers: [upstream]` runs it. One row per upstream that needs a
person: CORE commits not yet merged, an overlay with a newer state, a conflict, a sync
older than its interval, a subscription never materialized. Nothing to do prints [].
A check that cannot run is a row, never silence.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("upstream_items", ROOT / "skills" / "briefing" / "scripts" / "upstream_items.py")
ui = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ui)

CORE = {"name": "core", "repo": "acme/core", "branch": "main", "role": "oss-core"}
OVERLAY = {"name": "org", "repo": "acme/org-config", "branch": "main", "role": "org-overlay",
           "materialize": {"url": "git@github.com:acme/org-config.git", "ref": "main"}}


class Git:
    def __init__(self, behind="0", remotes="core-up\thttps://github.com/acme/core.git (fetch)\n", fail_fetch=False):
        self.behind, self.remotes, self.fail_fetch, self.calls = behind, remotes, fail_fetch, []

    def __call__(self, argv, **_):
        self.calls.append(argv)
        if argv[:2] == ["git", "remote"]:
            return self.remotes
        if argv[:2] == ["git", "fetch"]:
            if self.fail_fetch:
                raise RuntimeError("could not resolve host")
            return ""
        if argv[:2] == ["git", "rev-list"]:
            return self.behind + "\n"
        if argv[:2] == ["git", "log"]:
            return "feat: something new\n"
        raise AssertionError(argv)


def test_core_in_sync_is_no_row():
    assert ui.core_items([CORE], run=Git("0")) == []


def test_core_behind_is_one_plan_row_with_the_newest_subject():
    (row,) = ui.core_items([CORE], run=Git("5"))
    assert row["id"] == "upstream:core" and row["state"] == "ready"
    assert "5" in row["title"] and "feat: something new" in row["title"]


def test_core_remote_is_found_by_url_not_by_name():
    git = Git("2", remotes="origin\tgit@github.com:me/private.git (fetch)\nob\tgit@github.com:acme/core.git (fetch)\n")
    ui.core_items([CORE], run=git)
    assert ["git", "rev-list", "--count", "HEAD..ob/main"] in git.calls


def test_core_unreachable_is_a_row_not_silence():
    (row,) = ui.core_items([CORE], run=Git(fail_fetch=True))
    assert row["state"] == "blocked" and "could not" in row["title"]


def test_core_without_a_matching_remote_says_so():
    (row,) = ui.core_items([CORE], run=Git(remotes="origin\tgit@github.com:me/private.git (fetch)\n"))
    assert "no git remote" in row["title"]


def test_overlay_rows():
    data = [{"name": "org", "subscribed": True, "materialized": True, "cache_ahead": True, "days_since_sync": 9,
             "interval_days": 7, "stale": True, "files": {"conflict": 1, "locally-modified": 8}},
            {"name": "personal", "subscribed": True, "materialized": False},
            {"name": "calm", "subscribed": True, "materialized": True, "cache_ahead": False, "stale": False,
             "files": {"conflict": 0}}]
    rows = {r["id"]: r for r in ui.overlay_items(data)}
    assert set(rows) == {"upstream:org", "upstream:personal"}
    org = rows["upstream:org"]
    assert org["state"] == "blocked" and "conflict" in org["title"] and "sync" in org["title"]
    assert "never materialized" in rows["upstream:personal"]["title"]


def test_main_prints_a_json_list(tmp_path, capsys, monkeypatch):
    (tmp_path / "bridge-config.yaml").write_text("upstreams: []\n", encoding="utf-8")
    assert ui.main(["--root", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_an_authored_overlay_and_a_materialized_one_are_not_core():
    authored = {"name": "mine", "repo": "acme/mine", "role": "org-overlay"}
    git = Git("3")
    assert ui.core_items([authored, OVERLAY], run=git) == [] and git.calls == []


def test_two_cores_is_a_config_error_row():
    (row,) = ui.core_items([CORE, CORE | {"name": "core2"}], run=Git("0"))
    assert row["state"] == "blocked" and "oss-core" in row["title"]
