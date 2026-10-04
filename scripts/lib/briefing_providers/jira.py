# SPDX-License-Identifier: MIT
"""Jira (Cloud or Data Center) through its REST API, never a CLI.

query keys (all optional):
  jql     default: assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC
  limit   default 50
  fields  list of Jira fields to request (default: summary, status, issuetype,
          assignee, updated, labels, priority)

account file (section.account_ref, identity/accounts/<id>.yaml):
  base_url     https://example.atlassian.net   (required)
  token_ref    reference URI of the API token, e.g. keychain://example/jira-token (required)
  email        account email, required for Cloud basic auth
  auth         "bearer" for a Data Center personal access token (default: basic)
  api_version  3 (default, POST /rest/api/3/search/jql) or 2 (GET /rest/api/2/search)
  account_id   your accountId, used to flag assigned_to_me for custom JQL

The token is passed to the HTTP call only; it appears in no result and no error.
"""
from __future__ import annotations

import base64
from urllib.parse import quote

from . import source_error

DEFAULT_JQL = "assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC"
DEFAULT_FIELDS = ["summary", "status", "issuetype", "assignee", "updated", "labels", "priority"]
CATEGORY = {"new": "new", "indeterminate": "in_progress", "done": "done"}
TYPES = {"bug": "bug", "story": "story", "task": "task", "sub-task": "task", "subtask": "task",
         "epic": "epic", "feature": "feature", "improvement": "feature", "new feature": "feature"}


def _state(status: dict) -> tuple:
    name = str(status.get("name") or "")
    low = name.lower()
    cat = (status.get("statusCategory") or {}).get("key")
    state = CATEGORY.get(cat, "new")
    if "block" in low:
        return "blocked", "open"
    if "review" in low:
        return "review", "qa"
    if "test" in low or "qa" in low.split() or low.startswith("qa"):
        return "review", "qa"
    return state, "done" if state == "done" else "open"


def normalize(raw: dict, *, base_url: str, mine: bool, account_id: str | None = None) -> dict:
    f = raw.get("fields") or {}
    status = f.get("status") or {}
    state, category = _state(status)
    who = f.get("assignee") or {}
    if account_id and who.get("accountId"):
        mine = mine or who["accountId"] == account_id
    key = raw.get("key")
    prio = f.get("priority")
    return {
        "id": key,
        "title": f.get("summary"),
        "state": state,
        "raw_state": status.get("name"),
        "type": TYPES.get(str((f.get("issuetype") or {}).get("name") or "").lower(), "issue"),
        "assignee": who.get("displayName") or None,
        "assigned_to_me": bool(mine),
        "url": f"{base_url.rstrip('/')}/browse/{key}",
        "changed_at": f.get("updated"),
        "project": str(key).rsplit("-", 1)[0] if key else None,
        "labels": list(f.get("labels") or []),
        "priority": prio.get("name") if isinstance(prio, dict) else prio,
        "category": category,
    }


def _headers(account: dict, token: str) -> dict:
    if str(account.get("auth", "basic")).lower() == "bearer":
        return {"Authorization": f"Bearer {token}"}
    email = account.get("email")
    if not email:
        raise source_error("jira account file is missing 'email' (needed for Cloud basic auth)")
    raw = base64.b64encode(f"{email}:{token}".encode()).decode()
    return {"Authorization": f"Basic {raw}"}


def collect(section: dict, ctx) -> list:
    account = ctx.account(section)
    for key in ("base_url", "token_ref"):
        if not account.get(key):
            raise source_error(f"jira account file is missing {key!r}")
    base = str(account["base_url"]).rstrip("/")
    token = ctx.secret(str(account["token_ref"]))
    headers = _headers(account, token)
    query = dict(section.get("query") or {})
    jql = query.get("jql") or DEFAULT_JQL
    limit = int(query.get("limit", 50))
    fields = list(query.get("fields") or DEFAULT_FIELDS)
    if str(account.get("api_version", 3)) == "2":
        url = f"{base}/rest/api/2/search?jql={quote(jql)}&maxResults={limit}&fields={quote(','.join(fields))}"
        data = ctx.http("GET", url, headers, None)
    else:
        data = ctx.http("POST", f"{base}/rest/api/3/search/jql", headers,
                        {"jql": jql, "maxResults": limit, "fields": fields})
    if not isinstance(data, dict) or not isinstance(data.get("issues"), list):
        raise source_error("jira: unexpected search answer")
    mine = not query.get("jql")
    return [normalize(raw, base_url=base, mine=mine, account_id=account.get("account_id"))
            for raw in data["issues"]]
