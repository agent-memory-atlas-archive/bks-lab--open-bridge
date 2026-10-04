# SPDX-License-Identifier: MIT
"""Azure DevOps Boards through `az boards query` (WIQL, the az CLI's own login).

query keys (all optional):
  wiql          a full WIQL statement; default: work items assigned to @Me that
                are not Closed, Removed or Done
  organization  organization URL, e.g. https://dev.azure.com/example-org
  project       project name
  limit         cap on returned items, default 50

`organization` and `project` are also used to build item URLs.
States follow trackers/ado.md: Ready for Testing / In Testing are review (category qa).
"""
from __future__ import annotations

from . import load_json, source_error

DEFAULT_WIQL = (
    "SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType], [System.AssignedTo], "
    "[System.ChangedDate], [System.Tags], [Microsoft.VSTS.Common.Priority] FROM WorkItems "
    "WHERE [System.AssignedTo] = @Me AND [System.State] NOT IN ('Closed', 'Removed', 'Done') "
    "ORDER BY [System.ChangedDate] DESC"
)
STATES = {
    "new": "new", "proposed": "new",
    "active": "ready", "committed": "ready", "approved": "ready",
    "in progress": "in_progress",
    "ready for testing": "review", "in testing": "review",
    "done": "done", "approved by qa": "done", "closed": "done",
    "removed": "removed", "blocked": "blocked",
}
TYPES = {"bug": "bug", "user story": "story", "product backlog item": "story", "requirement": "story",
         "task": "task", "feature": "feature", "epic": "epic"}


def _assignee(value):
    if isinstance(value, dict):
        return value.get("displayName") or value.get("uniqueName")
    return value or None


def normalize(raw: dict, *, organization: str | None, project: str | None, mine: bool) -> dict:
    f = raw.get("fields") or {}
    raw_state = f.get("System.State")
    state = STATES.get(str(raw_state).lower(), "new")
    tags = [t.strip() for t in str(f.get("System.Tags") or "").split(";") if t.strip()]
    prio = f.get("Microsoft.VSTS.Common.Priority")
    item_project = f.get("System.TeamProject") or project
    url = None
    if organization and item_project:
        url = f"{organization.rstrip('/')}/{item_project}/_workitems/edit/{raw.get('id')}"
    return {
        "id": f"#{raw.get('id')}",
        "title": f.get("System.Title"),
        "state": state,
        "raw_state": raw_state,
        "type": TYPES.get(str(f.get("System.WorkItemType")).lower(), "issue"),
        "assignee": _assignee(f.get("System.AssignedTo")),
        "assigned_to_me": mine,
        "url": url,
        "changed_at": f.get("System.ChangedDate"),
        "project": item_project,
        "labels": tags,
        "priority": f"P{prio}" if prio is not None else None,
        "category": "done" if state in ("done", "removed") else "qa" if state == "review" else "open",
    }


def collect(section: dict, ctx) -> list:
    query = dict(section.get("query") or {})
    custom = query.get("wiql")
    argv = ["az", "boards", "query", "--wiql", str(custom or DEFAULT_WIQL), "--output", "json"]
    if query.get("organization"):
        argv += ["--org", str(query["organization"])]
    if query.get("project"):
        argv += ["--project", str(query["project"])]
    data = load_json(ctx.run(argv, timeout=ctx.timeout), "az boards query")
    if not isinstance(data, list):
        raise source_error("az boards query: unexpected answer")
    limit = int(query.get("limit", 50))
    # The default WIQL selects @Me; a custom one says nothing about ownership.
    return [normalize(raw, organization=query.get("organization"), project=query.get("project"),
                      mine=not custom) for raw in data[:limit]]
