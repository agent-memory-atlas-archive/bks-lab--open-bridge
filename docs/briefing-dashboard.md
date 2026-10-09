---
summary: "Set up the briefing dashboard in Claude Code step by step: install the briefing-ui mod, switch it on, build your own tabs, columns and marks in your briefing profile, keep slow sources fast with a cache, pick German or English, and add agent tabs through cmux if you use it. Every setting lives in your own files."
type: guide
last_updated: 2026-10-09
related:
  - briefings.md
  - workplace.md
  - inbox.md
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
asks Claude or opens an agent tab.

**Status.** Tested with Claude Code and cmux only. It is a Claude Code mod
(function hooks, early access); other agents cannot load it. Without cmux
everything works except the agent tabs: no tab line, no Yes and No for a
waiting tab, no layout backup.

## 1. Install the mod

You need:

- an onboarded Bridge: `bridge-config.yaml` in the repo root, written by
  `/bridge-onboard`;
- Claude Code 2.1.291 or newer (`claude --version`);
- `python3` with PyYAML (`python3 -c 'import yaml'` prints nothing): the mod
  reads `bridge-config.yaml` and runs the Bridge scripts through it.

Start Claude Code in the repo root, not a subfolder, because the mod checks
the current folder.

The mod ships with open-bridge under `mods/briefing-ui`, published through the
folder marketplace `open-bridge-mods` in `mods/` ([`mods/README.md`](../mods/README.md)).
From the Bridge folder:

```bash
claude plugin marketplace add ./mods --scope local
claude plugin install briefing-ui@open-bridge-mods --scope local
```

`--scope local` keeps both to this Bridge (they land in
`.claude/settings.local.json`, which git ignores). The mod only acts in a folder
that holds `bridge-config.yaml` and `scripts/briefing.py`. Claude Code reads the
mod straight from `mods/briefing-ui` (`claude plugin list` shows "Read from").
After a pull or an edit, start a new session or run `/reload-plugins`. If
`claude plugin list` shows no "Read from" line, your Claude Code keeps a copy:
then run `claude plugin update briefing-ui@open-bridge-mods --scope local`
first.

## 2. Switch it on

In `bridge-config.yaml` (yours, written by onboarding, never committed upstream),
add `claude_code_ui` under the `briefing:` block you already have:

```yaml
briefing:
  # ... your existing briefing keys stay as they are
  claude_code_ui:
    enabled: true
```

Do not add a second top-level `briefing:` key: YAML keeps only the last one,
so it silently replaces the first and its settings are gone.

Start a new Claude Code session in the Bridge folder and type `/briefing-ui`.
The card appears in the conversation; `Sidebar` (German: `Leiste`) opens it as
a side panel.

![The briefing card in the conversation](assets/briefing-dashboard/card.png)

The same card with the side panel open, and the band above the prompt at the bottom
(all data in these pictures is invented):

![The card and the side panel, with the band above the prompt](assets/briefing-dashboard/sidebar.png)

Every other key is optional; `bridge-config.yaml.template` lists them all with
their defaults:

| Key | Default | What it does |
|---|---|---|
| `surface` | `chat` | `chat`: a card in the conversation, `pane`: the side panel |
| `band` | `true` | one line above the prompt: waiting tabs, what is due now |
| `shortcuts` | `true` | type `3a` or `1a 4v` to act on numbered rows without asking Claude (letters below) |
| `morning_hint` | `true` | the first session of the day points at the briefing |
| `language` | from `language.conversation`, else `en` | `de` or `en` for the dashboard's own words |
| `full_minutes` | `10` | on open, run the full briefing again when the last is older |
| `status_seconds` | `60` | how often, in seconds, the agent tabs are re-read (cmux only); a value below 15 counts as 15 |
| `voice` | `false` | a waiting tab is also spoken (macOS) |
| `snapshot_minutes` | `60` | back up the cmux layout while a session inside cmux is open; `0` = never |
| `launch.target` | `area` | where "Do it" opens a tab: `area`, `tab`, `workspace` or `auto` |

The dashboard's default target is `area` (the workspace of the item's area),
while `workplace.py launch` on its own defaults to `tab` (the calling tab's
workspace).

Shortcut letters, after the row number as it stands on the card: `a` Do it,
`b` Later (tomorrow), `c` Drop (an inbox entry is dropped, any other row is
hidden for a week), `v` Advise me, `w` Do it in its own workspace. Shortcuts
work only while today's card is open in this session and shows the Briefing
tab; otherwise the text goes to Claude as an ordinary message.
`/briefing-ui-off` hides the line above the prompt for this session;
`/briefing-ui` still opens the dashboard.

Do it on an inbox entry that waits for your yes to run an action approves it;
nothing runs at once. The action runs at the next `python3 scripts/inbox.py run` on the
machine named in `inbox.runner` ([`inbox.md`](inbox.md)). Any other row gets
an agent tab (section 4).

## 3. Build your briefing profile

What the card and its tabs show comes from your briefing profile,
`workflow/briefings/<id>.yaml`. The dashboard shows the default profile: the
one `briefing.default` in `bridge-config.yaml` names, else the one with
`default: true`, else the only one there is. The card is built from the
profile's view, so the profile needs a `view.style` other than `sources`
(the template uses `triage`).

Without a profile of your own the built-in one runs (inbox, advice, tasks,
calendar, activity, and the trackers you enabled). It has no view, so the
dashboard asks for the triage view itself: the card shows your inbox, the
advice and your tasks, the calendar and the activity sit on their tabs. That
is enough to try the dashboard; for your own sources, tabs and marks, copy
the template:

```bash
cp workflow/briefings/_template.yaml workflow/briefings/morning.yaml
python3 scripts/briefing.py validate          # names every problem
python3 scripts/briefing.py collect --json    # what the dashboard receives
```

Edit `for:` and the `owners:` of the `github-mine` section (your GitHub org or
user) before you collect, or delete that section if you do not use GitHub.
Otherwise it answers without error and stays empty.

Each section is one source: the inbox, your tasks, a calendar, a tracker
(GitHub, GitLab, Jira, Azure DevOps, Linear), today's commits, or any
program of your own that prints JSON (`kind: command`). The kinds and their
keys are in [`briefings.md`](briefings.md).

### Tabs and columns

![A tracker tab: marks in front of the rows, the section answered from its cache ("as of 13:55")](assets/briefing-dashboard/tabs.png)

Without `view.pages` the kind decides the tab: `command` sections (your own
probes) on Status, calendars on Dates, trackers on Trackers, commits and
activity on Today, inbox, advice and tasks on the briefing itself, any other
kind on More. To choose yourself, merge these keys into
the `view:` block your profile already has, and add the two sections the
template leaves commented out:

```yaml
view:
  pages:
    - id: github
      title: GitHub
      sections: [github-mine]                  # the template's tracker section
    - id: today
      title: Today
      sections:
        - calendar                             # a section without id: its kind
        - commits
        - {id: activity, badge: false}
    - id: systems
      title: Systems
      sections:
        - {id: probes, alarm: true, empty: "all green"}

sections:
  # ... the template's sections, then:
  - kind: commits
    days: 7
  - kind: command                              # any program printing JSON items
    id: probes
    title: "Probes"
    argv: ["python3", "tools/probes.py"]
```

A page names sections by id; `validate` says which id it cannot find.

Every row has the same columns: when, title, detail, link. A page entry
overrides them per section (`when`, `detail`, `link` name an item field),
`empty` is the text for nothing (default "nothing"), `alarm: true` turns
every row into a red finding and nothing more, `badge: false` keeps a section
out of the number on its tab.

### Marks for customers and projects

```yaml
view:
  marks:
    - {label: ACME, match: [acme, acme-portal], color: magenta}
    - {label: Beta, match: beta-corp, color: cyan}
```

A row whose title, id, project, repo, task, context, area, labels or url (its
link) contains one of the words gets the label in front, on the card, on the tabs and in the text
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

`⟳ reload` (German: `⟳ neu`) on the dashboard always asks every source fresh. A failure is never kept,
and nothing cached crosses midnight.

### Words

The dashboard's own buttons and help come in German and English. The
briefing's words (headline, tab names, "today") are yours: set them in
`view.labels`, for example `labels: {page_status: Systeme, today: heute}`.

## 4. Agent tabs (optional, cmux)

With cmux, "Do it" and "Advise me" open an agent tab per task, the card shows
which tabs wait for you, and a tab that asks for permission gets Yes and No
buttons. That needs three things:

1. cmux installed;
2. Claude Code started inside a cmux tab;
3. the cmux driver in the `workplace:` block of `bridge-config.yaml`
   ([`workplace.md`](workplace.md)):

```yaml
workplace:
  driver: {command: ["python3", "${root}/skills/cmux/scripts/cmux_driver.py"]}
  control: {name: Control}
```

Without the driver, Do it and Advise me open nothing: the note at the bottom
of the card lists the commands to start by hand, one terminal each.

A row of a page that shows a `tasks` section opens with ▾, at any width, the
narrow side panel included. It shows the task's priority, area and status, its
origin, next step, blocker, the first open steps (unchecked boxes, else the
bullets under a "Next steps" heading in STATUS.md; a profile names headings in
another language with the tasks section's `step_headings`) and its latest log rows, then
every way to work on it: Do it, Advise me, and "Start:" as a tab here, in its
area's workspace or in its own workspace. A task with a running agent tab offers
that tab and its answer buttons instead; the task's open inbox entries follow
with their own buttons, then later, priority, team, context and adopt.

A start is held for a few seconds per item, so a double click in one card
never opens two tabs; workplace.py itself skips an item whose agent already
runs and the card switches to that tab (a tab that is still starting is not
seen yet, so a click from a second session in those seconds can open a second
one). The start note names the area, and the result names the workspace each
tab went to. A tab in state `shell` (the
command never started, or the agent ended) blocks nothing: its row offers
Restart next to Go to tab. A task whose only rows are inbox entries keeps its
own row under the tasks, with "N in the inbox".

`workplace.control.name` names a workspace: the workspace whose session steers
the others. The dashboard in that session polls the agent tabs and notifies;
the dashboards in other sessions read its state quietly.

### Check all, and closing a finished task

A task can be finished without anybody saying so: its linked issue was closed a
week ago, the PR merged, every box checked. Two buttons catch that.

**check all** sits in the header of the tasks page and of the card's "Your tasks"
block. It runs `python3 scripts/task.py review --all --json` and changes no task.
For every task under `work/tasks/` in `doing` or `review` (`--backlog` adds the
backlog; a named slug is checked whatever its status) the script gathers evidence
that costs nothing: the frontmatter (status, priority, `blocked_by`, dates, headline), the
first open steps and the latest log rows (the same ones the opened row shows),
the latest notes, the date of the last commit touching the task's folder, its open
inbox items, and the state of every GitHub issue or PR it names (`sync.github`
issues and pull requests, plus `owner/repo#N` in `blocked_by`, headline, title
and steps). All references of all tasks are resolved in ONE `gh api graphql`
call; when gh fails they are marked unknown and the check goes on.

Two signals are computed from that before any model: `own_refs_closed` (every
issue and PR in `sync.github` is closed as completed or merged) and
`blocker_resolved` (every reference `blocked_by` names, a bare `#N` meaning the
task's own repository, is closed or merged; a PR closed without merge counts as
not done). They head the task's evidence. `own_refs_closed` means `close`: the
model's reason names the closed reference with its date and the steps that still
look open, and the result carries `resolved` whatever the model answered, so the
card tags the task `close?` and offers Close: a weak answer cannot hide a finished
task. `blocker_resolved` alone is a hint for the model and a line on the card
("unblocked: <ref> <date>"), never a close by itself.

A model then judges. Tiered, to stay cheap:

| Pass | Model | Who goes |
|---|---|---|
| 1 | `models.mechanical` (else `models.routine`, else `claude-haiku-5-5`) | every task whose evidence changed, all in ONE call |
| 2 | `models.directed` (else `models.analysis`, else `claude-sonnet-5-5`) | only the answers that were `unclear`, again in one call |

Aliases (`haiku`, `sonnet`, `opus`) are mapped to full model ids: the CLI alias
`haiku` resolved to an older model than its name suggested. The answer is one of
`close` (the evidence shows the work is done or moot), `continue`, `waiting`
(blocked on someone or something still pending), `stale` (no activity for
`work.review.stale_days`, default 21, and no blocker) or `unclear`, with one sentence of reason in your `language` and a
confidence. The note on the card names count, how many to close and the cost,
for example "14 reviewed, 3 to close, 0.9 ct", or "cost unknown" when a call
failed, timed out or the command reports no cost. The whole review stays inside
190 s (the second pass gets only what is left; each pass is cached as soon as it
answers), and the card waits 240 s. When the models that answered
are not the ones asked for (`modelUsage` of the Claude JSON output), the note
says so.

Verdicts are cached in `.bridge/task-review.json` (derived, never committed), by
a hash of the evidence together with the language, the two model ids, `stale_days`
and a prompt version. A task whose evidence did not change keeps its verdict
for `work.review.max_age_days` (default 7) and reaches no model; `--fresh` asks
again. The card reads this file on open, so the last verdicts are there without
a click. The command is a template, any agent that reads the prompt on stdin
and prints the JSON array will do:

```yaml
work:
  review:
    command: "claude -p --model {model} --output-format json --no-session-persistence --setting-sources '' --strict-mcp-config --tools ''"
    max_age_days: 7
    stale_days: 21
```

A collapsed row with a recommendation carries a short tag (`close?`, `stale?`,
`waiting`, `unclear?`); a low confidence adds a question mark (`stale??`). A
`stale` verdict offers Close and Keep too; Close then closes with
`outcome: declined`, since a stale task was dropped, not finished. A stream
never shows Done or Close. Opened, it reads "Recommendation (Haiku 5.5): <reason>";
a `close` offers **Close** and **Keep**. Keep (`task.py review --keep <slug>`)
hides the recommendation until the task's evidence changes. **check** reviews
just this task.

**Done** stands in every opened task row. The first click turns it into "really
close?", a second click within five seconds runs `task.py close <slug> --reason
...` with the recommendation's reason (else "closed from the dashboard"): the
scripted 3-step close of [`work-system.md`](work-system.md). The row leaves the
card at once.

## 5. When something is off

| You see | Why, and what to do |
|---|---|
| `/briefing-ui` says it is off | `briefing.claude_code_ui.enabled` is not `true`, or `scripts/briefing.py` is missing in this folder |
| `/briefing-ui` says it could not read `bridge-config.yaml` | the file has a YAML error, or `python3` lacks PyYAML; the reason follows the message |
| `/briefing-ui` is an unknown command | the session does not run in the Bridge root, or the mod is not installed or enabled for this project (`claude plugin list`) |
| "Nothing waits for you" and empty tabs | the profile has no sections for it; run `python3 scripts/briefing.py collect --json` and look at `pages` |
| a tracker tab is empty but not failing | check its `query` (`owners`, `repos`): the template's placeholders find nothing |
| a section reads "could not read: …" | its source failed; the reason follows (a token, a timeout); fix the source, then ⟳ |
| a tab lags behind | it is cached (`as of …`); ⟳ asks fresh |
| the tab line says the tab state is stale | `workplace.py status` failed; the reason is shown in red |
| a change to the mod shows no effect | start a new session or run `/reload-plugins`; only if `claude plugin list` shows no "Read from" line, run `claude plugin update briefing-ui@open-bridge-mods --scope local` first |
