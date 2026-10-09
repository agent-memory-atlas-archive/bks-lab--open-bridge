# SPDX-License-Identifier: MIT
"""Contract for scripts/task.py: set a task's priority or add a note without touching any other byte."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "task.py"

STATUS = (
    "---\n"
    "slug: alpha   # keep me\n"
    "status: doing\n"
    "title: \"Quoted: title\"\n"
    "last_updated: 2026-09-01\n"
    "---\n\n# Alpha\n\nbody status: doing\n"
)


def run(root, *args):
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), *args],
                          capture_output=True, text=True)


@pytest.fixture()
def repo(tmp_path):
    for kind, slug in (("tasks", "alpha"), ("streams", "river")):
        d = tmp_path / "work" / kind / slug
        d.mkdir(parents=True)
        (d / "STATUS.md").write_text(STATUS.replace("alpha", slug), encoding="utf-8")
    return tmp_path


def test_adds_priority_after_status_and_preserves_everything_else(repo):
    r = run(repo, "priority", "alpha", "P1")
    assert r.returncode == 0, r.stderr
    text = (repo / "work/tasks/alpha/STATUS.md").read_text(encoding="utf-8")
    import datetime
    expected = STATUS.replace("status: doing\n", "status: doing\npriority: P1\n", 1) \
        .replace("last_updated: 2026-09-01", f"last_updated: {datetime.date.today().isoformat()}")
    assert text == expected


def test_rewrites_an_existing_priority_line_only(repo):
    p = repo / "work/tasks/alpha/STATUS.md"
    p.write_text(STATUS.replace("status: doing\n", "status: doing\npriority: P3  # old\n", 1), encoding="utf-8")
    assert run(repo, "priority", "alpha", "P0").returncode == 0
    text = p.read_text(encoding="utf-8")
    assert "priority: P0\n" in text and "P3" not in text and text.count("priority:") == 1


def test_streams_work_too_and_the_board_is_regenerated(repo):
    r = run(repo, "priority", "river", "P2")
    assert r.returncode == 0, r.stderr
    assert "priority: P2" in (repo / "work/streams/river/STATUS.md").read_text(encoding="utf-8")
    assert (repo / "work" / "board.md").is_file()
    assert "alpha" in (repo / "work" / "board.md").read_text(encoding="utf-8")


def test_refuses_unknown_slug_and_bad_value_without_writing(repo):
    before = (repo / "work/tasks/alpha/STATUS.md").read_text(encoding="utf-8")
    r = run(repo, "priority", "ghost", "P1")
    assert r.returncode == 1 and "ghost" in r.stderr
    r = run(repo, "priority", "alpha", "P9")
    assert r.returncode in (1, 2)
    assert (repo / "work/tasks/alpha/STATUS.md").read_text(encoding="utf-8") == before
    assert not (repo / "work" / "board.md").exists()


# ---------------------------------------------------------------- note

def test_note_appends_a_dated_line_under_a_new_notes_section(repo):
    import datetime
    assert run(repo, "note", "alpha", "Customer wants it by Friday").returncode == 0
    text = (repo / "work/tasks/alpha/STATUS.md").read_text(encoding="utf-8")
    today = datetime.date.today().isoformat()
    assert text.endswith(f"\n## Notes\n\n- {today}: Customer wants it by Friday\n")
    assert f"last_updated: {today}" in text and "body status: doing" in text


def test_note_goes_into_an_existing_notes_section_before_the_next_heading(repo):
    p = repo / "work/tasks/alpha/STATUS.md"
    p.write_text(STATUS + "\n## Notes\n\n- 2026-09-01: old\n\n## Later\n\nx\n", encoding="utf-8")
    assert run(repo, "note", "alpha", "new").returncode == 0
    text = p.read_text(encoding="utf-8")
    assert text.index("- 2026-09-01: old") < text.index(": new") < text.index("## Later")
    assert text.count("## Notes") == 1


def test_only_the_english_notes_heading_is_the_notes_section(repo):
    # CORE parses one heading, "## Notes"; any other heading is left alone and
    # a new "## Notes" section is opened at the end.
    p = repo / "work/tasks/alpha/STATUS.md"
    p.write_text(STATUS + "\n## Remarks\n\n- 2026-09-01: old\n", encoding="utf-8")
    assert run(repo, "note", "alpha", "new").returncode == 0
    text = p.read_text(encoding="utf-8")
    assert text.count("## Notes") == 1
    assert text.index("## Remarks") < text.index("## Notes") < text.index(": new")


def _from_template(repo):
    """A STATUS.md made from the shipped template, comment line above the fence included."""
    tpl = (ROOT / "work" / "templates" / "STATUS.md").read_text(encoding="utf-8")
    p = repo / "work/tasks/alpha/STATUS.md"
    p.write_text(tpl.replace("<slug>", "alpha"), encoding="utf-8")
    return tpl.replace("<slug>", "alpha"), p


def test_priority_works_on_a_status_made_from_the_template(repo):
    before, p = _from_template(repo)
    assert before.startswith("# yaml-language-server:")
    r = run(repo, "priority", "alpha", "P0")
    assert r.returncode == 0, r.stderr
    text = p.read_text(encoding="utf-8")
    assert text.splitlines()[0] == before.splitlines()[0]
    assert "\npriority: P0\n" in text and text.count("\npriority:") == 1


def test_note_works_on_a_status_made_from_the_template(repo):
    before, p = _from_template(repo)
    r = run(repo, "note", "alpha", "first note")
    assert r.returncode == 0, r.stderr
    text = p.read_text(encoding="utf-8")
    assert text.startswith(before.splitlines(keepends=True)[0])
    assert ": first note" in text and "last_updated: YYYY-MM-DD" not in text


def test_note_refuses_empty_text_and_unknown_slug(repo):
    before = (repo / "work/tasks/alpha/STATUS.md").read_text(encoding="utf-8")
    assert run(repo, "note", "alpha", "   ").returncode == 1
    assert run(repo, "note", "ghost", "x").returncode == 1
    assert (repo / "work/tasks/alpha/STATUS.md").read_text(encoding="utf-8") == before


def test_note_at_the_end_of_a_file_without_final_newline_gets_its_own_line(repo):
    p = repo / "work/tasks/alpha/STATUS.md"
    p.write_text(STATUS + "\n## Notes\n\n- 2026-09-01: old", encoding="utf-8")
    assert run(repo, "note", "alpha", "new").returncode == 0
    lines = p.read_text(encoding="utf-8").splitlines()
    assert lines[-2] == "- 2026-09-01: old" and lines[-1].endswith(": new")


def test_note_keeps_crlf_line_endings(repo):
    p = repo / "work/tasks/alpha/STATUS.md"
    p.write_bytes(STATUS.replace("\n", "\r\n").encode("utf-8"))
    assert run(repo, "note", "alpha", "new").returncode == 0
    data = p.read_bytes()
    assert b"\n" not in data.replace(b"\r\n", b"")
