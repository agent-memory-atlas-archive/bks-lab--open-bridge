#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""upstream-resolve.py — decide which upstream-merge conflicts a machine may resolve.

The daily upstream-autoupdate job used to stop at the first predicted conflict and
then stop again every morning after, because nothing ever resolved it: one instance
sat 84 commits behind before anybody looked. Most of those conflicts were not
decisions at all. A fix was promoted, merged upstream under a new hash, and then
upstream built on it (a review edit, a follow-up commit). The local file is an OLDER
upstream version, and upstream's current one is simply newer.

That is the one case this script resolves, and it is decided by CONTENT, never by
path or by commit message:

  take theirs   the local version of the file is byte-identical to a version
                upstream itself had between the merge base and now, and upstream
                did not revert any commit since. Upstream has seen our change and
                moved on from it; nothing local is lost.

  unresolved    everything else, each with the reason:
                · the local version never reached upstream (an unpromoted CORE
                  edit — promote it, or drop it)
                · upstream had it and then REVERTED it. Taking theirs here would
                  silently withdraw a change that may be running locally — on the
                  instance this was written on, a live launchd job.
                · the file was deleted locally, or the conflict is not a plain
                  content one (rename, mode, submodule)

Every path not provably "take theirs" is unresolved: the script fails closed.

Usage:
  upstream-resolve.py --theirs upstream/main [--ours HEAD]   # JSON on stdout
Exit: 0 = plan printed (check "unresolved") · 2 = git could not answer.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

ENV = {**os.environ, "LC_ALL": "C"}


class GitError(RuntimeError):
    pass


def git(*args: str, ok: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess:
    p = subprocess.run(["git", *args], capture_output=True, env=ENV)
    if p.returncode not in ok:
        raise GitError(f"git {' '.join(args)} → {p.returncode}: {p.stderr.decode(errors='replace').strip()}")
    return p


def blob(rev: str, path: str) -> str | None:
    p = git("rev-parse", "-q", "--verify", f"{rev}:{path}", ok=(0, 1, 128))
    return p.stdout.decode().strip() if p.returncode == 0 else None


def conflicts(ours: str, theirs: str) -> tuple[bool, dict[str, set[int]]]:
    """(clean, {path: {stages}}) from merge-tree's exit code and -z stage list."""
    p = git("merge-tree", "--write-tree", "-z", ours, theirs, ok=(0, 1))
    if p.returncode == 0:
        return True, {}
    out: dict[str, set[int]] = {}
    # <tree>NUL then "<mode> <oid> <stage>\t<path>" NUL ... then an empty field.
    for field in p.stdout.decode(errors="surrogateescape").split("\0")[1:]:
        if not field:
            break
        meta, _, path = field.partition("\t")
        parts = meta.split()
        if len(parts) != 3 or not path:
            raise GitError(f"unparseable merge-tree entry: {field!r}")
        out.setdefault(path, set()).add(int(parts[2]))
    if not out:
        raise GitError("merge-tree reported conflicts but listed no paths")
    return False, out


def is_revert(commit: str) -> bool:
    msg = git("log", "-1", "--format=%s%n%b", commit).stdout.decode(errors="replace")
    return msg.startswith('Revert "') or "This reverts commit" in msg


def short(c: str) -> str:
    return c[:7]


def local_commits(base: str, ours: str, path: str) -> list[str]:
    # base..ours alone lists every user-only commit ever made to the path, back to
    # the first sync; the ones a human has to look at are those since the base.
    # An old unpromoted edit has none since the base, so fall back to the newest few.
    since = git("log", "-1", "--format=%cI", base).stdout.decode().strip()
    rng = (f"{base}..{ours}", "--", path)
    recent = git("log", "--no-merges", f"--since={since}", "--format=%h %s", *rng).stdout
    out = recent or git("log", "--no-merges", "-3", "--format=%h %s", *rng).stdout
    return out.decode(errors="replace").splitlines()


def classify(path: str, stages: set[int], base: str, ours: str, theirs: str) -> dict:
    entry = {"path": path}
    ours_blob = blob(ours, path)
    if ours_blob is None:
        return {**entry, "reason": "deleted or renamed locally"}
    if 2 not in stages:
        return {**entry, "reason": "not a plain content conflict"}
    history = git("rev-list", "--reverse", f"{base}..{theirs}", "--", path).stdout.decode().split()
    hit = None
    for i, c in enumerate(history):
        if blob(c, path) == ours_blob:
            hit = i
    if hit is None:
        return {**entry, "reason": "local change never reached upstream",
                "local_commits": local_commits(base, ours, path)}
    later = history[hit + 1:]
    reverts = [c for c in later if is_revert(c)]
    if reverts:
        return {**entry, "reason": f"upstream had it at {short(history[hit])}, then reverted it in "
                + ", ".join(short(c) for c in reverts),
                "local_commits": local_commits(base, ours, path)}
    return {**entry, "seen_upstream_at": short(history[hit]),
            "theirs_deleted": blob(theirs, path) is None}


def plan(ours: str, theirs: str) -> dict:
    ours = git("rev-parse", "--verify", ours).stdout.decode().strip()
    theirs = git("rev-parse", "--verify", theirs).stdout.decode().strip()
    base = git("merge-base", ours, theirs).stdout.decode().strip()
    clean, paths = conflicts(ours, theirs)
    take, unresolved = [], []
    for path in sorted(paths):
        r = classify(path, paths[path], base, ours, theirs)
        (unresolved if "reason" in r else take).append(r)
    return {"clean": clean, "base": short(base), "take_theirs": take, "unresolved": unresolved}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--theirs", required=True)
    ap.add_argument("--ours", default="HEAD")
    a = ap.parse_args()
    try:
        print(json.dumps(plan(a.ours, a.theirs), indent=2))
    except GitError as e:
        print(f"upstream-resolve: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
