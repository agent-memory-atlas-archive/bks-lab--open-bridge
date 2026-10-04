---
name: cmux
description: 'Optional, only for cmux users: tabs, splits, parallel agents, workplace driver, restoring lost workspaces from layout snapshots. Trigger: "new tab", "split pane", "parallel agent", "workspaces lost", "restore cmux layout". Trap: "tab" = surface, not workspace.'
metadata:
  scope: core
---

# cmux

Manage [cmux](https://github.com/manaflow-ai/cmux) workspaces, tabs and the agent
sessions inside them from one terminal, and bring them back when cmux loses them.

**Optional.** Everything here needs the `cmux` CLI. Without it the skill does
nothing: the scripts exit with a clear message and the workplace driver answers an
error, which `scripts/workplace.py` reads as "tab view unknown", never as "no tabs
open". Nothing else in the Bridge depends on cmux.

## Decision tree

```
User wants to...
├── open a tab / split / workspace, spawn or watch an agent, sidebar, wait-for
│       → vocabulary table below, then references/local.md
├── "workspaces lost", "which sessions were running", cmux crashed or relaunched
│       → references/sessions.md: cmux_layout.py list → show → restore
├── one tab per task, "status of all tabs", "send <tab>: ..."
│       → scripts/workplace.py (CORE plan, docs/workplace.md) with this skill as driver
├── which session runs where, or what an agent is doing right now
│       → references/sessions.md: cmux sessions --json, vault search, agent journal
├── restart the agent in every tab (after an update)
│       → references/sessions.md § Restart
└── watch or answer agents on another machine, from a laptop or phone
        → references/remote.md
```

## The workplace driver

`scripts/workplace.py` plans the day as workspaces with one agent tab per task
and knows no terminal. This skill ships the cmux side of it. Wire it in
`bridge-config.yaml`:

```yaml
workplace:
  driver: {command: ["python3", "${root}/skills/cmux/scripts/cmux_driver.py"]}
```

Then `python3 scripts/workplace.py open --yes [--here "$CMUX_SURFACE_ID"]` opens
the plan in cmux, and `status`, `send`, `adopt` steer the tabs. The driver never
closes a tab or a workspace, reuses a tab that is already open, and joins live
socket refs (`surface:91`) with the session file (UUIDs) by workspace and tab
title without its status glyph, because the two ids never match.

## First move after a loss

`python3 skills/cmux/scripts/cmux_layout.py list`. A drop in the workspace or
agent count between two lines is the loss; `restore <n>` shows what is missing,
`--apply` (from a cmux tab) rebuilds it. Snapshots exist only if something takes
them: declare a workload (`workflow/workloads/`) that runs
`cmux_layout.py snapshot` every few minutes. Snapshots keep each workspace's
color and description.

## Rule: agent sessions start in the Bridge root

A tab that starts an agent opens in the Bridge repo root, the only place where it
loads `AGENTS.md`, the registries and the skills. `spawn-workspace.sh` and
`cmux_layout.py` default to it. Raw `cmux new-surface` / `new-split` inherit the
pane's directory, so prefix the command with `cd <bridge root> && ...`. Pass
another `--cwd` only when the work deliberately lives in a foreign repo (its own
agent instructions then apply).

## Rule: resolve the target workspace first, then open

`cmux new-surface`, `cmux browser open` and `new-split` without `--workspace` fall
back to `$CMUX_WORKSPACE_ID`, which can be stale after a restore or a moved
session, or to the selected workspace. The MCP browser (`browser_open`) has no
target parameter at all. Go through the wrapper:

```bash
skills/cmux/scripts/cmux-open.sh where                       # target, caller, selected workspace
skills/cmux/scripts/cmux-open.sh tab --name helper -- "cd <bridge root> && claude ..."
skills/cmux/scripts/cmux-open.sh browser https://example.com
skills/cmux/scripts/cmux-open.sh tab --workspace Platform    # a name or workspace:N
```

The wrapper takes the **caller's** workspace (live from `cmux identify`, not the
selected one), passes it explicitly, verifies with `list-pane-surfaces` that the
surface landed there and moves it otherwise. Use `--workspace` only when the user
names another destination. For browser work via MCP, call `cmux-open.sh browser
<url>` first and continue with the returned surface.

## User vocabulary → cmux primitives (read this first)

| User says | cmux primitive | Command |
|---|---|---|
| **"tab"**, "new tab", "tab next to it" | **Surface** (tab in the current pane) | `cmux new-surface` |
| **"workspace"**, "new window", "own window" | **Workspace** (top-level, sidebar entry) | `cmux new-workspace` or `spawn-workspace.sh` |
| **"split"**, "pane", "side by side" | **Pane** (split inside a workspace) | `cmux new-split <direction>` or `cmux new-pane` |

**Default:** "tab" almost always means a surface in the current workspace, not a
new workspace. A workspace where a tab was asked for is an extra window the user
has to manage. If the request is ambiguous, ask once: tab in this workspace, or
its own workspace?

Keep related work in ONE workspace and organize it with tabs and splits; open a
new workspace only when the user says so or the work is unrelated to the current
workspace's topic.

Starting an agent in a new tab (the common case):

```bash
NEW_SURFACE=$(skills/cmux/scripts/cmux-open.sh tab | grep -oE 'surface:[0-9]+')
cat > "$TMPDIR/agent-prompt.txt" <<'PROMPT'
... the full prompt ...
PROMPT
cmux send --surface "$NEW_SURFACE" "cd <bridge root> && claude \"\$(cat $TMPDIR/agent-prompt.txt)\""
cmux send-key --surface "$NEW_SURFACE" enter
cmux rename-tab --surface "$NEW_SURFACE" "agent-name"
```

## Where the rest lives

| File | Contents |
|---|---|
| [`references/local.md`](references/local.md) | quick reference, spawning agents, splits, sidebar, notifications, wait-for, observe protocol, tab management, settings, browser limits, environment, socket API, traps |
| [`references/sessions.md`](references/sessions.md) | layout snapshots and restore, loss alarm, what cmux and Claude Code already do natively, restart across all tabs |
| [`references/remote.md`](references/remote.md) | socket modes, steering agents on another machine |
| `scripts/cmux_driver.py` | the workplace driver (JSON protocol: tabs, sessions, open, send, rename) |
| `scripts/cmux_layout.py` | snapshot / list / show / restore |
| `scripts/cmux-open.sh` | tab / browser / split in a verified target workspace |
| `scripts/spawn-workspace.sh` | named workspace with an agent, prompt via file, verified start |
| `scripts/cmux-claude-restart.sh` | stop / start the agent across all tabs |
| `tests/` | run against a fake `cmux`, never the real one |
