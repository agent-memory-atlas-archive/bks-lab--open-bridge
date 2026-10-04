# SPDX-License-Identifier: MIT
"""GitHub issues and pull requests through `gh search` (the gh CLI's own login).

query keys (all optional):
  assignee          "@me" (default) or a login
  owners            [org or user, ...]  limits the search to these owners
  repos             ["owner/repo", ...]
  kinds             [issues, prs]  (default both)
  state             open (default) | closed
  labels            [label, ...]  all must be present
  review_requested  true: also PRs where a review is requested from you
  limit             per search, default 50

`@me` resolves on each person's machine to their own login, which is what lets
one shared (org) profile give every colleague their own issues.
"""
from __future__ import annotations

from . import load_json

FIELDS = "number,title,url,state,updatedAt,labels,assignees,repository"
BLOCKED_LABELS = {"blocked", "status:blocked", "on hold", "waiting"}


def _flags(query: dict) -> list:
    argv = []
    for owner in query.get("owners") or []:
        argv += ["--owner", str(owner)]
    for repo in query.get("repos") or []:
        argv += ["--repo", str(repo)]
    for label in query.get("labels") or []:
        argv += ["--label", str(label)]
    argv += ["--state", str(query.get("state", "open")), "--limit", str(query.get("limit", 50))]
    return argv


def _me(ctx) -> str | None:
    try:
        return load_json(ctx.run(["gh", "api", "user"], timeout=ctx.timeout), "gh api user").get("login")
    except Exception:  # noqa: BLE001 - without a login, assigned_to_me falls back to the query
        return None


def _state(raw: dict, is_pr: bool, labels: list) -> str:
    if raw.get("state") == "closed" or raw.get("state") == "merged":
        return "done"
    if any(lab.lower() in BLOCKED_LABELS for lab in labels):
        return "blocked"
    if is_pr:
        return "in_progress" if raw.get("isDraft") else "review"
    return "ready"


def normalize(raw: dict, *, is_pr: bool, me: str | None, assignee_query: str | None, review: bool = False) -> dict:
    labels = [lab.get("name") if isinstance(lab, dict) else lab for lab in raw.get("labels") or []]
    assignees = [a.get("login") if isinstance(a, dict) else a for a in raw.get("assignees") or []]
    repo = (raw.get("repository") or {}).get("nameWithOwner") if isinstance(raw.get("repository"), dict) \
        else raw.get("repository")
    mine = review or (me in assignees if me else assignee_query == "@me")
    state = _state(raw, is_pr, labels)
    item = {
        "id": f"{repo}#{raw.get('number')}",
        "title": raw.get("title"),
        "state": state,
        "raw_state": "draft" if raw.get("isDraft") else raw.get("state"),
        "type": "pr" if is_pr else "issue",
        "assignee": assignees[0] if assignees else None,
        "assigned_to_me": bool(mine),
        "url": raw.get("url"),
        "changed_at": raw.get("updatedAt"),
        "project": repo,
        "labels": labels,
        "priority": None,
        "category": "qa" if review else ("done" if state == "done" else "open"),
    }
    return item


def collect(section: dict, ctx) -> list:
    query = dict(section.get("query") or {})
    assignee = query.get("assignee", "@me")
    kinds = query.get("kinds") or ["issues", "prs"]
    me = _me(ctx) if assignee == "@me" or query.get("review_requested") else assignee
    base = _flags(query)
    out: dict = {}
    for kind in kinds:
        argv = ["gh", "search", kind, "--assignee", str(assignee), *base, "--json",
                FIELDS + (",isDraft" if kind == "prs" else "")]
        for raw in load_json(ctx.run(argv, timeout=ctx.timeout), f"gh search {kind}"):
            item = normalize(raw, is_pr=kind == "prs", me=me, assignee_query=assignee)
            out[item["id"]] = item
    if query.get("review_requested"):
        argv = ["gh", "search", "prs", "--review-requested", "@me", *base, "--json", FIELDS + ",isDraft"]
        for raw in load_json(ctx.run(argv, timeout=ctx.timeout), "gh search prs --review-requested"):
            item = normalize(raw, is_pr=True, me=me, assignee_query=assignee, review=True)
            out.setdefault(item["id"], item)
    return list(out.values())
