---
summary: "Set up the briefing dashboard in Claude Code step by step: install the briefing-ui mod, switch it on, build your own tabs, columns and marks in your briefing profile, keep slow sources fast with a cache, pick German or English, and add agent tabs through cmux if you use it. Every setting lives in your own files."
type: guide
last_updated: 2026-10-09
related:
  - briefings.md
  - workplace.md
  - ../workflow/briefings/_template.yaml
  - ../workflow/briefings/_schema.yaml
  - ../bridge-config.yaml.template
  - ../mods/README.md
  - ../mods/briefing-ui/hooks/register.tsx
---

# The briefing dashboard: setting it up

The briefing (`/briefing`, [`briefings.md`](briefings.md)) is text the agent
reads to you. The dashboard shows the same result as a card you click: what
waits for you, what you can hand off, your tasks, and tabs beside it for
whatever else your briefing collects (health checks, dates, GitHub, today's
commits, your inbox). Nothing on it costs tokens until you press a button that
asks Claude.

**Status.** Tested with Claude Code and cmux only. It is a Claude Code mod
(function hooks, early access, Claude Code 2.1.291 or newer); other agents
cannot load it. Without cmux everything works except the agent tabs.

## 1. Install the mod

The mod ships with open-bridge under `mods/briefing-ui`, published through the
folder marketplace `open-bridge-mods` in `mods/` ([`mods/README.md`](../mods/README.md)).
From the Bridge folder:

```bash
claude plugin marketplace add ./mods --scope local
claude plugin install briefing-ui@open-bridge-mods --scope local
```

`--scope local` keeps both to this Bridge (they land in
`.claude/settings.local.json`, which git ignores). The mod only acts in a folder
that holds `bridge-config.yaml` and `scripts/briefing.py`. After a pull that
changed the mod, `claude plugin update briefing-ui@open-bridge-mods --scope local`
and a new session bring the new version in.

## 2. Switch it on

In `bridge-config.yaml` (yours, never committed upstream):

```yaml
briefing:
  claude_code_ui:
    enabled: true
```

Start a new Claude Code session in the Bridge folder and type `/briefing-ui`.
The card appears in the conversation; `Sidebar` opens it as a side panel.
Every other key is optional; `bridge-config.yaml.template` lists them all with
their defaults:

| Key | Default | What it does |
|---|---|---|
| `surface` | `chat` | `chat`: a card in the conversation, `pane`: the side panel |
| `band` | `true` | one line above the prompt: waiting tabs, what is due now |
| `shortcuts` | `true` | type `3a` or `1a 4v` to act on numbered rows without asking Claude |
| `morning_hint` | `true` | the first session of the day points at the briefing |
| `language` | from `language.conversation`, else `en` | `de` or `en` for the dashboard's own words |
| `full_minutes` | `10` | on open, run the full briefing again when the last is older |
| `status_seconds` | `60` | how often the agent tabs are re-read (cmux only) |
| `voice` | `false` | a waiting tab is also spoken (macOS) |
| `snapshot_minutes` | `60` | back up the cmux layout while the session is open; `0` = never |
| `launch.target` | `area` | where "Do it" opens a tab: `area`, `tab`, `workspace` or `auto` |

## 3. Build your briefing profile

What the card and its tabs show comes from your briefing profile,
`workflow/briefings/<id>.yaml`. Without one the built-in profile runs (inbox,
advice, tasks, calendar, activity). Start from the template:

```bash
cp workflow/briefings/_template.yaml workflow/briefings/morning.yaml
python3 scripts/briefing.py validate          # names every problem
python3 scripts/briefing.py collect --json    # what the dashboard receives
```

Each section is one source: the inbox, your tasks, a calendar, a tracker
(GitHub, GitLab, Jira, Azure DevOps, Linear), today's commits, or any
program of your own that prints JSON (`kind: command`). The kinds and their
keys are in [`briefings.md`](briefings.md).

### Tabs and columns

Without `view.pages` the kind decides the tab: probes on Status, calendars on
Dates, trackers on Trackers, commits and the log on Today. To choose yourself:

```yaml
view:
  pages:
    - id: systems
      title: Systems
      sections:
        - {id: probes, alarm: true, empty: "all green"}
    - id: github
      title: GitHub
      sections: [github-mine, boards]
    - id: today
      title: Today
      sections:
        - commits
        - {id: activity, badge: false}
```

Every row has the same columns: when, title, detail, link. A page entry
overrides them per section (`when`, `detail`, `link` name an item field),
`empty` is the text for nothing, `alarm: true` turns every row into a red
finding, `badge: false` keeps a section out of the number on its tab.

### Marks for customers and projects

```yaml
view:
  marks:
    - {label: ACME, match: [acme, acme-portal], color: magenta}
    - {label: Beta, match: beta-corp, color: cyan}
```

A row whose title, id, project, repository, task, labels or link contains one
of the words gets the label in front, on the card, on the tabs and in the text
briefing. The first mark that fits wins. Customers change; keep them here.

### Fast despite slow sources

A tracker can take 20 seconds. `cache_minutes` on a section reuses its last
good answer for that long, and the section then says how old it is
("as of 08:46"):

```yaml
sections:
  - kind: tracker
    id: github-mine
    provider: github
    query: {assignee: "@me", kinds: [issues, prs]}
    cache_minutes: 5
```

⟳ on the dashboard always asks every source fresh. A failure is never kept,
and nothing cached crosses midnight.

### Words

The dashboard's own buttons and help come in German and English. The
briefing's words (headline, tab names, "today") are yours: set them in
`view.labels`, for example `labels: {page_status: Systeme, today: heute}`.

## 4. Agent tabs (optional, cmux)

With cmux, "Do it" and "Advise me" open an agent tab per task, the card shows
which tabs wait for you, and a tab that asks for permission gets Yes and No
buttons. Set up the `workplace:` block as in [`workplace.md`](workplace.md).
Name a control workspace (`workplace.control.name`): only the session there
polls the tabs and notifies, the others read along quietly.

## 5. When something is off

| You see | Why, and what to do |
|---|---|
| `/briefing-ui` says it is off | `briefing.claude_code_ui.enabled` is not `true`, or the session runs outside the Bridge folder |
| "Nothing waits for you" and empty tabs | the profile has no sections for it; run `briefing.py collect --json` and look at `pages` |
| a section reads "could not read: …" | its source failed; the reason follows (a token, a timeout); fix the source, then ⟳ |
| a tab lags behind | it is cached (`as of …`); ⟳ asks fresh |
| the tab line says the tab state is stale | `workplace.py status` failed; the reason is shown in red |
| a change to the mod shows no effect | an installed mod is a copy: raise its version, `claude plugin update briefing-ui@open-bridge-mods --scope local`, restart the session |
