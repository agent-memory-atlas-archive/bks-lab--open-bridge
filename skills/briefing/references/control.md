# Briefing as the control room: inbox first, one thing first, every line a lever

The rest of `workflow.md` gathers. This file decides what the person sees first and
what they can do from it. It runs in two places: **Phase 0.5** (before the streams)
and **Phase 4** (the top of the output). Model of the inbox: `docs/inbox.md`.
Workplace: `docs/workplace.md`. The always-on machine: `docs/always-on-machine.md`.

## The rule this file exists for

**Nothing is reported as open from the log.** A log row saying "needed" is history;
whether it is still needed is a question for the live source. A briefing that read
the log reported three things as open that had been solved hours earlier. Open is
what the inbox says after `check`, plus what a tracker or calendar says live.

## Phase 0.5: settle the inbox (always, also with `--quick`)

```bash
python3 scripts/inbox.py check            # close what the live source says is done
python3 scripts/inbox.py run --dry-run    # what a person already released and is ready
python3 scripts/inbox.py run              # execute it (free, a yes, or a yes whose condition holds)
```

`run` never executes an `only-you` item (send, publish, pay), whatever was recorded,
and never anything nobody released. Report every `ran` and every `failed` line
in the output; a `failed` item is back to open and belongs on top. When
`inbox.runner` names another machine, `run` says "not running" and the briefing
shows the `--dry-run` list as "ready, waiting for <runner>" instead.
No `work/inbox/` yet: skip silently; the first item creates it.

## After the streams: advise

Once Stream C has today's and tomorrow's calendar, write it as a JSON list of
`{"title", "start", "end"}` to a temp file and run:

```bash
python3 skills/briefing/scripts/advise.py --file --calendar-json "$TMP/calendar.json"
python3 skills/briefing/scripts/advise.py --json --calendar-json "$TMP/calendar.json"
```

`--file` turns collisions, quiet tasks, long blocks and WIP over the cap into inbox
items under stable keys (a repeat stays one item; a finding that is gone closes its
own item). The `--json` run adds the report-only lines (`waiting`, `due`). Without a
calendar the collision check is skipped, everything else runs. Thresholds:
`briefing.advise` in bridge-config.yaml.

Then `python3 scripts/inbox.py list --json` is the source for the top of the output.

## Phase 4: the top of the output

Render these three sections ABOVE everything else in `workflow.md` § Phase 4.

```
── One thing first ────────────────────────────────────────────────────────

  {summary}
  {why it is first: urgency, due, collision, what waits on it}
  → {proposed action}            [{gate}]   {a} yes · {b} later · {c} drop

── Waiting for you ({N}) ──────────────────────────────────────────────────

  1. {urgency} {kind}  {summary}  [{task}]  → {action or "decide"}  [{gate}]
  2. ...
  Ran since last briefing: {items closed by `check` or executed by `run`}

── Workplace today ────────────────────────────────────────────────────────

  {output of: python3 scripts/workplace.py propose}
  [a] open all · [b] only <workspaces> · [c] nothing
```

**One thing first** is the first item of `inbox.py list` (ordered by urgency, then
decisions before findings, then due), unless an advise finding of urgency `now`
exists. Say WHY it is first in one line. If nothing is open: "Nothing waits for
you", and the section shows the most active task instead.

**Waiting for you** lists the rest, at most 7 lines; more collapse to a count. Group
by task when three or more share one. Never list an item twice because a tracker
also shows it: the inbox line wins and the tracker section drops its duplicate.

**Workplace today** appears only when bridge-config.yaml has a `workplace:` block.
Opening needs the person's answer: show the dry run (`workplace.py open`), then
`workplace.py open --yes` or `--only A,B --yes`. The driver decides how tabs open;
with driver `none` the person gets the commands to start themselves.

## Every line is a lever

| Gate | Meaning | What the briefing may do |
|---|---|---|
| `free` | the Bridge may act alone | do it now and report it (regenerate, read, close a stale advise item) |
| `your-yes` | acts after a yes | ask; on yes run it, on "yes once X" record a conditional yes |
| `only-you` | send, publish, pay | prepare (draft, branch), never execute; say "you press send" |

Answers map onto the inbox, never onto memory or a log sentence:

| The person says | Do |
|---|---|
| yes / do it / `a` | `inbox.py approve <id>` then `inbox.py run` |
| yes once {condition} | `inbox.py approve <id> --when-json '<probe>'` (only `your-yes`; `run` executes it later) |
| later / tomorrow / `b` | `inbox.py defer <id> --until <date>` |
| drop it / `c` | `inbox.py drop <id> --note "<why>"` |
| done already | `inbox.py close <id> --note "<how>"` and, if the probe missed it, fix the probe |
| status | `workplace.py status` plus the open count per task from the inbox |
| tell {tab}: {text} | `workplace.py send <tab> <text>`; show what goes where first unless the person named both |

A condition is a probe (`docs/inbox.md` § Probes): "once it is green" on a PR is
`{"gh_pr": "owner/repo#N", "state": "green"}`.

## Offer the arm

When an item or task waits on something outside (a blocked task, a PR waiting
for checks, a reply that has not come, a service that should come back), and
a file in `infra/remotes/` lists `arm` under `capabilities` (a machine that is
always on and keeps a Bridge clone, `docs/always-on-machine.md`), offer once per item:

```
  Should {machine} watch this and file an item when it moves?   [your-yes]
```

On yes, declare the watcher through the `workload` skill with `reports_to: inbox`
and a `closes_when` matching the item. Without such a machine, say nothing: the
offer only appears where it can be kept.

## Write back

Whatever stays open at the end of the briefing is an item, not a sentence: a
promise made in a meeting, a "check tomorrow", a reply owed. File it with
`inbox.py add` and a `closes_when` wherever the live source can tell. Then
`inbox.py render` regenerates `work/inbox.md` next to `work/board.md`.
