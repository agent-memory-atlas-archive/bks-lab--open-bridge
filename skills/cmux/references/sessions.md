# cmux: sessions, recovery, observation

Loaded from `skills/cmux/SKILL.md` when a session or workspace is lost, when the
agent has to be restarted across all tabs, or when the question is which session
runs where.

## Lost workspaces: `cmux_layout.py`

cmux keeps one backup generation (`-previous.json`) and has dropped whole
workspaces on relaunch without a trace in its closed-item history
(manaflow-ai/cmux #2387, #8267). `cmux_layout.py` keeps several generations: it
reads cmux's session file directly (no socket needed), writes a snapshot to
`$CMUX_LAYOUT_DIR` (default `~/.local/state/cmux-layouts/`) only when workspaces
or tabs changed (titles alone do not count), and keeps seven days with at least
20 generations. Agent tabs cmux did not bind are resolved through their tty in
the process table.

**Schedule it.** Snapshots exist only if something takes them. Declare a workload
in `workflow/workloads/` (the `workload` skill provisions it) that runs
`python3 <bridge root>/skills/cmux/scripts/cmux_layout.py snapshot` every two to
five minutes on the machine cmux runs on.

```bash
S=skills/cmux/scripts/cmux_layout.py
python3 $S list                  # newest first: workspace / tab / agent counts
python3 $S show 3                # one generation in full
python3 $S restore 3             # dry run: what is missing, what already runs
python3 $S restore 3 --apply     # from a cmux tab: rebuild workspaces, tabs,
                                 # claude --resume, browser and markdown tabs
```

A drop in the counts in `list` is the loss. Restore skips sessions that still run
or are still bound to a tab (hibernated), adds into a workspace that still exists
under the same title, and starts every `claude --resume` with `; exec $SHELL -l`
behind it: a tab whose only process is the agent takes its workspace down when
the agent exits. It verifies each started session in `ps` and re-sends once,
because a shell update prompt can swallow the first character. Splits come back
as tabs in one pane.

**No snapshot yet?** The previous session file may still exist in a local
filesystem snapshot (on macOS: `tmutil listlocalsnapshots /`, then mount one
read-only with `mount_apfs -o ro,nobrowse -s <snapshot> /System/Volumes/Data
<mountpoint>` and read the session file under the user's
`Library/Application Support/cmux/`). Its panels carry the agent session UUID
(`resumeBinding` / `agent`), `browser.urlString` and `markdown.filePath`, enough
to rebuild by hand. A second source is cmux's agent journal (below):
`agent.session.ended` rows name every ended session with its UUID and time.

### Loss alarm

When a new snapshot shows 3 or more agent sessions or 2 or more workspaces fewer
than the one before, `snapshot` raises one alarm: the counts, the vanished tabs
with workspace and session id, and the restore command. It fires once per drop,
because the next run sees no change. Closing several tabs on purpose triggers it
too; the message says so. Thresholds: `--min-claude`, `--min-workspaces`.

Delivery goes through `CMUX_LAYOUT_NOTIFY`, an executable called with `--what`,
`--where`, `--do`, `--detail`. Point it at a small wrapper around one of the
instance's `infra/channels/` channels (a chat bot, a push service). Without it
the alarm is printed to the workload log. A configured notifier that fails makes
the run exit 1, so the workload's trace shows it.

### In place

```bash
cmux respawn-pane --surface surface:S --command "claude --resume <session-id>"   # restart in the same pane
cmux surface-health --workspace workspace:N       # crashed or running
cmux identify                                     # which workspace / surface / pane am I
cmux clear-history --surface surface:S            # clear scrollback
```

### Color and description

Each workspace can carry a color and a description
(`cmux workspace-action --workspace <ref> --action set-color --color Blue`,
`--action set-description --description "..."`; named colors Red, Crimson,
Orange, Amber, Olive, Green, Teal, Aqua, Blue, Navy, Indigo, Purple, Magenta,
Rose, Brown, Charcoal, or `#RRGGBB`). They live in the session file as
`customColor` / `customDescription`; snapshots keep them and `restore` sets them
again on every workspace it creates.

### Hibernated agents

With `terminal.agentHibernation.enabled` in `cmux.json`, cmux stops idle,
off-screen agent processes above `maxLiveTerminals` (default 12) and resumes them
when the tab is visited. Such a session has no process but stays bound to its
tab, so `restore` counts every session still bound in cmux's current layout as
present and never opens it twice. Under critical memory pressure cmux may also
hibernate a bounded batch of idle background agents; running, visible and
waiting agents are excluded.

## What cmux already does itself (checked against cmux 0.64)

Reach for these before writing anything of your own:

| Need | Native way | Limit |
|---|---|---|
| Resume the agent after a cmux relaunch | `autoResumeAgentSessions: true` in `cmux.json`, fed from each panel's `resumeBinding` | Only when the workspace itself survived (open bugs #2387, #5802, #9831) |
| Which session runs in which tab | `cmux sessions --json` (reads `~/.cmuxterm/claude-hook-sessions.json`, no socket): session id, cwd, workspace, surface, whether the pid lives | Only sessions cmux's hooks saw; a resumed agent can be missing, hence the tty lookup in `cmux_layout.py` |
| Resume inside one tab | `cmux restore --surface <ref> claude <session-id>` | Replaces the process of the tab it runs in |
| Reopen a closed tab or workspace | GUI undo-close; `closed-item-history-com.cmuxterm.app.json`, ring of 500 | Only regular closes; a lost workspace leaves no record there |
| Agent state (working, waiting, asking, approval) | `agent-journal-com.cmuxterm.app.sqlite3`, table `agent_journal`, append-only from the agent's hooks; live as `cmux events --category ...` | Open the sqlite as a copy (db + wal + shm); the app holds it |
| Multi-generation layout backup | none (feature request #2086) | `cmux_layout.py` fills this |
| Search across all agent sessions | `cmux vault search '<query>'` with `agent:`, `repo:`, `ws:`, `before:` / `after:`; `cmux vault sessions --folder <path>` | Try this before reading transcripts |
| Named checkpoint, branch off | `cmux vault checkpoint --agent claude --session <id> --name "<text>"`, `cmux fork --surface <ref> claude <checkpoint-id>` | The fork opens as a new session |

Sources: https://cmux.com/docs/session-restore, the manaflow-ai/cmux issues named
above, `cmux help`, and the files under cmux's Application Support folder.

**Prefer the journal over title glyphs.** The first character of a tab title
(Braille spinner = working, sparkle = idle, `user@host:` = shell) is a quick
heuristic and what the workplace driver uses for state; the journal records the
hook events themselves: `turn.started`, `turn.completed`, `approval.requested`,
`question.requested`, `session.ended`, with session, workspace and surface id.

## Claude Code's own view

`claude agents` lists every session with status (working, needs input, idle,
completed, failed), `--json` for scripts: a second view across all tabs. Naming
sessions (`claude -n <name>`, `/rename`) lets `claude --resume <name>` work
without the UUID. Transcripts live under `~/.claude/projects/<cwd with / as ->/`.

## Restart the agent in every tab (update)

`scripts/cmux-claude-restart.sh stop|start|restart|status` stops every agent tab,
remembers the session ids and resumes them. Its state lives in `$TMPDIR`
(override `CMUX_RESTART_STATE`), so it does not survive a reboot; after a reboot
use `cmux_layout.py restore`.

## Remote machines

Watching or answering agents on another machine: [`remote.md`](remote.md).
