---
summary: "Plan the day's work as workspaces with one agent tab per task, and steer the tabs from one place, through a driver so the same Bridge works with any terminal tool or none."
type: guide
last_updated: 2026-10-04
related:
  - ../scripts/workplace.py
  - inbox.md
  - ../skills/briefing/references/control.md
  - ../skills/cmux/SKILL.md
---

# Workplace

One agent per task, each in its own terminal tab, grouped into workspaces (one per
client, one for the platform, one for everything else), and one place from which you
see and steer all of them. The briefing proposes the day ("two clients, five tabs,
want the whole day open?"), you say yes, and the tabs open with an agent that already
read its task.

```bash
python3 scripts/workplace.py propose            # the plan: workspaces, tabs, why
python3 scripts/workplace.py open               # dry run
python3 scripts/workplace.py open --yes         # hand the plan to the driver
python3 scripts/workplace.py status             # every tab: task, state, last line
python3 scripts/workplace.py send <tab> <text>  # type into one tab
python3 scripts/workplace.py adopt <tab> <slug> # name an open tab after its task
```

## Plan and driver are separate on purpose

The **plan** is CORE and knows no terminal. It reads the active tasks
(`work/tasks/`, `work/streams/`, status doing or review), ranks them by recent log
activity, recency and priority, puts each into a workspace (slug pattern first, then
the task's `context:`, then the default workspace) and caps the day at
`max_workspaces` with `max_tabs` each. Blocked tasks and tasks resting longer than
`stale_days` get no tab; the plan names them instead. Every new tab carries the
command that starts its agent (`agent.new`, default Claude Code), a resumable one
the command that resumes the last session (`agent.resume`).

The **driver** is everything a terminal does: list the tabs that are open, open the
plan, type into a tab, rename one. Terminal tools differ completely here, so the
driver is a command the instance points at, and the plan never imports it.
A driver is optional. Without one (`driver: none`) the plan prints the commands to
start by hand, `status` has nothing to report and `send` says so: the same Bridge,
the same plan, no dependency.

## Configuration

```yaml
workplace:
  driver: none                       # or {command: ["python3", "path/to/driver.py"]}
  control: {name: Control}           # the tab that steers the others
  workspaces:
    - {name: Bigcorp, contexts: [bigcorp], color: "#1565C0"}
    - {name: Platform, slugs: ["platform-*"]}
    - {name: Misc, default: true}
  limits: {max_workspaces: 4, max_tabs: 3, stale_days: 10, activity_days: 7}
  tab_names: {payments-incident: Payments}
  agent: {new: "claude -n {slug} {prompt}", resume: "claude --resume {session}"}
```

`agent.new` gets `{slug}` and `{prompt}` (a short instruction to read the task's
STATUS.md, log rows, commits and open inbox items, report in eight lines and wait),
`agent.resume` gets `{session}`. Any agent CLI that takes a prompt fits.

## Writing a driver

A driver is a program that reads one JSON object on stdin and writes one on stdout,
the same shape `agents/_runtime/approval.py` uses for owner approval:

| Request | Answer |
|---|---|
| `{"verb": "tabs"}` | `{"tabs": [{"name", "workspace", "ref", "state", "last"}]}`, state one of `working`, `waiting`, `needs-you`, `shell` |
| `{"verb": "sessions"}` | `{"sessions": {"<tab name>": "<session id>"}}` |
| `{"verb": "open", "plan": {...}, "only": [...] or null, "resume": bool, "here": ref or null}` | `{"report": ["line", ...]}` |
| `{"verb": "send", "tab": ref, "text": "..."}` | `{"report": [...]}` |
| `{"verb": "rename", "tab": ref, "title": "..."}` | `{"report": [...]}` |

Rules every driver keeps: it never closes a tab or a workspace; a tab that is already
open is reused, never opened twice; `here` is the calling tab, which becomes the
control tab and moves last so no workspace is ever left empty. A driver that fails or
answers something unreadable is reported as a line, never raised, so the plan always
stands. A driver ships as an optional skill or with the tool itself; the plan never
imports it. `skills/cmux` is the reference driver, active only where cmux is
installed:

```yaml
workplace:
  driver: {command: ["python3", "${root}/skills/cmux/scripts/cmux_driver.py"]}
```

`driver: {command: [...]}` may use `${root}` for the repository root.

## From the briefing to open tabs

With a driver configured, the briefing's `workplace` section proposes one tab per
task, grouped into workspaces. On the person's yes, `workplace.py open --yes`
opens them through the driver; `status`, `send` and `adopt` steer them afterwards.

## Where tab state comes from

`status` shows what only the terminal knows: is the agent working, waiting for input,
or asking for a permission. What a tab has *achieved* (a finding, a question for you,
a draft, a result) does not come from the terminal: the agent files it in the inbox
(`docs/inbox.md`), the same place a scheduled job or a peer Bridge files theirs. That
keeps status equally good with any driver, and with none.
