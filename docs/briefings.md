---
summary: "Briefing profiles: each person describes the briefing they want in workflow/briefings/<id>.yaml (sections, trackers, queries, inbox rules); scripts/briefing.py executes it and the agent advises on the result. Section kinds, provider query keys, selection, change marks, inbox rules, org profiles."
type: guide
last_updated: 2026-10-04
related:
  - ../workflow/briefings/_schema.yaml
  - ../workflow/briefings/_template.yaml
  - ../scripts/briefing.py
  - ../scripts/tests/test_briefing.py
  - ../scripts/tests/test_briefing_providers.py
  - ../trackers/README.md
  - ../skills/briefing/references/workflow.md
  - ../skills/briefing/references/control.md
  - inbox.md
  - workplace.md
---

# Briefing profiles

Every person who uses a Bridge wants a different morning. One works from
GitHub issues, one from a Jira project, one from a customer's Azure board and
a calendar. A **briefing profile** says which, in a file the person owns:

```
workflow/briefings/morning.yaml     # plain /briefing
workflow/briefings/acme.yaml        # /briefing acme, before the customer call
workflow/briefings/weekly.yaml      # /briefing weekly, Friday afternoon
```

`scripts/briefing.py` runs the profile: every section, in the order written,
each with a time limit. The agent then advises on and renders what came back
(`skills/briefing/references/control.md`). Collection is code, not prose an
agent re-reads each morning, because a prose step can be skipped and nobody
notices: on one observed morning the trackers were not queried at all.

## Commands

```bash
python3 scripts/briefing.py list                  # the profiles, the default, their offer_on phrases
python3 scripts/briefing.py show [<id>]           # the resolved profile (also the built-in one)
python3 scripts/briefing.py offer "<text>"        # profiles whose offer_on matches the text
python3 scripts/briefing.py collect [<id>] --json --file
python3 scripts/briefing.py render [<id>]         # collect + plain terminal text
python3 scripts/briefing.py collect --skip tracker --skip calendar   # the quick mode
python3 scripts/briefing.py validate              # every profile; exit 1 on a problem
```

## Which profile runs

1. The id given (`/briefing acme`).
2. bridge-config.yaml `briefing.default`: the person's own choice, which wins
   over a flag in a file that may come from a shared overlay.
3. The profile with `default: true` (at most one; `validate` refuses two).
4. The only profile, when there is one.
5. Several and none chosen: `collect` exits 2 and names them; the agent asks.
6. No profile at all: the **built-in** one, equal to the briefing before
   profiles existed (inbox, advise, tasks, the trackers enabled under
   `integrations.*`, calendar when a tool is installed, activity, and the
   day's tabs when a `workplace:` block is configured). Existing Bridges keep
   working without a file.

`offer_on` lists phrases on which the Bridge proposes a profile by name
("good morning" → morning, "acme" → acme). That is how a Bridge with several
profiles offers the right one instead of the person having to remember ids.

## Section kinds

| kind | Shows | Keys |
|---|---|---|
| `inbox` | open inbox items, most urgent first ([inbox](inbox.md)) | `max` |
| `advise` | the advice checks: collisions, quiet and blocked tasks, WIP | `max` |
| `workplace` | the day's tab plan: one tab per task, grouped into workspaces, opened on your yes through the configured driver (cmux ships as `skills/cmux`) ([workplace](workplace.md)) | `max` |
| `tasks` | `work/tasks/*/STATUS.md` | `status` (default doing, review), `contexts`, `max` |
| `activity` | `work/log.md` rows of the last days | `days` (default 7), `max` |
| `calendar` | events in local time; also handed to `advise` for collisions. `ics` converts UTC and `TZID` times but lists a recurring event (RRULE) on its first date only: use `icalbuddy` or a `command` for recurring calendars | `provider` (auto, icalbuddy, ics, command), `days`, `path` (ics), `argv` (command), `exclude_calendars` (icalbuddy) |
| `tracker` | work items from an external system | `provider`, `query`, `account_ref`, `state_map`, `max`, `to_inbox` |
| `command` | any program printing a JSON list of items | `argv`, `max`, `to_inbox` |

Every section takes `id` (stable name, defaults to the kind; two sections of
one kind need distinct ids), `title`, `max` and `to_inbox`. Items follow the
normalized schema of [`trackers/README.md`](../trackers/README.md).

## Tracker providers

Each provider is a module under `scripts/lib/briefing_providers/`, tested
against recorded answers (`scripts/tests/fixtures/briefing/<provider>/`).
`trackers/*.md` stay as the documentation of each system.

| provider | Reaches it through | `query` keys |
|---|---|---|
| `github` | `gh search` (gh's own login) | `assignee` (default `@me`), `owners`, `repos`, `kinds` (issues, prs), `state`, `labels`, `review_requested`, `limit` |
| `github-board` | `gh project item-list`, boards from `github_projects:` in the ecosystem files, state maps from `workflow/projects/` (the same code as `scripts/tracker-sync.py`) | `boards`, `assigned_to_me`, `states`, `include_done`, `limit` |
| `gitlab` | `glab issue list` | `repos` (required), `assignee`, `state`, `labels`, `limit` |
| `ado` | `az boards query` (WIQL) | `wiql`, `organization`, `project`, `limit` |
| `jira` | REST API | `jql` (default: assigned to you, not done), `fields`, `limit` |
| `linear` | GraphQL API | `filter`, `team`, `limit` |

`state_map` on a section maps a raw state to a normalized one
(`{"Waiting for vendor": blocked}`) and overrides the provider's default.

### Tokens: references only

`gh`, `glab` and `az` use their own login; the profile carries no credential.
Jira and Linear need a token, and it never goes into the profile:
`account_ref` names an `identity/accounts/<id>.yaml` with the endpoint and a
`token_ref` **reference URI**, which `scripts/briefing.py` resolves through
the secrets engine at run time ([`rules/secret-placement.md`](../rules/secret-placement.md)).

```yaml
# identity/accounts/jira-example.yaml
id: jira-example
scope: user
display_name: "Jira (example)"
owner: your-handle
base_url: https://example.atlassian.net
email: you@example.com                       # Cloud basic auth
token_ref: keychain://example/jira-token     # the value lives in the keychain
# auth: bearer                               # Data Center personal access token
```

`validate` refuses a profile with a credential-named key holding a plain
value, and any value read through the engine is scrubbed from error lines.

## Change marks

The time limit (`timeout_sec`, default 30 s) covers a whole section, all of
its calls together, so a slow tracker costs at most that.

Each run is compared with the previous run of the same profile on the same
machine (`.bridge/briefings/<id>.last.json`, derived, not committed). Rows
carry `new` and `changed`, so a briefing can lead with what moved since
yesterday instead of repeating the whole list. A run in which a section
failed keeps that section's last good snapshot, so a lookup that failed
today does not make every row look new tomorrow.

## Inbox rules

`to_inbox` turns rows that need a person into [inbox](inbox.md) items:

```yaml
to_inbox:
  - when: {state: blocked}                         # every listed field must match
    urgency: now                                   # now | today (default) | later
  - when: {category: qa, assigned_to_me: true}     # a list value means "any of"
```

The key is `briefing:<profile>:<section>:<item>`, so a repeat is one item,
and a dropped key stays quiet. When the row is gone, the item closes on the
next run **in which that section completed**; an errored section closes
nothing, because a failed lookup is no evidence that the row is gone (the
same rule the advice checks follow). Filing needs `--file`, which the
briefing workflow passes.

## Profiles shared by an org

A profile with `scope: org` can ship in an org overlay, so a whole team gets
the same morning shape. `assignee: "@me"` resolves on each person's machine
to their own login, so one shared GitHub section gives every colleague their
own issues and pull requests across the org, and a `github-board` section
with `assigned_to_me: true` their own cards on the team's boards. A person
who wants something else sets `briefing.default` to their own profile; the
config wins over the shared file's `default: true`.

## Writing your own source

Anything without a provider is a `command` section: a program that prints a
JSON list (or JSON lines) of items in the normalized schema, run from the
Bridge root. A source that turns out to be useful to others is a new module
under `scripts/lib/briefing_providers/` with recorded answers and tests.

## Example

[`examples/portfolio/workflow/briefings/`](../examples/portfolio/workflow/briefings/)
has a morning profile (inbox, advice, a client board whose blocked cards
become inbox items, the person's own GitHub work, calendar) and a second
profile for one client's weekly call.
