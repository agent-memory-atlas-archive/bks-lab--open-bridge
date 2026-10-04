# cmux: steering agents on another machine

Loaded from `skills/cmux/SKILL.md` when agent sessions running in cmux on a
different machine should be watched or answered from a laptop or a phone.

## The one hard rule: who may talk to the socket

cmux's control socket runs in one of four modes (`automation.socketControlMode`
in `~/.config/cmux/cmux.json`): `off`, `cmuxOnly` (default), `allowAll`,
`password`.

- **cmuxOnly** admits only processes that cmux itself spawned. An SSH shell, a
  service-manager job, `launchctl asuser` and detached background processes all
  get `Failed to write to socket (Broken pipe, errno 32)`. Anything that must
  reach the socket from outside has to run as a cmux tab, or the mode has to
  change.
- **password** admits any local process that presents
  `automation.socketPassword`. This is what lets a background service drive cmux.
  Known trap: app updates have rewritten `cmux.json` and dropped the saved
  password, locking every client out without an alert (manaflow-ai/cmux #8372,
  #8335). Recovery over SSH: write the password back under
  `automation.socketPassword` (a top-level `socketPassword` and `settings.json`
  are ignored), restart cmux, restart the client. Keep the password in a secret
  store (`rules/secret-placement.md`), never in a tracked file.
- Some reading needs no socket at all: `cmux sessions --json` and the files under
  cmux's Application Support folder (see [`sessions.md`](sessions.md)). This is
  why `cmux_layout.py snapshot` works from a scheduled job.

## Options

| Way | What it gives | Traffic | Notes |
|---|---|---|---|
| **cmux mobile app** (pairing from the sidebar) | the same workspaces and tabs, answers and approvals from the lock screen | terminal traffic peer to peer over your own tailnet; sign-in, pairing metadata and optional push text via cmux servers | beta, paid tier; check current availability |
| **Third-party cmux remote apps** with their own relay on the host | mirror and type into a surface, needs-input inbox | own relay over the tailnet | usually need **password** socket mode and a background service; read the code at a pinned commit first |
| **Claude Code Remote Control** (`claude remote-control`, or `/remote-control` in a session) + the Claude app | send prompts, approve tools, full conversation, push on input needed | conversation text via Anthropic | needs a claude.ai login on the host |
| **Happy** (happy.engineering, MIT) | remote for one agent session, push, voice | end-to-end encrypted, relay self-hostable | |
| **SSH over a tailnet** into the host, then `claude agents` or `cmux read-screen` | everything, no extra service | tailnet only | always there |
| **Own broker** (HTTP + SSE in front of the socket) | a tailored phone view | tailnet only | only if nothing above fits |

For customer work, decide deliberately before routing conversation text through
a third party (Remote Control, a hosted relay, push text through cmux servers). A
third-party app with its own relay on the host gets full control of every
terminal: read its code at a pinned commit before installing.

## If this instance runs its own broker

It is instance infrastructure, not part of this skill. Declare it as a workload
(`workflow/workloads/`) and describe the host in `infra/remotes/<host>.yaml`
(port, exposure: tailnet or public, probe). Then
`grep -l cmux workflow/workloads/*.yaml` finds it.
