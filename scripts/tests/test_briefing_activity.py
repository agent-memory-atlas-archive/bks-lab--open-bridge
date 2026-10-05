# SPDX-License-Identifier: MIT
"""Contract for the two overview parts of a briefing: commit activity and board summaries.

`kind: commits` counts commits per repository per day (the repositories registered in
the ecosystem files, or a list) and draws them as a sparkline, the "what moved this
week" a briefing showed before profiles. `summary: true` on a github-board section
adds one line per board with its cards per state, so a person sees the whole board
while their own cards still land in the view's buckets.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True


def _load(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


bf = _load("briefing", ROOT / "scripts" / "briefing.py")
bv = _load("briefing_view", ROOT / "scripts" / "lib" / "briefing_view.py")
NOW = dt.datetime(2026, 10, 5, 9, 0)
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def bridge(tmp_path: Path, ecosystem: dict | None = None) -> Path:
    root = tmp_path / "bridge"
    (root / "work" / "inbox").mkdir(parents=True)
    (root / "work" / "tasks").mkdir(parents=True)
    (root / ".git").mkdir()
    if ecosystem is not None:
        (root / "ecosystem.yaml").write_text(yaml.safe_dump(ecosystem), encoding="utf-8")
    return root


def repo(path: Path) -> Path:
    (path / ".git").mkdir(parents=True)
    return path


class Git:
    """git log answers per repository path, as dates; records the calls."""

    def __init__(self, dates: dict, branch="main", email="me@example.com"):
        self.dates, self.branch, self.email, self.calls = dates, branch, email, []

    def __call__(self, argv, timeout=30, cwd=None):
        self.calls.append(list(argv))
        path = argv[2]
        if argv[3] == "log":
            return "\n".join(self.dates.get(path, [])) + "\n"
        if argv[3:5] == ["branch", "--show-current"]:
            return self.branch + "\n"
        if argv[3:5] == ["config", "user.email"]:
            return self.email + "\n"
        raise bf.SourceError(f"unexpected {argv}")


def run_commits(root, section, git):
    c = bf.Context(root, now=NOW, run=git, cfg={})
    return bf.collect(root, {"id": "p", "sections": [section]}, c)["sections"][0]


# ---------------------------------------------------------------- commits

def test_commits_count_per_day_over_the_registered_repositories(tmp_path):
    a = repo(tmp_path / "code" / "alpha")
    repo(tmp_path / "code" / "quiet")
    root = bridge(tmp_path, {"local_root": str(tmp_path / "code"),
                             "base": {"alpha": {"github": "o/alpha"}, "quiet": {"github": "o/quiet"},
                                      "missing": {"github": "o/missing"}}})
    git = Git({str(a): ["2026-10-05", "2026-10-05", "2026-10-03", "2026-09-29"]})
    sec = run_commits(root, {"kind": "commits", "days": 7}, git)
    assert sec["status"] == "ok"
    [item] = sec["items"]                              # quiet and missing leave no row
    assert item["id"] == "alpha" and item["total"] == 4 and item["branch"] == "main"
    assert item["counts"] == [1, 0, 0, 0, 1, 0, 2]     # 29.09 .. 05.10, oldest first
    assert len(item["spark"]) == 7 and item["spark"][-1] == "█" and item["spark"][1] == "▁"


def test_commits_take_an_explicit_list_and_the_authors_filter(tmp_path):
    b = repo(tmp_path / "beta")
    root = bridge(tmp_path)
    git = Git({str(b): ["2026-10-04"]})
    sec = run_commits(root, {"kind": "commits", "repos": [str(b)], "author": "me", "all_branches": True}, git)
    assert sec["items"][0]["id"] == "beta"
    log = next(c for c in git.calls if c[3] == "log")
    assert "--author=me@example.com" in log and "--all" in log


def test_a_repository_that_fails_is_skipped_not_the_section(tmp_path):
    good, bad = repo(tmp_path / "good"), repo(tmp_path / "bad")
    root = bridge(tmp_path)

    class Flaky(Git):
        def __call__(self, argv, timeout=30, cwd=None):
            if argv[2] == str(bad):
                raise bf.SourceError("not a git repository")
            return super().__call__(argv, timeout, cwd)

    sec = run_commits(root, {"kind": "commits", "repos": [str(bad), str(good)]},
                      Flaky({str(good): ["2026-10-05"]}))
    assert sec["status"] == "ok" and [i["id"] for i in sec["items"]] == ["good"]


def test_commits_are_validated(tmp_path):
    ok = {"schema_version": 1, "scope": "user", "id": "p",
          "sections": [{"kind": "commits", "days": 7, "repos": ["a"], "author": ["me", "x@y"],
                        "all_branches": True}]}
    assert bf.profile_problems(ok, "p") == []
    bad = {**ok, "sections": [{"kind": "commits", "repos": "a", "author": 3, "all_branches": "yes"}]}
    text = " | ".join(bf.profile_problems(bad, "p"))
    assert "repos" in text and "author" in text and "all_branches" in text


def test_sources_render_draws_the_sparkline():
    result = {"profile": "p", "title": "P", "sections": [
        {"id": "commits", "kind": "commits", "title": "Commits", "status": "ok", "total": 1, "items": [
            {"id": "alpha", "title": "alpha", "branch": "main", "spark": "▁▃█", "total": 4}]}]}
    assert "alpha" in bf.render(result) and "▁▃█" in bf.render(result) and "4" in bf.render(result)


# ---------------------------------------------------------------- views

def sec(sid, kind, items, **extra):
    return {"id": sid, "kind": kind, "title": sid, "status": "ok", "items": items, "all": items,
            "total": len(items), **extra}


def view_of(*sections, style="triage", labels=None):
    result = {"profile": "p", "title": "P", "collected_at": NOW.isoformat(timespec="minutes"),
              "sections": list(sections)}
    v = {"style": style}
    if labels:
        v["labels"] = labels
    return bv.build(result, {"id": "p", "sections": [{"kind": s["kind"], "id": s["id"]} for s in sections],
                             "view": v})


def test_triage_shows_activity_as_one_block_not_as_buckets():
    v = view_of(sec("commits", "commits", [{"id": "alpha", "title": "alpha", "branch": "main", "spark": "▁▃█",
                                            "total": 4, "counts": [0, 1, 3]}], days=3))
    assert v["buckets"] == []
    out = ANSI.sub("", bv.draw(v))
    assert "Activity (3 days)" in out and re.search(r"alpha\s+main\s+▁▃█\s+4 commits", out)


def test_brevity_leaves_activity_out():
    v = view_of(sec("commits", "commits", [{"id": "alpha", "title": "alpha", "branch": "main", "spark": "▁▃█",
                                            "total": 4}]), style="brevity")
    assert "alpha" not in bv.draw(v)


# ---------------------------------------------------------------- board summary

def board_payload():
    def card(n, status, assignee=None):
        return {"id": f"PVT_{n}", "status": status, "title": f"Card {n}", "assignees": [assignee] if assignee else [],
                "content": {"number": n, "repository": "o/infra", "type": "Issue", "title": f"Card {n}"}}
    return {"items": [card(1, "Todo", "me"), card(2, "Todo"), card(3, "In Progress"), card(4, "In Review"),
                      card(5, "Done")]}


def test_board_summary_counts_every_card_while_rows_stay_mine(tmp_path, monkeypatch):
    import json
    root = bridge(tmp_path, {"github_projects": [{"number": 26, "name": "Infra", "org": "o", "slug": "infra"}]})
    git_calls = []

    def run(argv, timeout=30, cwd=None):
        git_calls.append(argv)
        if argv[:3] == ["gh", "project", "item-list"]:
            return json.dumps(board_payload())
        raise bf.SourceError(f"unexpected {argv}")

    c = bf.Context(root, now=NOW, run=run, cfg={"integrations": {"github": {"assignee_me": "me"}}})
    section = {"kind": "tracker", "id": "boards", "provider": "github-board", "summary": True,
               "query": {"assigned_to_me": True}}
    s = bf.collect(root, {"id": "p", "sections": [section]}, c)["sections"][0]
    assert s["status"] == "ok", s.get("reason")
    assert [i["title"] for i in s["items"]] == ["Card 1"]
    [board] = s["summary"]
    assert board["name"] == "Infra" and board["open"] == 4
    assert sum(board["counts"].values()) == 4                       # done is not open work
    out = bf.render(bf._public(s and {"profile": "p", "title": "P", "sections": [s]}))
    assert "Infra" in out


def test_board_summary_is_one_line_per_board_in_the_view():
    s = sec("boards", "tracker", [], summary=[{"name": "Infra", "number": 26, "open": 4,
                                               "counts": {"new": 2, "in_progress": 1, "review": 1}}])
    out = ANSI.sub("", bv.draw(view_of(s, labels={"st_in_progress": "in Arbeit"})))
    assert re.search(r"Infra.*2 new.*1 in Arbeit.*1 review", out)
    assert bf.profile_problems({"schema_version": 1, "scope": "user", "id": "p", "sections": [
        {"kind": "tracker", "provider": "github-board", "summary": "yes"}]}, "p")


def test_a_board_without_open_cards_takes_no_line():
    s = sec("boards", "tracker", [], summary=[{"name": "Quiet", "number": 1, "open": 0, "counts": {}},
                                              {"name": "Busy", "number": 2, "open": 1, "counts": {"review": 1}}])
    out = ANSI.sub("", bv.draw(view_of(s)))
    assert "Busy" in out and "Quiet" not in out
