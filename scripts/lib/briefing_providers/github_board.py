# SPDX-License-Identifier: MIT
"""GitHub Projects (V2) boards, through the same code as scripts/tracker-sync.py.

Boards come from `github_projects:` in the ecosystem files, state maps from
workflow/projects/<slug>.yaml: the registry tracker-sync already reads, so a
board is configured once. Done and removed cards are left out unless asked.

query keys (all optional):
  boards          [slug, ...]  only these boards (default: every registered board)
  assigned_to_me  true: only cards assigned to you (bridge-config
                  integrations.github.assignee_me, else your gh login)
  states          [normalized state, ...]  only these
  include_done    true: keep done/removed cards
  limit           per board, default 200
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from . import load_json, source_error


def _tracker_sync(root: Path):
    name = "tracker_sync"
    if name in sys.modules:
        return sys.modules[name]
    here = Path(__file__).resolve().parents[2] / "tracker-sync.py"
    spec = importlib.util.spec_from_file_location(name, here)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise source_error("scripts/tracker-sync.py is missing")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def collect(section: dict, ctx) -> list:
    query = dict(section.get("query") or {})
    ts = _tracker_sync(ctx.root)
    boards = ts.resolve_boards(ctx.root, ts.load_registries(ctx.root))
    if query.get("boards"):
        boards = [b for b in boards if b["slug"] in query["boards"]]
    if not boards:
        raise source_error("no boards: add `github_projects:` to an ecosystem file")
    me = ((ctx.cfg.get("integrations") or {}).get("github") or {}).get("assignee_me")
    if not me and query.get("assigned_to_me"):
        try:
            me = load_json(ctx.run(["gh", "api", "user"], timeout=ctx.timeout), "gh api user").get("login")
        except Exception:  # noqa: BLE001
            raise source_error("assigned_to_me needs integrations.github.assignee_me or a gh login") from None
    states = set(query.get("states") or [])
    keep_done = query.get("include_done") or bool(states & {"done", "removed"})
    out, summary = [], []
    order = ("new", "ready", "in_progress", "review", "blocked")
    for board in boards:
        argv = ["gh", "project", "item-list", str(board["number"]), "--owner", str(board["org"]),
                "--format", "json", "--limit", str(query.get("limit", 200))]
        payload = load_json(ctx.run(argv, timeout=ctx.timeout), f"board {board['slug']}")
        counts = dict.fromkeys(order, 0)
        for raw in payload.get("items", []) if isinstance(payload, dict) else []:
            item = ts.normalize_gh_item(raw, board, me)
            if not item:
                continue
            if item["state"] in counts:      # every open card, before the person's filters
                counts[item["state"]] += 1
            if query.get("assigned_to_me") and not item["assigned_to_me"]:
                continue
            if states and item["state"] not in states:
                continue
            if not keep_done and item["state"] in ("done", "removed"):
                continue
            out.append({**{k: v for k, v in item.items() if k not in ("number", "repo")},
                        "id": f"{item.get('repo') or board['org']}#{item['number']}",
                        "type": str(item.get("type") or "issue").lower(),
                        "project": board["name"], "tracker": "github-board", "priority": None,
                        "_category_from_state": True})
        summary.append({"name": board["name"], "number": board["number"], "org": board["org"],
                        "slug": board["slug"], "counts": counts, "open": sum(counts.values())})
    if section.get("summary"):
        # `summary: true`: the whole board as counts per state, beside the person's own rows.
        section["_summary"] = summary
    return out
