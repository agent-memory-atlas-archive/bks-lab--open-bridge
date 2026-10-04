# SPDX-License-Identifier: MIT
"""Linear through its GraphQL API.

query keys (all optional):
  filter  a raw Linear IssueFilter object (replaces the default filter)
  team    team key, e.g. "ENG": adds a team filter
  limit   default 50

Default: the viewer's assigned issues that are not completed or canceled.

account file (section.account_ref, identity/accounts/<id>.yaml):
  token_ref   reference URI of the API key (required); sent as `Authorization: <key>`
              without "Bearer", as Linear expects for personal API keys
  base_url    GraphQL endpoint, default https://api.linear.app/graphql

The token is passed to the HTTP call only; it appears in no result and no error.
"""
from __future__ import annotations

from . import source_error

ENDPOINT = "https://api.linear.app/graphql"
DEFAULT_FILTER = {"state": {"type": {"nin": ["completed", "canceled"]}}}
NODE = ("identifier title url updatedAt priorityLabel state { name type } "
        "labels { nodes { name } } assignee { name } project { name } team { key }")
STATES = {"backlog": "new", "triage": "new", "unstarted": "ready", "started": "in_progress",
          "completed": "done", "canceled": "removed"}


def normalize(raw: dict, *, mine: bool) -> dict:
    st = raw.get("state") or {}
    state = STATES.get(st.get("type"), "new")
    if "review" in str(st.get("name") or "").lower() and state not in ("done", "removed"):
        state = "review"
    prio = raw.get("priorityLabel")
    return {
        "id": raw.get("identifier"),
        "title": raw.get("title"),
        "state": state,
        "raw_state": st.get("name"),
        "type": "issue",
        "assignee": (raw.get("assignee") or {}).get("name"),
        "assigned_to_me": mine,
        "url": raw.get("url"),
        "changed_at": raw.get("updatedAt"),
        "project": (raw.get("project") or {}).get("name") or (raw.get("team") or {}).get("key"),
        "labels": [n.get("name") for n in (raw.get("labels") or {}).get("nodes") or []],
        "priority": None if prio in (None, "No priority") else prio,
        "category": "done" if state in ("done", "removed") else "qa" if state == "review" else "open",
    }


def _gql(query: dict, limit: int):
    custom = query.get("filter")
    flt = dict(custom) if custom else dict(DEFAULT_FILTER)
    if query.get("team"):
        flt["team"] = {"key": {"eq": str(query["team"])}}
    if custom:
        text = f"query($filter: IssueFilter) {{ issues(first: {limit}, filter: $filter) {{ nodes {{ {NODE} }} }} }}"
    else:
        text = (f"query($filter: IssueFilter) {{ viewer {{ assignedIssues(first: {limit}, filter: $filter) "
                f"{{ nodes {{ {NODE} }} }} }} }}")
    return text, {"filter": flt}


def collect(section: dict, ctx) -> list:
    account = ctx.account(section)
    if not account.get("token_ref"):
        raise source_error("linear account file is missing 'token_ref'")
    token = ctx.secret(str(account["token_ref"]))
    query = dict(section.get("query") or {})
    text, variables = _gql(query, int(query.get("limit", 50)))
    data = ctx.http("POST", str(account.get("base_url") or ENDPOINT),
                    {"Authorization": token}, {"query": text, "variables": variables})
    if not isinstance(data, dict):
        raise source_error("linear: unexpected answer")
    if data.get("errors"):
        first = data["errors"][0] if isinstance(data["errors"], list) and data["errors"] else {}
        msg = first.get("message") if isinstance(first, dict) else None
        raise source_error(f"linear: GraphQL error: {msg or 'unknown'}")
    body = data.get("data") or {}
    nodes = ((body.get("viewer") or {}).get("assignedIssues") or body.get("issues") or {}).get("nodes") or []
    mine = not query.get("filter")
    return [normalize(n, mine=mine) for n in nodes]
