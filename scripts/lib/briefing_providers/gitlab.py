# SPDX-License-Identifier: MIT
"""GitLab issues through the `glab` CLI (its own login, no token in the profile).

query keys:
  repos     ["group/project", ...]  required: one `glab issue list` per repo
  assignee  "@me" (default) or a username
  state     opened (default) | closed
  labels    [label, ...]  all must be present
  limit     per repo, default 50

State: closed is done; labels in-progress/doing give in_progress, in-review/review
give review, blocked gives blocked; any other open issue is ready.
"""
from __future__ import annotations

from . import load_json, source_error

BLOCKED = {"blocked"}
PROGRESS = {"in-progress", "doing", "in progress"}
REVIEW = {"in-review", "review", "in review"}
QA = {"needs-qa", "needs-testing", "qa-queue"}
TYPES = [("bug", {"bug", "defect", "incident"}), ("feature", {"feature", "enhancement"}),
         ("epic", {"epic"}), ("story", {"story", "user-story"}), ("task", {"task", "chore"})]


def _state(raw: dict, labels: list) -> str:
    if raw.get("state") == "closed":
        return "done"
    low = {lab.lower() for lab in labels}
    if low & BLOCKED:
        return "blocked"
    if low & REVIEW:
        return "review"
    if low & PROGRESS:
        return "in_progress"
    return "ready"


def _priority(labels: list):
    for lab in labels:
        low = lab.lower()
        if low.startswith("priority:") or (len(low) == 2 and low[0] == "p" and low[1].isdigit()):
            return lab
    return None


def normalize(raw: dict, *, repo: str, assignee_query: str) -> dict:
    labels = [lab.get("name") if isinstance(lab, dict) else lab for lab in raw.get("labels") or []]
    assignees = [a.get("username") if isinstance(a, dict) else a for a in raw.get("assignees") or []]
    low = {lab.lower() for lab in labels}
    state = _state(raw, labels)
    kind = next((name for name, names in TYPES if low & names), "issue")
    category = "done" if state == "done" else "qa" if (state == "review" or low & QA) else "open"
    mine = assignee_query == "@me" or assignee_query in assignees
    return {
        "id": f"{repo}#{raw.get('iid')}",
        "title": raw.get("title"),
        "state": state,
        "raw_state": raw.get("state"),
        "type": kind,
        "assignee": assignees[0] if assignees else None,
        "assigned_to_me": bool(mine and (assignees or assignee_query == "@me")),
        "url": raw.get("web_url"),
        "changed_at": raw.get("updated_at"),
        "project": repo,
        "labels": labels,
        "priority": _priority(labels),
        "category": category,
    }


def collect(section: dict, ctx) -> list:
    query = dict(section.get("query") or {})
    repos = query.get("repos") or []
    if not repos:
        raise source_error("gitlab: query.repos is required (a list of group/project paths)")
    assignee = str(query.get("assignee", "@me"))
    out = []
    for repo in repos:
        argv = ["glab", "issue", "list", "--repo", str(repo), "--assignee", assignee,
                "--output", "json", "--per-page", str(query.get("limit", 50))]
        if str(query.get("state", "opened")) == "closed":
            argv.append("--closed")
        for label in query.get("labels") or []:
            argv += ["--label", str(label)]
        data = load_json(ctx.run(argv, timeout=ctx.timeout), f"glab issue list {repo}")
        if not isinstance(data, list):
            raise source_error(f"glab issue list {repo}: unexpected answer")
        out += [normalize(raw, repo=str(repo), assignee_query=assignee) for raw in data]
    return out
