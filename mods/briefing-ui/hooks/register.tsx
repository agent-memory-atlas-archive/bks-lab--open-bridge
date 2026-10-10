import { atom, read, update } from 'claude-code'
import type { ButtonProps, EngineInterface, Register, RenderNode, ResolveInput, TextProps } from 'claude-code'

import type {
  Info, Mark, Mode, OvFilter, OvSort, PageId, Review, ReviewMeta, Row, SectionId, SideTab, Tab, TabSeen, Target, Team, TeamRun, UiConfig, View,
} from '../types'
import {
  askAbout, askInfo, asText, ATTENTION, BRIEFING_PAGE, clockTime, DAY, evening, filedBy, followUp, isoDate,
  isLive, isWaiting, launchItem, layout, longText, mergeView, modelShort, nextMonday, overview, pageBadge, planDay,
  parseConfig, parseDate, parseReview, parseReviewCache, parseReviewLast, parseTasks, parseTeams, parseView,
  barParts, capFirst, confDots, effectiveVerdict, minutesSince, ovCounts, ovFilter, ovSort, STRIP_ORDER, VERDICT_ORDER, refNumber, rowUrl, short, SHORTCUT, stateWord, tabColor, tabFor, taskRow,
  taskRowFor, teamState, toTab, withTasks,
} from './logic'
import type { Layout, Section, TaskInfo } from './logic'
import { TABLES, T, setLanguage } from './text'

/**
 * briefing-ui: the briefing as a clickable dashboard in Claude Code.
 *
 * The mod is a thin surface over the bridge scripts and holds
 * no logic of its own: data comes from `briefing.py collect --json`,
 * `inbox.py` and `workplace.py status --json`, every action is one of these
 * calls. It does nothing unless the session runs in a bridge
 * and `briefing.claude_code_ui.enabled` in bridge-config.yaml is true.
 *
 * The card is built around the questions of the day, not around the sections
 * of the briefing: who is waiting for me, what do I hand off, what am I working on,
 * what is for later. Compact shows only the most important rows of each block.
 *
 * Early access: written against the function hooks API of Claude Code
 * 2.1.291, which may change between versions.
 */

const PANE = 'briefing-ui'
const STORE_VIEW = 'briefing-ui:view'
const STORE_DAY = 'briefing-ui:morning'
const STORE_HIDDEN = 'briefing-ui:hidden'
const STORE_TEAMS = 'briefing-ui:teams'

const config = atom({ plugin: 'briefing-ui', key: 'config' } as const, null)
const view = atom({ plugin: 'briefing-ui', key: 'view' } as const, null)
const loading = atom({ plugin: 'briefing-ui', key: 'loading' } as const, null)
const tabs = atom({ plugin: 'briefing-ui', key: 'tabs' } as const, [])
const selected = atom({ plugin: 'briefing-ui', key: 'selected' } as const, [])
const settled = atom({ plugin: 'briefing-ui', key: 'settled' } as const, [])
const expanded = atom({ plugin: 'briefing-ui', key: 'expanded' } as const, null)
const notes = atom({ plugin: 'briefing-ui', key: 'notes' } as const, [])
const isBandHidden = atom({ plugin: 'briefing-ui', key: 'isBandHidden' } as const, false)
const messageTo = atom({ plugin: 'briefing-ui', key: 'messageTo' } as const, null)
const hidden = atom({ plugin: 'briefing-ui', key: 'hidden' } as const, {})
const openSection = atom({ plugin: 'briefing-ui', key: 'openSection' } as const, null)
const showAll = atom({ plugin: 'briefing-ui', key: 'showAll' } as const, false)
const showTabs = atom({ plugin: 'briefing-ui', key: 'showTabs' } as const, false)
const cardId = atom({ plugin: 'briefing-ui', key: 'cardId' } as const, null)
const isClosed = atom({ plugin: 'briefing-ui', key: 'isClosed' } as const, false)
const showHelp = atom({ plugin: 'briefing-ui', key: 'showHelp' } as const, false)
const helpLang = atom({ plugin: 'briefing-ui', key: 'helpLang' } as const, 'en' as 'de' | 'en')
const teamList = atom({ plugin: 'briefing-ui', key: 'teams' } as const, [])
const teamOf = atom({ plugin: 'briefing-ui', key: 'teamOf' } as const, {})
const tabSeen = atom({ plugin: 'briefing-ui', key: 'tabSeen' } as const, {})
const lastSnapshot = atom({ plugin: 'briefing-ui', key: 'lastSnapshot' } as const, null)
const snapshots = atom({ plugin: 'briefing-ui', key: 'snapshots' } as const, null)
const sideTab = atom({ plugin: 'briefing-ui', key: 'sideTab' } as const, 'all')
const sidePage = atom({ plugin: 'briefing-ui', key: 'sidePage' } as const, 0)
const sideMore = atom({ plugin: 'briefing-ui', key: 'sideMore' } as const, false)
const page = atom({ plugin: 'briefing-ui', key: 'page' } as const, 'briefing' as PageId)
/** How long the last quick run and the last second run took (ms), for the loading indicator */
const loadTook = atom({ plugin: 'briefing-ui', key: 'loadTook' } as const, {} as Record<string, number>)
const tabsError = atom({ plugin: 'briefing-ui', key: 'tabsError' } as const, null as string | null)
const isControl = atom({ plugin: 'briefing-ui', key: 'isControl' } as const, null as boolean | null)
const starting = atom({ plugin: 'briefing-ui', key: 'starting' } as const, [] as string[])
/** The active tasks as workplace.py tasks lists them: area, priority, type; a page row opens with them */
const taskInfo = atom({ plugin: 'briefing-ui', key: 'taskInfo' } as const, [] as TaskInfo[])
/** The last recommendation per task (task.py review); on open read from its cache file, no model asked */
const reviews = atom({ plugin: 'briefing-ui', key: 'reviews' } as const, {} as Record<string, Review>)
const reviewing = atom({ plugin: 'briefing-ui', key: 'reviewing' } as const, null as string | null)
const confirmClose = atom({ plugin: 'briefing-ui', key: 'confirmClose' } as const, null as { slug: string; at: number } | null)
const closedTasks = atom({ plugin: 'briefing-ui', key: 'closedTasks' } as const, [] as string[])
/** The review overview: last run, filter, sort, picks, open row, a pending bulk close, shown on the card */
const reviewMeta = atom({ plugin: 'briefing-ui', key: 'reviewMeta' } as const, null as ReviewMeta | null)
const ovFilterAtom = atom({ plugin: 'briefing-ui', key: 'ovFilter' } as const, 'all' as OvFilter)
const ovSortAtom = atom({ plugin: 'briefing-ui', key: 'ovSort' } as const, 'verdict' as OvSort)
const ovPicked = atom({ plugin: 'briefing-ui', key: 'ovPicked' } as const, [] as string[])
const ovOpen = atom({ plugin: 'briefing-ui', key: 'ovOpen' } as const, null as string | null)
const ovConfirm = atom({ plugin: 'briefing-ui', key: 'ovConfirm' } as const, null as { at: number; n: number } | null)
const showOverview = atom({ plugin: 'briefing-ui', key: 'showOverview' } as const, false)
/** The verdicts' colours: the card's own (green works, yellow wants you, cyan waits, magenta marks) */
const VERDICT_COLOR: Record<string, string> = { close: 'green', stale: 'yellow', waiting: 'cyan', continue: 'blue',
  unclear: 'magenta' }
/** task.py keeps the whole review (evidence and both tiers) inside 190 s; this leaves a margin */
const REVIEW_TIMEOUT_MS = 240000
/** How long the first click on Done waits for the second */
const CONFIRM_MS = 5000
const REVIEW_CACHE = '.bridge/task-review.json'
/** How long an item counts as starting after its start returned: until the tab list knows the new tab */
const START_HOLD_MS = 15000
/** A start may wait for the router (45 s) and for the driver to see the command run (20 s) */
const LAUNCH_TIMEOUT_MS = 150000
const confirmAll = atom({ plugin: 'briefing-ui', key: 'confirmAll' } as const, false)
/**
 * True once a collect came back without a view: the built-in profile, or a profile whose view.style is
 * sources. The card is built from the view, so from then on this session asks for the triage view.
 */
const askTriage = atom({ plugin: 'briefing-ui', key: 'askTriage' } as const, false)
/** Why bridge-config.yaml could not be read; null when it was read (switched on or off) */
const configError = atom({ plugin: 'briefing-ui', key: 'configError' } as const, null as string | null)

const READ_CONFIG = [
  'import json, yaml',
  "c = (yaml.safe_load(open('bridge-config.yaml', encoding='utf-8')) or {})",
  "u = dict((c.get('briefing') or {}).get('claude_code_ui') or {})",
  "u['_control'] = (((c.get('workplace') or {}).get('control') or {}).get('name'))",
  "l = c.get('language')",
  "u['_language'] = l.get('conversation') if isinstance(l, dict) else l",
  'print(json.dumps(u))',
].join('\n')

const PRIO_COLOR: Record<string, string> = { P0: 'red', P1: 'yellow', P2: 'cyan', P3: 'gray' }
const TAB_CAP = 4
/** Below this width (columns) the card in the chat also draws as a sidebar */
const NARROW = 90

const SECTION_COLOR: Record<SectionId, string | undefined> = { now: 'yellow', give: 'cyan', work: 'green', later: 'gray' }
/** Separator line that the layout shortens to the width */
const RULE = '─'.repeat(300)
/** The languages name themselves in their own language */
const LANG_NAME = { de: 'Deutsch', en: 'English' } as const
/** The identifier sits in the text of the output line, the only place that tells one card from another. */
const CARD_ID = /\(briefing-ui (\d+)\)/

// ---------------------------------------------------------------- Buttons

/**
 * The affordance rule of the whole mod: everything clickable is a framed button in a colour, the one main
 * action of an area `variant="primary"` (or `selected`), closing and dropping in red; grey is information
 * only. A checkbox ("[x]", "[ ]") is the one plain button, and it is coloured too. Every Button of the mod
 * goes through this, so a `plain` or `dimColor` at a call site cannot slip through; labels start with a capital.
 */
type FramedProps = Omit<ButtonProps, 'label' | 'plain' | 'dimColor'> & {
  label: string
  /** colour of the label; cyan by default, red for close and drop */
  tone?: string
  /** the current choice of a group (filter, sort, language, priority): drawn as primary */
  selected?: boolean
  plain?: boolean
  dimColor?: boolean
}

function framed(Raw: (p: ButtonProps) => RenderNode, Txt: (p: TextProps) => RenderNode) {
  return (p: FramedProps): RenderNode | null | undefined => {
    const { tone, selected, plain: _plain, dimColor: _dim, label, variant, ...rest } = p
    const text = capFirst(label.trim())
    const isCheckbox = /^\[[ x]\]$/.test(text)
    const isPrimary = variant === 'primary' || selected === true
    const props = { ...rest, label: text, ...(isPrimary ? { variant: 'primary' as const } : {}),
      ...(isCheckbox ? { plain: true as const } : {}) }
    return isPrimary ? h(Raw, props) : h(Raw, props, h(Txt, { color: tone ?? 'cyan' }, text))
  }
}

const RED = 'red'

// ---------------------------------------------------------------- Bridge calls

async function bridge(
  $: EngineInterface,
  args: string[],
  timeoutMs = 30000,
): Promise<{ ok: boolean; out: string; err: string }> {
  const cwd = await $.session.cwd()
  try {
    const run = await $.process.run(['python3', ...args], { cwd, timeoutMs })
    return { ok: run.exitCode === 0, out: run.stdout, err: run.stderr.trim() }
  } catch (error) {
    return { ok: false, out: '', err: String(error) }
  }
}

/** Feedback for a click: as a brief toast, and readable at the bottom of the card. */
async function note($: EngineInterface, text: string): Promise<void> {
  const now = await $.clock.now()
  await update($, notes, list => [`${clockTime(now)} ${text}`, ...list].slice(0, 6))
  $.ui.toast(short(text, 160))
}

/** What an action returns and has not already reported itself becomes feedback. */
function reported(): Set<string> {
  const t = T()
  return new Set([t.resDo, t.resLater, t.resDrop, t.resDone, t.resStarted, t.resPartly, t.resFailed, t.resHidden,
    t.resAsked, ''])
}

function act($: EngineInterface, run: () => unknown): () => Promise<void> {
  return async () => {
    const result = await run()
    if (typeof result === 'string' && !reported().has(result)) await note($, result)
  }
}

/**
 * What the session finds: outside a Bridge, a config that could not be read (with the reason),
 * switched off, or the config. A read error is never reported as "switched off".
 */
type Loaded = { outside: true } | { error: string } | { off: true } | { cfg: UiConfig }

async function loadConfig($: EngineInterface): Promise<Loaded> {
  const cwd = await $.session.cwd()
  const isBridge =
    (await $.fs.exists(`${cwd}/bridge-config.yaml`)) && (await $.fs.exists(`${cwd}/scripts/briefing.py`))
  if (!isBridge) return { outside: true }
  const run = await bridge($, ['-c', READ_CONFIG], 15000)
  if (!run.ok) return { error: short(run.err || 'python3 failed', 200) }
  try {
    const cfg = parseConfig(JSON.parse(run.out) as Record<string, unknown>)
    // even when switched off: the notice from /briefing-ui already speaks the configured language
    setLanguage(cfg.language)
    return cfg.enabled ? { cfg } : { off: true }
  } catch (error) {
    return { error: short(String(error), 200) }
  }
}


/**
 * quick: everything except trackers and command sections (SLOW_KINDS); those stay at the
 * last state · auto: on open; if the last full run is older than full_minutes
 * (briefing.claude_code_ui), a second run fetches everything · full: always both, with --fresh.
 */
type LoadHow = 'quick' | 'auto' | 'full'
const HOW_RANK: Record<LoadHow, number> = { quick: 0, auto: 1, full: 2 }
/** What the quick run leaves out and the second run fetches */
// Calendar and commits take 2 s each and belong in the quick run: headline and advice then see
// the appointments even after a click. Only those that wait for a service are slow.
const SLOW_KINDS = ['tracker', 'command']

/** Requests during a load: the strongest runs afterwards (full before auto before quick). */
let reloadAfter: LoadHow | null = null

async function loadView($: EngineInterface, how: LoadHow): Promise<void> {
  if ((await read($, loading)) !== null) {
    if (reloadAfter === null || HOW_RANK[how] > HOW_RANK[reloadAfter]) reloadAfter = how
    if (how === 'full') await note($, T().alreadyLoading)
    return
  }
  // A pending "approve all?" refers to rows that are about to change.
  await update($, confirmAll, () => false)
  // Claim it immediately, before the first script runs: otherwise two loads get through.
  await update($, loading, () => T().loadTasks)
  const last = await read($, view)
  const now0 = await $.clock.now()
  const freshFor = ((await read($, config))?.fullMinutes ?? 10) * 60000
  const wantsFull = how === 'full' || (how === 'auto' && !(last?.isFull && now0 - (last.fullMs || 0) < freshFor))
  if (Object.keys(await read($, reviews)).length === 0) {
    try {
      const text = await $.fs.read(REVIEW_CACHE)
      // the last whole run carries the overview; an older cache only the verdicts
      const last = parseReviewLast(text)
      const cached = last ? last.reviews : parseReviewCache(text)
      if (Object.keys(cached).length) await update($, reviews, () => cached)
      if (last) await update($, reviewMeta, () => last.meta)
    } catch {
      // no review yet: no verdicts on the rows
    }
  }
  const taskRun = await bridge($, ['scripts/workplace.py', 'tasks', '--json'], 20000)
  let taskList: TaskInfo[] = []
  try {
    if (taskRun.ok) {
      taskList = parseTasks(taskRun.out)
      await update($, taskInfo, () => taskList)
    }
  } catch {
    // without a task list the card shows only the rows of the briefing
  }
  // The recipes hardly change: once per session (and on reload).
  if ((await read($, teamList)).length === 0 || how === 'full') {
    const teamRun = await bridge($, ['scripts/workplace.py', 'teams', '--json'], 20000)
    try {
      if (teamRun.ok) {
        const list = parseTeams(teamRun.out)
        await update($, teamList, () => list)
      }
    } catch {
      // without recipes there are no team buttons
    }
  }
  const took = await read($, loadTook)
  for (const pass of wantsFull ? (['quick', 'rest'] as const) : (['quick'] as const)) {
    const guess = took[pass] ? T().seconds(Math.round(took[pass] / 1000)) : ''
    await update($, loading, () => (pass === 'rest' ? T().loadRest(guess) : T().loadQuick(guess)))
    // The card pages by itself ("+N more"): all rows, not only those of the morning text.
    // The second run fetches everything: headline and advice need inbox and calendar together,
    // and it takes no longer than one with --only (the sections run side by side).
    const args = ['scripts/briefing.py', 'collect', '--json', '--no-save', '--max-items', '500']
    if (pass === 'quick') for (const kind of SLOW_KINDS) args.push('--skip', kind)
    // ⟳ wants the state of right now: past the cache (cache_minutes).
    if (how === 'full') args.push('--fresh')
    if (await read($, askTriage)) args.push('--style', 'triage')
    const started = await $.clock.now()
    let run = await bridge($, args, 120000)
    let raw: unknown = null
    try {
      raw = run.ok ? JSON.parse(run.out) : null
    } catch {
      // unreadable output is reported below
    }
    // Without a view the card would show the tasks and nothing else: ask once more for the triage view.
    if (run.ok && raw !== null && typeof raw === 'object' && !('view' in raw) && !(await read($, askTriage))) {
      await update($, askTriage, () => true)
      run = await bridge($, [...args, '--style', 'triage'], 120000)
    }
    const ended = await $.clock.now()
    await update($, loadTook, t => ({ ...t, [pass]: ended - started }))
    if (!run.ok) {
      await note($, T().loadFailed(short(run.err, 120)))
      break
    }
    try {
      const fresh = parseView(JSON.parse(run.out), pass === 'rest', ended)
      // What this run left out stays at the state of the previous one. Add the tasks only afterwards:
      // otherwise a task whose inbox row comes from the previous run would appear twice.
      const before = await read($, view)
      const merged = withTasks(before ? mergeView(before, fresh) : fresh, taskList)
      await update($, view, () => merged)
      // Completed items stay gone while they are still in the list (a yes only runs at the next pass).
      const present = new Set(merged.buckets.flatMap(b => b.rows.map(r => r.key)))
      await update($, settled, list => list.filter(k => present.has(k)))
      await $.store.set(STORE_VIEW, merged)
    } catch (error) {
      await note($, T().viewUnreadable(short(String(error), 120)))
      break
    }
  }
  await update($, loading, () => null)
  if (reloadAfter) {
    const next = reloadAfter
    reloadAfter = null
    startLoad($, next)
  }
}


function startLoad($: EngineInterface, how: LoadHow): void {
  // A timer outlives the dispatch that sets it: loading blocks no click.
  $.clock.after(0, () => {
    void loadView($, how)
  })
}

/** The tab state that the control workspace files for the other sessions */
const SHARED_TABS = '.bridge/briefing-ui/tabs.json'
/** Whether a query is running: a hanging one must not pile up */
let tabsBusy = false


/**
 * Fetch the tab state. Only the control workspace (the session in the workspace from workplace.control) queries
 * cmux, reports via toast and files the state for the other sessions; every other session only reads
 * it. If it is older than three beats (no control workspace open), it queries by itself, but stays quiet.
 */
async function loadTabs($: EngineInterface, cfg: UiConfig): Promise<void> {
  if (tabsBusy) return
  tabsBusy = true
  try {
    await loadTabsOnce($, cfg)
  } finally {
    tabsBusy = false
  }
}

/** The tab state that the control workspace has filed; null if there is none or it is too old. */
async function sharedTabs($: EngineInterface, cfg: UiConfig, now0: number): Promise<Record<string, unknown>[] | null> {
  try {
    const shared = JSON.parse(await $.fs.read(SHARED_TABS)) as { at: number; tabs: Record<string, unknown>[] }
    if (now0 - shared.at < cfg.statusSeconds * 3000) {
      await update($, tabsError, () => null)
      return shared.tabs
    }
  } catch {
    // no or broken filing: query by itself
  }
  return null
}

/** Query cmux by itself; null on an error (the reason then shows in red on the card). */
async function askTabs($: EngineInterface, now0: number): Promise<Record<string, unknown>[] | null> {
  const run = await bridge($, ['scripts/workplace.py', 'status', '--json'], 20000)
  try {
    if (!run.ok) throw new Error(run.err || T().statusFailed)
    const raw = JSON.parse(run.out) as Record<string, unknown>[]
    await update($, tabsError, () => null)
    return raw
  } catch (error) {
    const was = await read($, tabsError)
    const why = short(String(error).replace(/^Error: /, '').split('\n').pop() ?? '', 80)
    if (!was) await update($, tabsError, () => T().tabsStale(clockTime(now0), why))
    return null
  }
}


async function loadTabsOnce($: EngineInterface, cfg: UiConfig): Promise<void> {
  const now0 = await $.clock.now()
  const role = await read($, isControl)
  const raw = (role === false ? await sharedTabs($, cfg, now0) : null) ?? await askTabs($, now0)
  if (raw === null) return
  // Who am I: my own tab, by the identifier that cmux gives every session.
  const own = await $.env.get('CMUX_SURFACE_ID')
  const isSelf = (t: Record<string, unknown>) => t.is_self === true || (!!own && t.id === own)
  const self = raw.find(isSelf)
  // Control is the first Claude session in the control workspace: two sessions there do not report twice.
  const first = raw.filter(t => cfg.control && asText(t.workspace) === cfg.control && (asText(t.state) !== 'shell' || isSelf(t)))
    .sort((a, b) => refNumber(a.ref) - refNumber(b.ref))[0]
  const amControl = cfg.control && self ? first !== undefined && asText(first.ref) === asText(self.ref) : null
  if (amControl !== role) await update($, isControl, () => amControl)
  // My own tab (the session in which the dashboard runs) never waits for itself.
  const list = raw.filter(t => !isSelf(t)).map(toTab)
  if (amControl === true) {
    // For the other sessions, with my own tab: each one strikes its own when reading.
    try {
      await $.fs.write(SHARED_TABS, JSON.stringify({ at: now0, tabs: raw.map(t => ({ ...t, is_self: false })) }))
    } catch {
      // without a filing the others query by themselves
    }
  }
  const isQuiet = amControl === false
  const before = await read($, tabs)
  const known = new Map(before.map(t => [t.ref, t.state]))
  const woke = list.filter(t => ATTENTION.has(t.state) && known.has(t.ref) && !ATTENTION.has(known.get(t.ref) ?? ''))
  // Write only what has changed: every write redraws card and band.
  if (JSON.stringify(before) !== JSON.stringify(list)) await update($, tabs, () => list)
  for (const t of isQuiet ? [] : woke) {
    $.ui.toast(T().tabToast(short(t.name, 40), stateWord(t.state)))
    if (cfg.voice) void $.audio.speak(T().voiceWaiting(short(t.name, 40)))
  }
  // Since when each tab has been in its state; whoever waits or runs for long is reported once.
  const now = await $.clock.now()
  const old = await read($, tabSeen)
  const seen: Record<string, TabSeen> = {}
  for (const t of list) {
    const prev = old[t.ref]
    seen[t.ref] = prev && prev.state === t.state ? prev : { state: t.state, since: now, isWarned: false }
  }
  for (const t of list) {
    const text = longText(t, seen, now)
    const entry = seen[t.ref]
    if (text && entry && !entry.isWarned) {
      seen[t.ref] = { ...entry, isWarned: true }
      if (!isQuiet) $.ui.toast(T().tabToast(short(t.name, 40), text))
    }
  }
  if (JSON.stringify(old) !== JSON.stringify(seen)) await update($, tabSeen, () => seen)
}

/**
 * Save the cmux layout (workspaces, tabs, Claude sessions) with the building block of the cmux skill.
 * It writes only when the structure changed and clears old saves; without CMUX_LAYOUT_NOTIFY
 * there is no alarm.
 */
async function snapshot($: EngineInterface, isManual: boolean): Promise<void> {
  const run = await bridge($, ['skills/cmux/scripts/cmux_layout.py', 'snapshot'], 180000)
  const at = clockTime(await $.clock.now())
  if (run.ok) await update($, lastSnapshot, () => at)
  if (isManual || !run.ok) {
    await note($, run.ok ? T().saved : T().saveFailed(short(run.err, 100)))
  }
  if ((await read($, snapshots)) !== null) await listSnapshots($)
}

async function listSnapshots($: EngineInterface): Promise<void> {
  const run = await bridge($, ['skills/cmux/scripts/cmux_layout.py', 'list'], 20000)
  const lines = run.ok ? run.out.split('\n').filter(l => l.trim()).slice(0, 6) : [T().listUnreadable(short(run.err, 80))]
  await update($, snapshots, () => lines)
}

async function settle($: EngineInterface, row: Row, text: string): Promise<void> {
  await update($, settled, list => (list.includes(row.key) ? list : [...list, row.key]))
  await update($, selected, list => list.filter(k => k !== row.key))
  await update($, expanded, cur => (cur === row.key ? null : cur))
  await note($, `${text}: ${short(row.title, 60)}`)
}

async function approve($: EngineInterface, row: Row): Promise<string> {
  if (!row.inboxId) return T().noInbox
  const yes = await bridge($, ['scripts/inbox.py', 'approve', row.inboxId])
  if (!yes.ok) {
    await note($, T().approveFailed(short(yes.err, 100)))
    return T().resFailed
  }
  // It runs on the machine that is the inbox runner (inbox.runner), at the next pass;
  // an `inbox.py run` from here would run all approved entries, and on another machine not at all.
  await settle($, row, T().approvedNote)
  return T().resDo
}

async function defer($: EngineInterface, row: Row, date?: string): Promise<string> {
  if (!row.inboxId) return T().noInbox
  const until = date ?? isoDate((await $.clock.now()) + DAY)
  const run = await bridge($, ['scripts/inbox.py', 'defer', row.inboxId, '--until', until])
  if (!run.ok) {
    await note($, T().laterFailed(short(run.err, 100)))
    return T().resFailed
  }
  await settle($, row, T().laterBack(until))
  return T().resLater
}

/** Hide on the card only, until the date; nothing changes on the task. */
async function hideUntil($: EngineInterface, row: Row, until: string): Promise<string> {
  const next = { ...(await read($, hidden)), [row.key]: until }
  await update($, hidden, () => next)
  await $.store.set(STORE_HIDDEN, next)
  await update($, expanded, cur => (cur === row.key ? null : cur))
  await update($, selected, list => list.filter(k => k !== row.key))
  await note($, T().hiddenNote(until, short(row.title, 60)))
  return T().resHidden
}

async function unhide($: EngineInterface, row: Row): Promise<void> {
  const next = { ...(await read($, hidden)) }
  delete next[row.key]
  await update($, hidden, () => next)
  await $.store.set(STORE_HIDDEN, next)
}

/** Later for inbox entries (really postponed), hide for everything else. */
async function later($: EngineInterface, row: Row, until: string): Promise<string> {
  return row.inboxId && row.gate !== 'free' ? defer($, row, until) : hideUntil($, row, until)
}

async function setUrgency($: EngineInterface, row: Row, urgency: string): Promise<void> {
  if (!row.inboxId) return
  const run = await bridge($, ['scripts/inbox.py', 'urgency', row.inboxId, urgency])
  await note($, run.ok ? T().urgencySet(T().urgency[urgency] ?? urgency, short(row.title, 60))
    : T().urgencyFailed(short(run.err, 100)))
  if (run.ok) startLoad($, 'quick')
}

async function setPriority($: EngineInterface, row: Row, priority: string): Promise<void> {
  if (!row.task) return
  const run = await bridge($, ['scripts/task.py', 'priority', row.task, priority])
  await note($, run.ok ? `${priority}: ${short(row.title, 60)}` : T().prioFailed(short(run.err, 100)))
  if (run.ok) startLoad($, 'quick')
}

async function drop($: EngineInterface, row: Row): Promise<string> {
  if (!row.inboxId) return hideUntil($, row, isoDate((await $.clock.now()) + 7 * DAY))
  const run = await bridge($, ['scripts/inbox.py', 'drop', row.inboxId, '--note', T().dropInboxNote])
  if (!run.ok) {
    await note($, T().dropFailed(short(run.err, 100)))
    return T().resFailed
  }
  await settle($, row, T().dropped)
  return T().resDrop
}

async function closeDone($: EngineInterface, row: Row): Promise<string> {
  if (!row.inboxId) return T().noInbox
  const run = await bridge($, ['scripts/inbox.py', 'close', row.inboxId, '--note', T().doneInboxNote])
  if (!run.ok) {
    await note($, T().doneFailed(short(run.err, 100)))
    return T().resFailed
  }
  await settle($, row, T().resDone)
  return T().resDone
}

async function launch($: EngineInterface, rows: Row[], how: Mode, where: Target,
  team?: { id: string; role: string; name: string }): Promise<string> {
  const wanted = rows.map(launchItem).filter((x): x is string => x !== null)
  if (wanted.length === 0) return T().nothingToStart
  // One start per item at a time, whichever button or shortcut asks: a second click while the first
  // is under way (or before the tab list shows the new tab) would open a second tab.
  const busy = await read($, starting)
  const items = wanted.filter(x => !busy.includes(x))
  for (const row of rows.filter(r => busy.includes(launchItem(r) ?? ''))) {
    await note($, T().startingAlready(short(row.title, 40)))
  }
  if (items.length === 0) return ''
  await update($, starting, list => [...new Set([...list, ...items])])
  const release = () => update($, starting, list => list.filter(x => !items.includes(x)))
  const here = (await $.env.get('CMUX_SURFACE_ID')) ?? ''
  const args = ['scripts/workplace.py', 'launch', '--items', items.join(','), '--mode', how, '--target', where,
    '--yes', '--json']
  if (here) args.push('--here', here)
  if (team) args.push('--team', team.id, '--role', team.role)
  const word = team ? T().launchTeam(team.name) : how === 'go' ? T().btnDo : how === 'context' ? T().launchContext : T().btnAdvise
  // into an area: name it, when the started rows share one
  const areas = [...new Set(rows.filter(r => items.includes(launchItem(r) ?? '')).map(r => r.area).filter(Boolean))]
  const whereText = where === 'area' && areas.length === 1 ? T().whereArea(areas[0]!) : T().where[where]
  await note($, T().launchStart(word, items.length, whereText))
  const run = await bridge($, args, LAUNCH_TIMEOUT_MS)
  let report = run.err
  // Part of it may have started even if the run fails as a whole: the started ones
  // count as done, otherwise a second click starts them twice.
  let started: string[] = []
  let running: { label: string; ref: string }[] = []
  let anySkipped = false
  try {
    const data = JSON.parse(run.out) as {
      report?: string[]
      items?: { item?: string; error?: string; label?: string; workspace?: string; own?: boolean; why?: string
        skipped?: string; ref?: string }[]
    }
    const lines = data.report ?? []
    // the skip lines (English, from workplace.py) get a note of their own below
    const fresh = lines.filter(line => !line.startsWith('already open:'))
    report = fresh.join(' · ') || (lines.length ? '' : report)
    // For auto: where each item went and why, instead of the raw driver lines
    if (where === 'auto') {
      const placed = (data.items ?? []).filter(i => i.label && !i.error && !i.skipped)
        .map(i => `${short(i.label ?? '', 30)} → ${i.own ? T().ownWs : i.workspace ?? '?'}${i.why ? ` (${i.why})` : ''}`)
      if (placed.length) report = placed.join(' · ')
    }
    const hasErrorLine = lines.some(line => line.startsWith('ERROR'))
    if (!hasErrorLine && lines.length > 0) {
      // a skipped item (its agent runs already) did not start here
      started = (data.items ?? []).filter(i => i.item && !i.error && !i.skipped).map(i => asText(i.item))
    }
    // An agent already works on it (workplace.py never opens a second one): go there instead.
    anySkipped = (data.items ?? []).some(i => i.skipped)
    running = (data.items ?? []).filter(i => i.skipped === 'open' && i.ref)
      .map(i => ({ label: asText(i.label ?? i.item), ref: asText(i.ref) }))
  } catch {
    // no JSON answer: stderr is already in report
  }
  const launched = rows.filter(r => started.some(id => id === r.task || id === r.inboxId))
  // Every item had its agent running already: nothing started, the jump below is the answer.
  const onlyRunning = run.ok && anySkipped && launched.length === 0
  const outcome = run.ok ? T().resStarted : launched.length ? T().partlyStarted(launched.length) : T().startFailed
  if (!onlyRunning) await note($, `${outcome} (${word}): ${short(report, 160)}`)
  const cfg = await read($, config)
  if (running.length && cfg) {
    await loadTabs($, cfg)
    const tab = (await read($, tabs)).find(t => t.ref === running[0]!.ref)
    if (tab) await jump($, tab)
    await note($, T().alreadyOpen(short(running[0]!.label, 40)))
  }
  if (launched.length) {
    await update($, selected, list => list.filter(k => !launched.some(r => r.key === k)))
    if (cfg) $.clock.after(5000, () => void loadTabs($, cfg))
  }
  // A start that ran holds its items until the new tab shows up in the list (loadTabs 5 s after it);
  // a failed one frees them at once for another try.
  if (!onlyRunning && (run.ok || launched.length)) $.clock.after(START_HOLD_MS, () => void release())
  else await release()
  if (onlyRunning) return ''
  return run.ok ? T().resStarted : launched.length ? T().resPartly : T().resFailed
}

/**
 * Start a role: the next one of the chosen team, or the first of another (switch).
 * It is remembered before the start, so a second click does not open the same role again.
 */
async function startRole($: EngineInterface, row: Row, team: Team): Promise<string> {
  if (!row.task) return T().noTask
  const now = await $.clock.now()
  const runs = await read($, teamOf)
  const st = teamState(row, runs, await read($, teamList), await read($, tabs), now)
  const isSame = st !== null && st.team.id === team.id
  if (isSame && !st.isReady) return T().waitsForRole(st.waitingFor ?? T().prevRole)
  const role = isSame ? st.next : team.roles[0]
  if (!role) return T().allRolesStarted
  const item = launchItem(row)
  if (item && (await read($, starting)).includes(item)) {
    // a start of this task is under way: launch would start nothing, so nothing is recorded
    await note($, T().startingAlready(short(row.title, 40)))
    return ''
  }
  const before = runs[row.task]
  const run: TeamRun = { team: team.id, roles: isSame && before ? [...before.roles, role.id] : [role.id], at: now }
  const save = async (next: Record<string, TeamRun>) => {
    await update($, teamOf, () => next)
    await $.store.set(STORE_TEAMS, next)
  }
  await save({ ...runs, [row.task]: run })
  const cfg = await read($, config)
  const result = await launch($, [row], role.mode, cfg?.target ?? 'area', { id: team.id, role: role.id, name: role.name })
  if (result === T().resFailed) {
    const rest = { ...(await read($, teamOf)) }
    if (before) rest[row.task] = before
    else delete rest[row.task]
    await save(rest)
  }
  return result
}

/** Assign a running tab to a task: it is named after the task afterwards, the card finds it. */
async function adopt($: EngineInterface, row: Row, tab: Tab): Promise<void> {
  if (!row.task) return
  const run = await bridge($, ['scripts/workplace.py', 'adopt', tab.ref, row.task])
  await note($, run.ok ? T().adopted(short(tab.name, 30), short(row.title, 40))
    : T().adoptFailed(short(run.err, 100)))
  const cfg = await read($, config)
  if (run.ok && cfg) await loadTabs($, cfg)
}

/** A note on a task or entry: the context that only you know. */
async function addNote($: EngineInterface, row: Row, text: string): Promise<void> {
  const line = text.trim()
  if (!line) return
  const run = row.task
    ? await bridge($, ['scripts/task.py', 'note', row.task, '--', line])
    : row.inboxId ? await bridge($, ['scripts/inbox.py', 'note', row.inboxId, '--', line]) : null
  if (!run) {
    await note($, T().noteOnly)
    return
  }
  await note($, run.ok ? T().noteAdded(short(row.title, 40), short(line, 60)) : T().noteFailed(short(run.err, 100)))
}

/** Check all open tasks, or the named ones: one recommendation each, with what it cost. Changes no task. */
async function reviewTasks($: EngineInterface, slugs: string[] | null, escalate = false): Promise<void> {
  if ((await read($, reviewing)) !== null) {
    await note($, T().reviewBusy)
    return
  }
  await update($, reviewing, () => (slugs ? slugs.join(',') : 'all'))
  try {
    const args = ['scripts/task.py', 'review', ...(escalate ? ['--escalate'] : []), ...(slugs ?? ['--all']), '--json']
    const run = await bridge($, args, REVIEW_TIMEOUT_MS)
    if (!run.ok) throw new Error(run.err || 'task.py review failed')
    const got = parseReview(run.out)
    await update($, reviews, cur => ({ ...cur, ...got.reviews }))
    // a whole run is the overview's new strip; a check of a few tasks only changes their rows
    if (!slugs) await update($, reviewMeta, () => got.meta)
    const odd = got.mismatch.length ? ` · ${T().modelMismatch(got.mismatch.join('; '))}` : ''
    await note($, `${T().reviewDone(got.count, got.toClose, got.costUsd, got.costKnown)}${odd}`)
  } catch (error) {
    await note($, T().reviewFailed(short(String(error).replace(/^Error: /, ''), 120)))
  } finally {
    await update($, reviewing, () => null)
  }
}

/** Keep: the recommendation stays away until the task's evidence changes (stored by task.py). */
async function keepTask($: EngineInterface, slug: string): Promise<void> {
  const run = await bridge($, ['scripts/task.py', 'review', '--keep', slug, '--json'])
  if (!run.ok) {
    await note($, T().keepFailed(short(run.err, 100)))
    return
  }
  await update($, reviews, cur => (cur[slug] ? { ...cur, [slug]: { ...cur[slug]!, kept: true } } : cur))
  await note($, T().kept(slug))
}

/**
 * Close a finished task: the first click asks (the button turns into "really close?"), a second
 * one within a few seconds runs the 3-step close of task.py and takes the row off the card.
 */
async function closeTask($: EngineInterface, slug: string, declined = false): Promise<void> {
  const now = await $.clock.now()
  const pending = await read($, confirmClose)
  if (!pending || pending.slug !== slug || now - pending.at > CONFIRM_MS) {
    await update($, confirmClose, () => ({ slug, at: now }))
    $.clock.after(CONFIRM_MS, () => {
      void update($, confirmClose, cur => (cur && cur.slug === slug && cur.at === now ? null : cur))
    })
    return
  }
  await update($, confirmClose, () => null)
  if (await closeNow($, slug, declined)) {
    await note($, T().taskClosed(slug))
    startLoad($, 'quick')
  }
}

/** The recommendation's reason says why it is finished; a close without one says where it came from. */
function closeReason(rv: Review | undefined): string {
  const v = rv ? effectiveVerdict(rv) : null
  return rv && (v === 'close' || v === 'stale') && rv.reason ? rv.reason : T().closedFromDashboard
}

/** One task.py close, no questions asked (the caller asked); the row leaves the card. */
async function closeNow($: EngineInterface, slug: string, declined: boolean): Promise<boolean> {
  const reason = closeReason((await read($, reviews))[slug])
  // Close on a stale verdict means dropped, not finished: outcome declined
  const run = await bridge($, ['scripts/task.py', 'close', slug, '--reason', reason, ...(declined ? ['--declined'] : []),
    '--json'])
  if (!run.ok) {
    await note($, T().closeTaskFailed(short(run.err, 100)))
    return false
  }
  await update($, closedTasks, list => (list.includes(slug) ? list : [...list, slug]))
  await update($, reviews, cur => {
    const next = { ...cur }
    delete next[slug]
    return next
  })
  await update($, taskInfo, list => list.filter(t => t.slug !== slug))
  await update($, expanded, () => null)
  await update($, ovPicked, list => list.filter(x => x !== slug))
  return true
}

/** The overview's bulk close: the first click asks for all of them at once, the second closes each in turn. */
async function bulkClose($: EngineInterface, list: Review[]): Promise<void> {
  const now = await $.clock.now()
  const pending = await read($, ovConfirm)
  if (!pending || pending.n !== list.length || now - pending.at > CONFIRM_MS) {
    await update($, ovConfirm, () => ({ at: now, n: list.length }))
    $.clock.after(CONFIRM_MS, () => {
      void update($, ovConfirm, cur => (cur && cur.at === now ? null : cur))
    })
    return
  }
  await update($, ovConfirm, () => null)
  let done = 0
  for (const rv of list) if (await closeNow($, rv.slug, effectiveVerdict(rv) === 'stale')) done += 1
  await note($, T().ovClosedSome(done, list.length - done))
  startLoad($, 'quick')
}

/** Keep for several at once: one task.py call. */
async function bulkKeep($: EngineInterface, slugs: string[]): Promise<void> {
  const run = await bridge($, ['scripts/task.py', 'review', '--keep', ...slugs, '--json'])
  if (!run.ok) {
    await note($, T().keepFailed(short(run.err, 100)))
    return
  }
  await update($, reviews, cur => {
    const next = { ...cur }
    for (const s of slugs) if (next[s]) next[s] = { ...next[s]!, kept: true }
    return next
  })
  await update($, ovPicked, () => [])
  await note($, T().kept(slugs.join(', ')))
}

/** Do it yourself: have it run with a yes where the inbox can, otherwise have a tab work it off. */
async function doIt($: EngineInterface, rows: Row[], where?: Target): Promise<string> {
  const cfg = await read($, config)
  // A yes only runs what an action carries; a tab handles everything else.
  const open = rows.filter(r => r.inboxState !== 'approved')
  const yes = open.filter(r => r.inboxId && r.gate === 'your-yes' && r.hasAction)
  const rest = open.filter(r => !yes.includes(r) && launchItem(r) !== null)
  const said: string[] = []
  for (const row of yes) said.push(await approve($, row))
  if (rest.length) said.push(await launch($, rest, 'go', where ?? cfg?.target ?? 'area'))
  return said.join(', ') || T().nothingToDo
}

/** Advise me: a tab reads the context and proposes; without a startable item the chat asks. */
async function advise($: EngineInterface, rows: Row[]): Promise<string> {
  const cfg = await read($, config)
  const startable = rows.filter(r => launchItem(r) !== null)
  if (startable.length) return launch($, startable, 'report', cfg?.target ?? 'area')
  if (rows[0]) await ask($, askAbout(rows[0]))
  return T().resAsked
}

async function jump($: EngineInterface, tab: Tab): Promise<void> {
  const cmux = (await $.env.get('CMUX_BUNDLED_CLI_PATH')) ?? 'cmux'
  try {
    const ws = await $.process.run([cmux, 'select-workspace', '--workspace', tab.wsRef], { timeoutMs: 10000 })
    const panel = await $.process.run([cmux, 'focus-panel', '--panel', tab.ref, '--workspace', tab.wsRef],
      { timeoutMs: 10000 })
    const failed = [ws, panel].find(r => r.exitCode !== 0)
    if (failed) await note($, T().jumpFailed(short(failed.stderr.trim() || failed.stdout.trim(), 100)))
  } catch (error) {
    await note($, T().jumpFailed(short(String(error), 100)))
  }
}

/** A key to the tab: the answer to a permission prompt (1 = yes, escape = no) */
async function pressKey($: EngineInterface, tab: Tab, key: string, said: string): Promise<void> {
  if (!tab.ref) return
  // The state on the card may be seconds old: if the tab has moved on in the meantime,
  // Esc would abort its work and the 1 would land in the prompt.
  const now = (await askTabs($, await $.clock.now()))?.find(t => asText(t.ref) === tab.ref)
  if (!now || asText(now.state) !== 'needs-you') {
    await note($, T().notAsking(short(tab.name, 30)))
    const cfg = await read($, config)
    if (cfg) void loadTabs($, cfg)
    return
  }
  const cmux = (await $.env.get('CMUX_BUNDLED_CLI_PATH')) ?? 'cmux'
  try {
    const run = await $.process.run([cmux, 'send-key', '--workspace', tab.wsRef, '--surface', tab.ref, key],
      { timeoutMs: 10000 })
    await note($, run.exitCode === 0 ? `${short(tab.name, 30)}: ${said}` : T().keyFailed(short(run.stderr.trim(), 100)))
  } catch (error) {
    await note($, T().keyFailed(short(String(error), 100)))
  }
  const cfg = await read($, config)
  if (cfg) $.clock.after(3000, () => void loadTabs($, cfg))
}

/** Close a finished tab, on click only. Without a target cmux would close its own tab: then do nothing. */
async function closeTab($: EngineInterface, tab: Tab): Promise<void> {
  if (!tab.ref || !tab.wsRef) return
  const cmux = (await $.env.get('CMUX_BUNDLED_CLI_PATH')) ?? 'cmux'
  try {
    const run = await $.process.run([cmux, 'close-surface', '--surface', tab.ref, '--workspace', tab.wsRef],
      { timeoutMs: 10000 })
    await note($, run.exitCode === 0 ? T().tabClosed(short(tab.name, 30)) : T().closeFailed(short(run.stderr.trim(), 100)))
  } catch (error) {
    await note($, T().closeFailed(short(String(error), 100)))
  }
  const cfg = await read($, config)
  if (cfg) $.clock.after(1000, () => void loadTabs($, cfg))
}

async function send($: EngineInterface, tab: Tab, text: string): Promise<void> {
  const run = await bridge($, ['scripts/workplace.py', 'send', tab.ref, '--', text])
  await note($, run.ok ? T().sentTo(short(tab.name, 30), short(text, 60)) : T().sendFailed(short(run.err, 100)))
  await update($, messageTo, () => null)
}

async function openPane($: EngineInterface): Promise<void> {
  await $.ui.open({ id: PANE, title: T().briefing, focus: true, closeOnEscape: true, columns: 60, rows: 40 })
}

async function ask($: EngineInterface, text: string): Promise<void> {
  await $.prompt.submit({ text })
}


/** The buttons of a row, brief; the rest hides behind ▾. */
type Action = { id: string; label: string; primary?: boolean; tone?: string; run: () => unknown }

function rowActions($: EngineInterface, row: Row, tab: Tab | undefined): Action[] {
  const out: Action[] = []
  if (tab && !isLive(tab) && launchItem(row) !== null && row.inboxState !== 'approved') {
    // The tab holds no agent (its command never ran, or the agent ended): start it again, or look.
    out.push({ id: 'restart', label: T().btnRestart, primary: true, run: () => doIt($, [row]) })
    out.push({ id: 'hin', label: T().btnToTab, run: () => jump($, tab) })
    return out
  }
  if (tab) {
    out.push({ id: 'hin', label: T().btnToTab, primary: true, run: () => jump($, tab) })
    return out
  }
  if (row.inboxId && row.inboxState === 'approved') {
    out.push({ id: 'ready', label: T().btnApproved, tone: 'green',
      run: () => note($, T().approvedPending(short(row.title, 60))) })
    out.push({ id: 'drop', label: T().btnDrop, tone: RED, run: () => drop($, row) })
    return out
  }
  if (row.bucket === 'waiting') {
    out.push({ id: 'nudge', label: T().btnNudge, run: () => ask($, followUp(row)) })
    return out
  }
  if (row.inboxId && row.gate === 'only-you') {
    out.push({ id: 'done', label: T().btnDone, primary: true, run: () => closeDone($, row) })
    out.push({ id: 'advise', label: T().btnAdvise, run: () => advise($, [row]) })
    return out
  }
  if (launchItem(row) !== null) {
    out.push({ id: 'do', label: T().btnDo, primary: true, run: () => doIt($, [row]) })
    if (row.inboxId) out.push({ id: 'drop', label: T().btnDrop, tone: RED, run: () => drop($, row) })
    else out.push({ id: 'advise', label: T().btnAdvise, run: () => advise($, [row]) })
    return out
  }
  out.push({ id: 'ask', label: T().btnAskClaude, run: () => ask($, askAbout(row)) })
  return out
}

/** The dashboard: in the chat as a card (inChat) or as a panel, the same tree. */
async function dashboard($: EngineInterface, e: ResolveInput, columns: number, inChat: boolean, height = 40) {
  const table = $.ui.resolve(e)
  const { Box, Text, Link } = table
  const Button = framed(table.Button, Text)
  // "release all": only entries whose yes executes an action, no tab, none with a yes already given.
  const approvable = (rows: Row[]) => rows.filter(r => r.inboxId && r.gate === 'your-yes' && r.hasAction
    && r.inboxState !== 'approved' && !tabFor(r, tabList))
  // Mark from view.marks (customer, project) before the title; if the area already stands before it, not twice.
  const markText = (mark: Mark | null, area: string | null) =>
    mark && mark.label.toLowerCase() !== (area ?? '').toLowerCase()
      ? <Text color={mark.color ?? 'magenta'}>{`${mark.label} `}</Text> : null
  // An input field does not exist on every surface (not on mobile).
  const Input = 'Input' in table ? table.Input : null
  // The verdict of the last review as a short tag behind a task's title; continue and kept ones say nothing.
  const tagOf = (slug: string | null) => {
    const rv = slug ? rvs[slug] : undefined
    // a resolved signal says close whatever the model answered; a low confidence adds a question mark
    const verdict = rv?.resolved ? 'close' : rv?.verdict
    const tag = rv && !rv.kept && verdict ? T().verdictTag[verdict] : undefined
    const unsure = rv?.confidence === 'low' && !rv.resolved ? '?' : ''
    return tag ? <Text color={verdict === 'close' ? 'green' : 'yellow'}>{`  ${tag}${unsure}`}</Text> : null
  }
  const reviewButton = (key: string) => (reviewNow !== null
    ? <Text dimColor>{`${T().reviewing} `}</Text>
    : <Button key={key} label={T().btnReviewAll} onPress={() => reviewTasks($, null)} />)
  // The review overview: a strip with the verdicts as a bar, filter chips, comparable rows, and bulk actions.
  const overviewBox = (isWide: boolean) => {
    const counts = ovCounts(ovList)
    const rows = ovSort(ovFilter(ovList, ovF), ovS)
    const picked = ovSort(ovList.filter(r => picks.includes(r.slug)), ovS)
    const infoOf = (slug: string) => taskList.find(t => t.slug === slug)
    const barWidth = isWide ? 30 : 12
    const label = (v: string) => T().ovVerdict[v] ?? v
    const strip = meta ? T().ovStrip(meta.count, T().ovCost(meta.costUsd, meta.costKnown),
      meta.models.map(modelShort).join(', ') || '?', Math.round(meta.durationSec ?? 0), minutesSince(meta.at, now)) : ''
    const chipIds: OvFilter[] = ['all', ...STRIP_ORDER, 'changed']
    const chipName = (id: OvFilter) => (id === 'all' ? T().ovAll : id === 'changed' ? T().ovChanged : label(id))
    const tabbable = picked.filter(r => ['continue', 'stale'].includes(effectiveVerdict(r)))
    const row = (r: Review) => {
      const v = effectiveVerdict(r)
      const info = infoOf(r.slug)
      const prio = r.priority ?? info?.priority ?? null
      const isPicked = picks.includes(r.slug)
      const isOpen = ovOpened === r.slug
      const chips = r.chips.map(c => T().chip(c)).join(' · ')
      return (
        <Box key={`ov-row-${r.slug}`} flexDirection="column">
          <Box>
            <Box width={4} flexShrink={0}>
              <Button key={`ov-pick-${r.slug}`} label={isPicked ? '[x]' : '[ ]'}
 onPress={() => update($, ovPicked, l => (l.includes(r.slug) ? l.filter(x => x !== r.slug) : [...l, r.slug]))} />
            </Box>
            <Box width={3} flexShrink={0}>
              {prio && <Text color={PRIO_COLOR[prio] ?? 'cyan'}>{prio}</Text>}
            </Box>
            {isWide && (
              <Box width={10} flexShrink={0}><Text dimColor wrap="truncate-end">{info?.area ?? ''}</Text></Box>
            )}
            <Box width={isWide ? 28 : undefined} flexGrow={isWide ? 0 : 1} flexShrink={isWide ? 0 : 1}>
              <Text wrap="truncate-end">{r.title || info?.label || r.slug}</Text>
            </Box>
            <Box key={`ov-tag-${r.slug}`} width={12} flexShrink={0} marginLeft={1}>
              <Text color={VERDICT_COLOR[v]}>{label(v)}</Text>
              {r.changed && <Text dimColor>*</Text>}
            </Box>
            {isWide && <Box key={`ov-conf-${r.slug}`} width={4} flexShrink={0}><Text dimColor>{confDots(r.confidence)}</Text></Box>}
            {isWide && (
              <Box key={`ov-days-${r.slug}`} width={6} flexShrink={0}>
                <Text dimColor>{r.days === null ? '?' : T().ovDays(r.days)}</Text>
              </Box>
            )}
            {isWide && (
              <Box key={`ov-chips-${r.slug}`} width={34} flexShrink={0}><Text dimColor wrap="truncate-end">{chips}</Text></Box>
            )}
            {isWide && <Box flexGrow={1} width={0}><Text wrap="truncate-end">{r.reason}</Text></Box>}
            <Box flexShrink={0} marginLeft={1}>
              <Button key={`ov-x-${r.slug}`} label={T().btnDetails(isOpen)}
 onPress={() => update($, ovOpen, cur => (cur === r.slug ? null : r.slug))} />
            </Box>
          </Box>
          {isOpen && (
            <Box flexDirection="column" marginLeft={4} paddingX={1} borderStyle="round" borderDimColor>
              {!isWide && chips && <Text dimColor wrap="wrap">{chips}</Text>}
              {reviewBox(taskRowFor(r.slug, r.title, taskList))}
            </Box>
          )}
        </Box>
      )
    }
    const groups = ovS === 'verdict'
      ? VERDICT_ORDER.map(v => ({ v, list: rows.filter(r => effectiveVerdict(r) === v) })).filter(g => g.list.length)
      : [{ v: null, list: rows }]
    return (
      <Box key="overview" flexDirection="column" marginTop={1} borderStyle="round" borderDimColor paddingX={1}>
        <Box flexWrap="wrap">
          {barParts(counts, barWidth, STRIP_ORDER).map(p => (
            <Text key={`ov-bar-${p.verdict}`} color={VERDICT_COLOR[p.verdict]}>{'█'.repeat(p.cells)}</Text>
          ))}
          <Text>{' '}</Text>
          <Text>{STRIP_ORDER.filter(v => counts[v] > 0).map(v => `${counts[v]} ${label(v)}`).join(' · ')}</Text>
        </Box>
        {strip && <Text dimColor wrap="wrap">{strip}</Text>}
        <Box flexWrap="wrap">
          {chipIds.map(id => (
            <Button key={`ov-f-${id}`} variant={ovF === id ? 'primary' : undefined} tone={counts[id] ? VERDICT_COLOR[id] ?? 'cyan' : 'cyan'}
 label={`${chipName(id)} ${counts[id]}`} onPress={() => update($, ovFilterAtom, () => id)} />
          ))}
        </Box>
        <Box flexWrap="wrap">
          <Text dimColor>{T().ovSortPrefix}</Text>
          {(['verdict', 'priority', 'activity'] as const).map(id => (
            <Button key={`ov-s-${id}`} selected={ovS === id} label={T().ovSortLabel[id]}
 onPress={() => update($, ovSortAtom, () => id)} />
          ))}
          <Text>{'  '}</Text>
          <Button key="ov-all" label={T().ovSelectAll}
 onPress={() => update($, ovPicked, l => [...new Set([...l, ...rows.map(r => r.slug)])])} />
        </Box>
        {picked.length > 0 && (
          <Box flexWrap="wrap">
            <Button key="ov-close" variant="primary"
 label={ovSure && ovSure.n === picked.length ? T().ovBulkSure(picked.length) : T().ovBulkClose(picked.length)}
 onPress={() => bulkClose($, picked)}  tone={RED} />
            <Button key="ov-keep" label={T().ovBulkKeep(picked.length)}
 onPress={() => bulkKeep($, picked.map(r => r.slug))} />
            {reviewNow === null && (
              <Button key="ov-esc" label={T().ovBulkEscalate(picked.length, T().ovCost(meta?.escalateUsd ?? 0.021, true))}
 onPress={() => reviewTasks($, picked.map(r => r.slug), true)} />
            )}
            {tabbable.length > 0 && (
              <Button key="ov-tab" label={T().ovBulkTab(tabbable.length)} onPress={act($, async () =>
 launch($, tabbable.map(r => taskRowFor(r.slug, r.title, taskList)), 'go',
 (await read($, config))?.target ?? 'area'))} />
            )}
          </Box>
        )}
        {rows.length === 0 && <Text dimColor>{T().ovEmpty}</Text>}
        {groups.map(g => (
          <Box key={`ov-g-${g.v ?? 'all'}`} flexDirection="column">
            {g.v && <Text bold color={VERDICT_COLOR[g.v]}>{T().ovGroup(label(g.v), g.list.length)}</Text>}
            {g.list.map(row)}
          </Box>
        ))}
      </Box>
    )
  }
  // An opened task: the recommendation with Close/Keep, Done (asks once more) and a check of this one task.
  const reviewBox = (row: Row) => {
    const slug = row.task!
    const rv = rvs[slug]
    const shown = rv && !rv.kept ? rv : undefined
    const isClose = shown?.verdict === 'close' || shown?.resolved === true
    const isStale = !isClose && shown?.verdict === 'stale'
    // a long-runner never closes: no Done, no Close
    if (taskList.find(t => t.slug === slug)?.isStream) return null
    const sure = confirm?.slug === slug
    return (
      <Box key={`rv-${row.key}`} flexDirection="column">
        {shown && (
          <Text wrap="wrap" color={isClose ? 'green' : undefined}>{T().recommendation(modelShort(shown.model), shown.reason)}</Text>
        )}
        {shown?.resolved && shown.closedRefs.length > 0 && (
          <Text wrap="wrap" color="green">{T().signalClosed(shown.closedRefs.join(', '))}</Text>
        )}
        {shown && !shown.resolved && shown.unblocked && shown.closedRefs.length > 0 && (
          <Text wrap="wrap" dimColor>{T().signalUnblocked(shown.closedRefs.join(', '))}</Text>
        )}
        <Box flexWrap="wrap">
          {(isClose || isStale) && (
            <Button key={`rv-close-${row.key}`} variant="primary" label={sure ? T().btnReallyClose : T().btnCloseTask}
 onPress={() => closeTask($, slug, isStale)}  tone={RED} />
          )}
          {(isClose || isStale) && (
            <Button key={`rv-keep-${row.key}`} label={T().btnKeep} onPress={() => keepTask($, slug)} />
          )}
          <Button key={`done-${row.key}`} label={sure ? T().btnReallyClose : T().btnFinished} tone={RED}
 onPress={() => closeTask($, slug)} />
          {reviewNow !== null ? <Text dimColor>{` ${T().reviewing}`}</Text> : (
            <Button key={`rv-one-${row.key}`} label={T().btnCheckOne} onPress={() => reviewTasks($, [slug])} />
          )}
        </Box>
      </Box>
    )
  }
  // A task closed here leaves the card at once, before the next collect knows it.
  const closed = await read($, closedTasks)
  const isGone = (task: string | null, inboxId: string | null = null) => !!task && !inboxId && closed.includes(task)
  const rawView = await read($, view)
  const v = rawView && closed.length ? {
    ...rawView,
    buckets: rawView.buckets.map(b => ({ ...b, rows: b.rows.filter(r => !isGone(r.task, r.inboxId)) })),
    pages: rawView.pages.map(pg => ({ ...pg, sections: pg.sections.map(x => {
      const items = x.items.filter(it => !isGone(it.task))
      return { ...x, items, count: x.count - (x.items.length - items.length) }
    }) })),
  } : rawView
  const done = await read($, settled)
  const rvs = await read($, reviews)
  const reviewNow = await read($, reviewing)
  const confirm = await read($, confirmClose)
  const meta = await read($, reviewMeta)
  const showOv = await read($, showOverview)
  const ovF = await read($, ovFilterAtom)
  const ovS = await read($, ovSortAtom)
  const picks = await read($, ovPicked)
  const ovOpened = await read($, ovOpen)
  const ovSure = await read($, ovConfirm)
  // The overview compares the reviewed tasks that are still there: a closed one leaves it too.
  const ovList = Object.values(rvs).filter(r => !closed.includes(r.slug))
  const taskList = await read($, taskInfo)
  const picked = await read($, selected)
  const isConfirming = await read($, confirmAll)
  // Without cmux there are no tabs to count, steer or back up: those lines stay away.
  const inCmux = Boolean(await $.env.get('CMUX_SURFACE_ID'))
  const hasTabs = (await read($, tabs)).length > 0 || inCmux
  const open = await read($, expanded)
  const busy = await read($, loading)
  const now = await $.clock.now()
  const today = isoDate(now)
  const tabList = await read($, tabs)
  const typing = await read($, messageTo)
  const log = await read($, notes)
  const hide = await read($, hidden)
  const section = await read($, openSection)
  const all = await read($, showAll)
  const tabsOpen = await read($, showTabs)
  const help = await read($, showHelp)
  const tabErr = await read($, tabsError)
  const lang = await read($, helpLang)
  const recipes = await read($, teamList)
  const saved = await read($, lastSnapshot)
  const snapList = await read($, snapshots)
  // The layout is saved only from a session inside cmux (see session.start), as often as snapshot_minutes says.
  const every = (await read($, config))?.snapshotMinutes ?? 60
  const backupText = `${T().backup} ${saved ? T().backupAt(saved) : T().backupEvery(every)}`
  const chosen = await read($, teamOf)
  // In the chat the frame of the card subtracts, in the panel columns is already the width of the content.
  const width = inChat ? Math.max(40, columns - 6) : Math.max(24, columns - 1)
  const lay = layout(v, done, hide, today, section, all, tabList)
  const byId = Object.fromEntries(lay.sections.map(s => [s.id, s])) as Record<SectionId, Section>
  const seen = await read($, tabSeen)
  // Whoever works for long also belongs at the top: maybe it is stuck.
  const waiting = tabList.filter(t => isWaiting(t, v) || longText(t, seen, now) !== null)
  const longCount = tabList.filter(t => longText(t, seen, now) !== null).length
  const busyTabs = tabList.filter(t => t.state === 'working').length
  const pickedRows = lay.sections.flatMap(s => s.all).filter(r => picked.includes(r.key))
  const toggle = (row: Row) =>
    update($, selected, list => (list.includes(row.key) ? list.filter(k => k !== row.key) : [...list, row.key]))
  const setSection = (id: SectionId | null) => update($, openSection, cur => (cur === id ? null : id))

  // Columns of the card: selection and number, area, mark, title (fills, shortens itself), buttons flush right.
  // Below 120 columns the card tightens: narrower area, short button texts, no ✉.
  const isTight = width < 120
  const LEAD = 7
  const AREA = isTight ? 9 : 11
  const label = (a: Action) => (isTight ? T().shortLabel[a.id] ?? a.label : a.label)
  const MARK = 4
  // Per state the fitting buttons: answer a permission prompt, let it carry on, or clear it away.
  const tabButtons = (tab: Tab) => {
    const result = filedBy(tab, v)
    if (tab.state === 'needs-you') {
      return [
        <Button key={`yes-${tab.ref}`} label={T().btnYes} onPress={() => pressKey($, tab, '1', T().saidYes)} />,
        <Button key={`no-${tab.ref}`} label={T().btnNo} onPress={() => pressKey($, tab, 'escape', T().saidNo)}  tone={RED} />,
      ]
    }
    if (tab.state === 'waiting' && result) {
      return [<Button key={`close-${tab.ref}`} label={T().btnCloseTab} onPress={() => closeTab($, tab)}  tone={RED} />]
    }
    if (tab.state === 'waiting') {
      return [<Button key={`go-${tab.ref}`} label={T().btnGoOn} onPress={() => send($, tab, T().goOnMessage)} />]
    }
    return []
  }
  const tabLine = (tab: Tab) => (
    <Box key={`tab-${tab.ref}`} flexDirection="column">
      <Box>
        <Box width={LEAD} flexShrink={0} justifyContent="flex-end" paddingRight={1}>
          <Text color={tabColor(tab)}>●</Text>
        </Box>
        <Box width={AREA} flexShrink={0}><Text dimColor wrap="truncate-end">{tab.workspace}</Text></Box>
        <Box width={MARK} flexShrink={0} />
        <Box flexGrow={1} flexShrink={1}>
          <Text wrap="truncate-end">
            {tab.name}
            <Text color={longText(tab, seen, now) ? 'red' : tabColor(tab)}>
              {`  ${longText(tab, seen, now) ?? stateWord(tab.state)}`}
            </Text>
            {filedBy(tab, v) && <Text color="green">{`  ${T().resultFiled}`}</Text>}
            <Text dimColor>{tab.last ? `  ${tab.last}` : ''}</Text>
          </Text>
        </Box>
        <Box flexShrink={0} marginLeft={1}>
          <Button key={`jump-${tab.ref}`} label={T().btnToTab} variant="primary" onPress={() => jump($, tab)} />
          {tabButtons(tab)}
          {Input && !isTight && (
            <Button key={`msg-${tab.ref}`} label="✉" 
 onPress={() => update($, messageTo, cur => (cur === tab.ref ? null : tab.ref))} />
          )}
        </Box>
      </Box>
      {Input && typing === tab.ref && (
        <Input key={`input-${tab.ref}`} label={T().toTabLabel} placeholder={T().toTabPlaceholder} submitLabel={T().btnSend}
          autoFocus onSubmit={(text: string) => send($, tab, text)} />
      )}
    </Box>
  )

  const detail = (row: Row, tab: Tab | undefined, inSidebar = false, hasStartRow = false) => {
    const url = rowUrl(row)
    // a dead shell tab blocks nothing: what a live agent tab would make pointless stays on offer
    const agent = tab && isLive(tab) ? tab : undefined
    const isInbox = row.inboxId !== null && row.gate !== 'free'
    return (
      <Box key={`detail-${row.key}`} flexDirection="column" marginLeft={inSidebar ? 0 : 6}
        borderStyle={inSidebar ? undefined : 'round'} borderDimColor paddingX={inSidebar ? 0 : 1}>
        {!inSidebar && <Text wrap="wrap" bold>{row.title}</Text>}
        {!inSidebar && row.why.length > 0 && <Text dimColor>{row.why.join(' · ')}</Text>}
        {!inSidebar && tab && <Text dimColor>{T().tabInfo(tab.workspace, tab.name, stateWord(tab.state))}</Text>}
        <Box flexWrap="wrap">
          <Text>{isInbox ? T().laterPrefix : T().hidePrefix}</Text>
          <Button key={`l1-${row.key}`} label={T().btnTomorrow} onPress={() => later($, row, isoDate(now + DAY))} />
          <Button key={`l3-${row.key}`} label={T().btnMonday} onPress={() => later($, row, isoDate(nextMonday(now)))} />
          <Button key={`l7-${row.key}`} label={T().btnWeek} onPress={() => later($, row, isoDate(now + 7 * DAY))} />
          {Input && (
            <Input key={`lx-${row.key}`} placeholder={T().datePlaceholder} submitLabel={T().btnUntil}
              onSubmit={async (text: string) => {
                const date = parseDate(text, await $.clock.now())
                if (date) await later($, row, date)
                else await note($, T().noDate(short(text, 20)))
              }} />
          )}
        </Box>
        {(row.inboxId || row.task) && (
          <Box flexWrap="wrap">
            {row.inboxId && <Text>{T().urgencyPrefix}</Text>}
            {row.inboxId && ['now', 'today', 'later'].map(u => (
              <Button key={`u-${u}-${row.key}`} label={T().urgency[u] ?? u} selected={row.urgency === u}
 onPress={() => setUrgency($, row, u)} />
            ))}
            {row.task && <Text>{row.inboxId ? '  ' : ''}{T().prioPrefix}</Text>}
            {row.task && ['P0', 'P1', 'P2', 'P3'].map(p => (
              <Button key={`p-${p}-${row.key}`} label={p} selected={row.priority === p}
 onPress={() => setPriority($, row, p)} />
            ))}
          </Box>
        )}
        {row.task && !row.inboxId && recipes.length > 0 && (() => {
          const st = teamState(row, chosen, recipes, tabList, now)
          const fits = (t: Team) => (row.taskType !== null && t.forTypes.includes(row.taskType) ? 0 : 1)
          return (
            <Box flexWrap="wrap">
              <Text>{st ? T().teamProgress(st.team.label, st.started, st.team.roles.length) : T().teamPrefix}</Text>
              {st && st.next && (st.isReady ? (
                <Button key={`team-next-${row.key}`} variant="primary" label={`▶ ${st.next.name}`}
 onPress={act($, () => startRole($, row, st.team))} />
              ) : (
                <Text dimColor>{T().teamStillWorking(st.waitingFor ?? '')}</Text>
              ))}
              {[...recipes].sort((a, b) => fits(a) - fits(b)).filter(t => !st || t.id !== st.team.id).map(t => (
                <Button key={`team-${t.id}-${row.key}`} variant={fits(t) === 0 && !st ? 'primary' : undefined}
 
 label={inSidebar ? `${st ? T().teamNew : ''}${t.label}` : `${st ? T().teamNew : ''}${t.label} (${t.roles.map(r => r.name).join(' → ')})`}
 onPress={act($, () => startRole($, row, t))} />
              ))}
            </Box>
          )
        })()}
        {launchItem(row) !== null && (
          <Box flexWrap="wrap">
            <Text>{T().contextPrefix}</Text>
            <Button key={`ctx-${row.key}`} label={T().btnCollect}
 onPress={act($, async () => launch($, [row], 'context', (await read($, config))?.target ?? 'area'))} />
            {Input && (
              <Input key={`note-${row.key}`} placeholder={T().notePlaceholder} submitLabel={T().btnNote}
                onSubmit={(text: string) => addNote($, row, text)} />
            )}
          </Box>
        )}
        {row.task && !row.inboxId && !agent && (() => {
          // Agent tabs in the area of the task that do not belong to anything yet
          const free = tabList.filter(t => row.areaNames.includes(t.workspace) && !t.slug && !t.item && t.state !== 'shell')
          return free.length > 0 && (
            <Box flexWrap="wrap">
              <Text>{T().adoptPrefix}</Text>
              {free.slice(0, 4).map(t => (
                <Button key={`adopt-${t.ref}-${row.key}`} label={short(t.name, inSidebar ? 18 : 28)} 
 onPress={() => adopt($, row, t)} />
              ))}
            </Box>
          )
        })()}
        {row.task && !row.inboxId && reviewBox(row)}
        <Box flexWrap="wrap">
          {launchItem(row) !== null && !agent && !hasStartRow && (
            <Button key={`ws-${row.key}`} label={inSidebar ? T().btnOwnWs : T().btnDoOwnWs}
 onPress={act($, () => doIt($, [row], 'workspace'))} />
          )}
          {row.inboxId && row.gate === 'only-you' && (
            <Button key={`drop-${row.key}`} label={T().btnDrop} onPress={act($, () => drop($, row))}  tone={RED} />
          )}
          <Button key={`ask-${row.key}`} label={T().btnAskChat} onPress={() => ask($, askAbout(row))} />
          {url && <Link key={`url-${row.key}`} href={url} label={T().btnOpen} />}
        </Box>
      </Box>
    )
  }

  // An opened row of a task page: what the task is, then every way to start it or to reach its tab.
  const taskDetail = (it: Info, row: Row, inSidebar: boolean) => {
    const tab = tabFor(row, tabList)
    const agent = tab && isLive(tab) ? tab : undefined
    const entries = (v?.buckets ?? []).flatMap(b => b.rows)
      .filter(r => r.task === row.task && r.inboxId !== null && !done.includes(r.key))
    const state = it.state ? T().taskState[it.state] ?? it.state : null
    const head = [it.priority ?? row.priority, row.area, state, it.when].filter(Boolean).join(' · ')
    return (
      <Box key={`task-${row.key}`} flexDirection="column" marginLeft={inSidebar ? 0 : 2} marginBottom={1}
        borderStyle="round" borderDimColor paddingX={1}>
        <Text bold wrap="wrap">{it.title}</Text>
        {head && <Text dimColor wrap="wrap">{head}</Text>}
        {row.why.length > 0 && <Text dimColor wrap="wrap">{row.why.join(' · ')}</Text>}
        {it.lines.map((l, j) => (
          <Text key={`tl-${row.key}-${j}`} wrap="wrap"><Text dimColor>{T().lineKind[l.kind] ?? ''}</Text>{l.text}</Text>
        ))}
        {tab && <Text dimColor wrap="wrap">{T().tabInfo(tab.workspace, tab.name, stateWord(tab.state))}</Text>}
        <Box flexWrap="wrap">
          {rowActions($, row, tab).map(a => (
            <Button key={`ta-${a.id}-${row.key}`} label={a.label} variant={a.primary ? 'primary' : undefined}
 tone={a.tone} onPress={act($, a.run)} />
          ))}
          {agent && tabButtons(agent)}
        </Box>
        {!agent && (
          <Box flexWrap="wrap">
            {(['tab', 'area', 'workspace'] as const).map(t => (
              <Button key={`ts-${t}-${row.key}`} label={T().startAt(t, row.area)}
 onPress={act($, () => launch($, [row], 'go', t))} />
            ))}
          </Box>
        )}
        {entries.length > 0 && <Text bold>{T().inboxOpen(entries.length)}</Text>}
        {entries.map(r => (
          <Box key={`te-${r.key}`} flexWrap="wrap">
            <Text>{`· ${short(r.title, inSidebar ? 30 : 60)} `}</Text>
            {rowActions($, r, tabFor(r, tabList)).map(a => (
              <Button key={`te-${a.id}-${r.key}`} label={a.label} variant={a.primary ? 'primary' : undefined}
 tone={a.tone} onPress={act($, a.run)} />
            ))}
          </Box>
        ))}
        {detail(row, tab, true, true)}
      </Box>
    )
  }

  const rowLine = (row: Row, n: number | null) => {
    const tab = tabFor(row, tabList)
    const team = teamState(row, chosen, recipes, tabList, now)
    const acts = rowActions($, row, tab)
    const canPick = (!tab || !isLive(tab)) && launchItem(row) !== null && row.inboxState !== 'approved'
    const isOpen = open === row.key
    const toggleRow = () => update($, expanded, cur => (cur === row.key ? null : row.key))
    return (
      <Box key={`row-${row.key}`} flexDirection="column">
        <Box>
          <Box width={LEAD} flexShrink={0}>
            {canPick ? (
              <Button key={`pick-${row.key}`} label={picked.includes(row.key) ? '[x]' : '[ ]'}
 onPress={() => toggle(row)} />
            ) : <Text>   </Text>}
            <Text dimColor>{n === null ? '' : String(n).padStart(3)}</Text>
          </Box>
          <Box width={AREA} flexShrink={0}><Text dimColor wrap="truncate-end">{row.area ?? ''}</Text></Box>
          <Box width={MARK} flexShrink={0}>
            {row.urgency === 'now' ? <Text color="red" bold>!</Text> : null}
            {row.priority && <Text color={PRIO_COLOR[row.priority] ?? 'cyan'}>{row.priority}</Text>}
          </Box>
          <Box flexGrow={1} flexShrink={1}>
            <Text wrap="truncate-end">
              {markText(row.mark, row.area)}
              {isOpen ? <Text bold>{row.title}</Text> : row.title}
              {!row.inboxId && tagOf(row.task)}
              {tab && <Text color={tabColor(tab)}>{`  ● ${stateWord(tab.state)}`}</Text>}
              {team && <Text color="magenta">{`  ${team.team.label} ${team.started}/${team.team.roles.length}`}</Text>}
            </Text>
          </Box>
          <Box flexShrink={0} marginLeft={1}>
            {team && team.next && team.started > 0 && team.isReady && (
              <Button key={`next-${row.key}`} label={`▶ ${team.next.name}`} variant="primary"
 onPress={act($, () => startRole($, row, team.team))} />
            )}
            {acts.map(a => (
              <Button key={`${a.id}-${row.key}`} label={label(a)} variant={a.primary ? 'primary' : undefined}
 tone={a.tone} onPress={act($, a.run)} />
            ))}
            <Button key={`more-${row.key}`} label={T().btnDetails(isOpen)} onPress={toggleRow} />
          </Box>
        </Box>
        {isOpen && detail(row, tab)}
      </Box>
    )
  }

  const numberOf = (row: Row) => lay.numbers.get(row.key) ?? null

  const block = (id: SectionId) => {
    const s = byId[id]
    const more = s.all.length - s.shown.length
    const tabCount = id === 'now' ? waiting.length : 0
    if (s.all.length === 0 && tabCount === 0) return null
    const isOpen = section === id || all
    const shownTabs = isOpen ? waiting : waiting.slice(0, TAB_CAP)
    const moreTabs = id === 'now' ? waiting.length - shownTabs.length : 0
    return (
      <Box key={`block-${id}`} flexDirection="column" marginTop={1}>
        <Box>
          <Box flexShrink={0}>
            <Text bold color={SECTION_COLOR[id]}>{T().section[id]}</Text>
            <Text dimColor>{` ${s.all.length + tabCount} `}</Text>
            {id === 'work' && reviewButton('review-all-work')}
            {id === 'work' && <Text> </Text>}
            {id === 'work' && meta && (
              <Button key="review-overview" selected={showOv} label={T().btnOverview}
 onPress={() => update($, showOverview, x => !x)} />
            )}
            {id === 'work' && meta && <Text> </Text>}
            {id === 'give' && s.all.length > 1 && (
              <Button key="pick-give" label={`${T().btnPickAll} `} 
 onPress={() => update($, selected, list => [...new Set([...list,
 ...s.all.filter(r => !tabFor(r, tabList) && launchItem(r) !== null && r.inboxState !== 'approved')
 .map(r => r.key)])])} />
            )}
            {id === 'give' && approvable(s.shown).length > 1 && !isConfirming && (
              <Button key="approve-all" label={`${T().approveAll(approvable(s.shown).length)} `} 
 onPress={() => update($, confirmAll, () => true)} />
            )}
          </Box>
          <Box flexGrow={1} width={0} height={1} overflow="hidden"><Text dimColor>{RULE}</Text></Box>
        </Box>
        {id === 'give' && isConfirming && approvable(s.shown).length > 0 && (
          <Box flexWrap="wrap">
            <Text color="yellow">{`${T().approveAsk(approvable(s.shown).length)} `}</Text>
            <Button key="approve-yes" label={T().approveYes} variant="primary" onPress={async () => {
 // Only the rows on screen: a yes never reaches an item nobody saw. Each approval notes itself.
 const rows = approvable(s.shown)
 await update($, confirmAll, () => false)
 await doIt($, rows)
 }} />
            <Button key="approve-no" label={T().approveNo} onPress={() => update($, confirmAll, () => false)}  tone={RED} />
          </Box>
        )}
        {id === 'now' && shownTabs.map(tabLine)}
        {s.shown.map(row => rowLine(row, numberOf(row)))}
        {(more > 0 || moreTabs > 0) && !isOpen && (
          <Box paddingLeft={LEAD}>
            <Button key={`more-${id}`} 
 label={`${T().moreRows(more + moreTabs)}${id === 'work' ? T().moreWork : ''}`}
 onPress={() => setSection(id)} />
          </Box>
        )}
        {section === id && !all && (
          <Box paddingLeft={LEAD}>
            <Button key={`less-${id}`} label={T().btnLess} onPress={() => setSection(null)} />
          </Box>
        )}
      </Box>
    )
  }

  const give = byId.give
  const laterSection = byId.later
  const laterOpen = section === 'later' || all

  // Status tabs: systems, appointments, GitHub, today; the same data as the briefing, no separate fetch.
  const pageSel = await read($, page)
  const infoPages = v?.pages ?? []
  const shownPage = infoPages.find(pg => pg.id === pageSel) ?? null
  const pageIds = [BRIEFING_PAGE, ...infoPages.map(pg => pg.id)]
  const pageTitle = (id: string) => (id === BRIEFING_PAGE ? T().briefing : infoPages.find(pg => pg.id === id)?.title ?? id)
  const badge = (id: string) => (id === BRIEFING_PAGE
    ? { text: String(waiting.length + byId.now.all.length + give.all.length) } as { text: string; color?: string }
    : pageBadge(infoPages.find(pg => pg.id === id)!))
  // Red findings and the tab they sit on
  const alarmPage = infoPages.find(pg => pg.sections.some(x => x.bad > 0)) ?? null
  const alarmCount = infoPages.reduce((n, pg) => n + pg.sections.reduce((m, x) => m + x.bad, 0), 0)
  const goPage = async (id: string) => {
    await update($, page, () => id)
    await update($, expanded, () => null)
  }
  const pageBar = (
    <Box flexWrap="wrap">
      {pageIds.map(id => (
        <Box key={`pg-${id}`} marginRight={2}>
          {(shownPage?.id ?? BRIEFING_PAGE) === id ? (
            <Text bold underline>{pageTitle(id)}</Text>
          ) : (
            <Button key={`pgb-${id}`} label={pageTitle(id)}
 onPress={() => goPage(id)} />
          )}
          <Text color={badge(id).color} dimColor={!badge(id).color}>{` ${badge(id).text}`}</Text>
        </Box>
      ))}
    </Box>
  )

  const pageBarWidth = pageIds.reduce((n, id) => n + pageTitle(id).length + badge(id).text.length + 3, 0)
  const helpBox = help && (
    <Box flexDirection="column" borderStyle="round" borderDimColor paddingX={1} marginTop={1}>
      <Box>
        <Text bold>{`${TABLES[lang].helpTitle} `}</Text>
        <Button key="lang-de" label={LANG_NAME.de} selected={lang === 'de'} onPress={() => update($, helpLang, () => 'de')} />
        <Button key="lang-en" label={LANG_NAME.en} selected={lang === 'en'} onPress={() => update($, helpLang, () => 'en')} />
      </Box>
      {TABLES[lang].help.map(([what, does]) => (
        width >= 70 ? (
          <Box key={`help-${what}`}>
            <Box width={18} flexShrink={0}><Text bold>{what}</Text></Box>
            <Box flexGrow={1} width={0}><Text wrap="wrap">{does}</Text></Box>
          </Box>
        ) : (
          <Box key={`help-${what}`} flexDirection="column">
            <Text bold>{what}</Text>
            <Box paddingLeft={2}><Text wrap="wrap" dimColor>{does}</Text></Box>
          </Box>
        )
      ))}
    </Box>
  )

  if (shownPage) {
    const startingNow = await read($, starting)
    const sections = shownPage.sections
    // Panel: as many rows per section as fit in the height; card: ten, "all" shows all.
    const perSection = all ? 999 : inChat ? 10 : Math.max(2, Math.floor((height - 6) / Math.max(1, sections.length)) - 2)
    const whenWidth = Math.min(16, Math.max(0, ...sections.flatMap(x => x.items.map(it => it.when.length))))
    const isWide = width >= 70
    return (
      <Box flexDirection="column" borderStyle={inChat ? 'round' : undefined} borderDimColor paddingX={inChat ? 1 : 0}>
        <Box>
          <Text dimColor>{`${T().asOf} `}</Text>
          <Text dimColor>{v ? `${v.collectedAt}${v.isFull ? '' : ` ${T().noTracker}`}` : T().loading}{busy ? ` · ${T().loadingWhat(busy)}` : ''}</Text>
          <Box flexGrow={1} />
          <Box flexShrink={0}>
            <Button key="pg-reload" label="⟳" onPress={() => startLoad($, 'full')} />
            <Text>  </Text>
            <Button key="pg-all" label={all ? T().btnCompact : T().btnAll} selected={all} onPress={() => update($, showAll, x => !x)} />
            <Text>  </Text>
            <Button key="pg-help" label="?" selected={help} onPress={() => update($, showHelp, x => !x)} />
            <Text>  </Text>
            <Button key="pg-close" role="dismiss" label="✕" 
 onPress={() => (inChat ? update($, isClosed, () => true) : $.ui.close({ id: PANE }))} />
          </Box>
        </Box>
        {pageBar}
        {helpBox}
        {sections.some(x => x.kind === 'tasks') && ovList.length > 0 && overviewBox(isWide)}
        {sections.map(sec => (
          <Box key={`ps-${sec.id}`} flexDirection="column" marginTop={1}>
            <Box>
              <Box flexShrink={0}>
                <Text bold color={sec.alarm && sec.count > 0 ? 'red' : undefined}>{sec.title.replace(/\s*\(.*?\)/g, '')}</Text>
                <Text dimColor>{` ${sec.status === 'skipped' ? '' : sec.count} `}</Text>
                {sec.asOf && <Text dimColor>{`${T().sourceAsOf(sec.asOf)} `}</Text>}
                {sec.kind === 'tasks' && reviewButton(`review-all-${sec.id}`)}
                {sec.kind === 'tasks' && <Text> </Text>}
              </Box>
              <Box flexGrow={1} width={0} height={1} overflow="hidden"><Text dimColor>{RULE}</Text></Box>
            </Box>
            {sec.status === 'skipped' && <Text dimColor>{`   ${T().skippedSection}`}</Text>}
            {sec.status !== 'skipped' && sec.count === 0 && (
              <Text color={sec.alarm && sec.status === 'ok' ? 'green' : undefined} dimColor={!sec.alarm || sec.status !== 'ok'}>
                {`   ${sec.status === 'ok' ? sec.empty : T().unreadable(short(sec.reason || sec.status, 90))}`}
              </Text>
            )}
            {sec.items.slice(0, perSection).map((it, i) => {
              // A task row opens (▾) to its details and every way to start it, at any width.
              const trow = sec.kind === 'tasks' && it.task ? taskRowFor(it.task, it.title, taskList) : null
              const isOpen = trow !== null && open === trow.key
              return (
              <Box key={`pi-${sec.id}-${i}`} flexDirection="column">
              <Box>
                {whenWidth > 0 && (
                  <Box width={whenWidth + 1} flexShrink={0}>
                    <Text dimColor wrap="truncate-end">{it.when}</Text>
                  </Box>
                )}
                <Box flexGrow={1} width={0}>
                  <Text wrap="truncate-end" dimColor={it.tone === 'dim'}
                    color={it.tone === 'bad' ? 'red' : it.tone === 'warn' ? 'yellow' : undefined}>
                    {markText(it.mark, null)}{isOpen ? <Text bold>{it.title}</Text> : it.title}{tagOf(it.task)}</Text>
                </Box>
                {it.detail && isWide && (
                  <Box flexShrink={0} marginLeft={1}><Text dimColor>{short(it.detail, 36)}</Text></Box>
                )}
                {isWide && it.task && (() => {
                  const open = tabFor(trow ?? taskRow(it.task, it.title), tabList)
                  return (
                    <Box flexShrink={0} marginLeft={1}>
                      {open && isLive(open) ? (
                        <Button key={`pt-${sec.id}-${i}`} label={T().btnToTab} onPress={() => jump($, open)} />
                      ) : startingNow.includes(it.task) ? (
                        <Text dimColor>{T().startingTab}</Text>
                      ) : (
                        <Button key={`pt-${sec.id}-${i}`} label={T().btnOpenTab}
 onPress={act($, async () =>
 launch($, [trow ?? taskRow(it.task!, it.title)], 'report', (await read($, config))?.target ?? 'area'))} />
                      )}
                    </Box>
                  )
                })()}
                {isWide && it.ask && (
                  <Box flexShrink={0} marginLeft={1}>
                    <Button key={`pa-${sec.id}-${i}`} label={T().btnAsk}
 onPress={() => ask($, askInfo(sec.title.replace(/\s*\(.*?\)/g, ''), it))} />
                  </Box>
                )}
                {it.url && isWide && (
                  <Box flexShrink={0} marginLeft={1}><Link key={`pl-${sec.id}-${i}`} href={it.url} label={T().btnOpen} /></Box>
                )}
                {trow && (
                  <Box flexShrink={0} marginLeft={1}>
                    <Button key={`px-${sec.id}-${i}`} label={T().btnDetails(isOpen)}
 onPress={() => update($, expanded, cur => (cur === trow.key ? null : trow.key))} />
                  </Box>
                )}
              </Box>
              {isOpen && trow && taskDetail(it, trow, !isWide)}
              </Box>
              )
            })}
            {sec.items.length > perSection && (
              <Box paddingLeft={whenWidth + 1}>
                <Button key={`pm-${sec.id}`} label={T().moreRows(sec.items.length - perSection)}
 onPress={() => update($, showAll, () => true)} />
              </Box>
            )}
          </Box>
        ))}
        {log[0] && <Text dimColor wrap="truncate-end">{log[0]}</Text>}
      </Box>
    )
  }

  // Sidebar (and narrow card): tabs instead of blocks, one row per item, page instead of scroll.
  if (!inChat || width < NARROW) {
    const tabSel = await read($, sideTab)
    const page = await read($, sidePage)
    const more = await read($, sideMore)
    const agentTabs = tabList.filter(t => t.state !== 'shell')
    const counts: Record<SideTab, number> = {
      all: 0,
      now: waiting.length + byId.now.all.length,
      give: give.all.length,
      work: byId.work.all.length,
      later: laterSection.all.length + lay.hiddenRows.length,
      tabs: agentTabs.length,
    }
    const NAMES: Record<SideTab, string> = T().side
    type Item = { kind: 'tab'; tab: Tab } | { kind: 'row'; row: Row } | { kind: 'hidden'; row: Row }
      | { kind: 'head'; id: SectionId; count: number } | { kind: 'more'; id: SectionId; count: number }
    const asRows = (list: Row[]) => list.map(r => ({ kind: 'row' as const, row: r }))
    // All: every block with a heading, like the wide card; tasks compact, Later only as a number.
    const overviewItems = (): Item[] => {
      const out: Item[] = []
      const section = (id: SectionId, body: Item[], count: number, rest: number) => {
        if (count === 0) return
        out.push({ kind: 'head', id, count }, ...body)
        if (rest > 0) out.push({ kind: 'more', id, count: rest })
      }
      section('now', [...waiting.map(t => ({ kind: 'tab' as const, tab: t })), ...asRows(byId.now.all)],
        counts.now, 0)
      section('give', asRows(give.all), counts.give, 0)
      section('work', asRows(byId.work.shown), counts.work, byId.work.all.length - byId.work.shown.length)
      section('later', [], counts.later, 0)
      return out
    }
    const items: Item[] =
      tabSel === 'all' ? overviewItems()
      : tabSel === 'tabs' ? agentTabs.map(t => ({ kind: 'tab' as const, tab: t }))
        : tabSel === 'now' ? [...waiting.map(t => ({ kind: 'tab' as const, tab: t })),
          ...byId.now.all.map(r => ({ kind: 'row' as const, row: r }))]
          : tabSel === 'later' ? [...laterSection.all.map(r => ({ kind: 'row' as const, row: r })),
            ...lay.hiddenRows.map(r => ({ kind: 'hidden' as const, row: r }))]
            : byId[tabSel].all.map(r => ({ kind: 'row' as const, row: r }))
    const keyOf = (it: Item) =>
      it.kind === 'tab' ? `tab:${it.tab.ref}` : it.kind === 'head' || it.kind === 'more' ? `${it.kind}:${it.id}` : it.row.key
    const openIndex = items.findIndex(it => keyOf(it) === open)
    // Height: head, tabs (one or two rows), line, paging, feedback; an open row needs more.
    const barWidth = (['all', 'now', 'give', 'work', 'later', 'tabs'] as const)
      .reduce((sum, id) => sum + NAMES[id].length + String(counts[id]).length + 3, 0)
    const barLines = barWidth > width ? 2 : 1
    const groupBreak = tabSel === 'now' && waiting.length > 0 && byId.now.all.length > 0 ? 1 : 0
    // Blank lines before the headings of the overview
    const headGaps = Math.max(0, items.filter(it => it.kind === 'head').length - 1)
    const pageBarLines = pageBarWidth > width ? 2 : 1
    const fixed = 5 + pageBarLines + barLines + groupBreak + headGaps + (pickedRows.length ? 1 : 0) + (tabErr ? 1 : 0)
    const openCost = openIndex < 0 ? 0 : more ? 18 : 6
    const perPage = Math.max(3, height - fixed - openCost)
    const pages = Math.max(1, Math.ceil(items.length / perPage))
    // An open row needs room; the page follows it instead of pushing it away.
    const pageNow = openIndex >= 0 ? Math.floor(openIndex / perPage) : Math.min(page, pages - 1)
    const shownItems = items.slice(pageNow * perPage, pageNow * perPage + perPage)
    const toggleOpen = (key: string) => {
      void update($, sideMore, () => false)
      return update($, expanded, cur => (cur === key ? null : key))
    }

    const isNarrow = width < 44
    const wsWidth = isNarrow ? 7 : 10
    const sideRow = (row: Row) => {
      const tab = tabFor(row, tabList)
      const team = teamState(row, chosen, recipes, tabList, now)
      const isOpen = open === row.key
      const canPick = (!tab || !isLive(tab)) && launchItem(row) !== null && row.inboxState !== 'approved'
      const n = lay.numbers.get(row.key)
      const urgent = row.urgency === 'now'
      const markWidth = (urgent ? 1 : 0) + (row.priority ? row.priority.length : 0) + (tab ? 1 : 0)
      const areaWidth = isNarrow ? 0 : wsWidth
      const titleWidth = Math.max(8, width - 4 - 3 - areaWidth - (markWidth ? markWidth + 1 : 0) - 1)
      return (
        <Box key={`side-${row.key}`} flexDirection="column">
          <Box>
            <Box width={4} flexShrink={0}>
              {canPick ? (
                <Button key={`spick-${row.key}`} label={picked.includes(row.key) ? '[x]' : '[ ]'} onPress={() => toggle(row)} />
              ) : <Text>   </Text>}
            </Box>
            <Box width={3} flexShrink={0}><Text dimColor>{n ? String(n).padStart(2) : ''}</Text></Box>
            {areaWidth > 0 && <Box width={areaWidth} flexShrink={0}><Text dimColor wrap="truncate-end">{row.area ?? ''}</Text></Box>}
            {markWidth > 0 && (
              <Box width={markWidth + 1} flexShrink={0}>
                {urgent && <Text color="red" bold>!</Text>}
                {row.priority && <Text color={PRIO_COLOR[row.priority] ?? 'cyan'}>{row.priority}</Text>}
                {tab && <Text color={tabColor(tab)}>●</Text>}
              </Box>
            )}
            <Box flexGrow={1} flexShrink={1}>
              {markText(row.mark, row.area)}
              <Button key={`stitle-${row.key}`} label={short(row.title, titleWidth - (row.mark ? row.mark.label.length + 1 : 0))}
 onPress={() => toggleOpen(row.key)} />
            </Box>
          </Box>
          {isOpen && (
            <Box flexDirection="column" marginLeft={2} marginBottom={1} paddingX={1} borderStyle="round" borderDimColor>
              {row.title.length > titleWidth && <Text wrap="wrap" bold>{row.title}</Text>}
              {row.why.length > 0 && <Text dimColor wrap="wrap">{row.why.join(' · ')}</Text>}
              {(row.area || tab || team) && (
                <Text wrap="truncate-end">
                  {row.area && <Text dimColor>{row.area}</Text>}
                  {tab && <Text color={tabColor(tab)}>{`  ● Tab ${stateWord(tab.state)}`}</Text>}
                  {team && <Text color="magenta">{`  Team ${team.team.label} ${team.started}/${team.team.roles.length}`}</Text>}
                </Text>
              )}
              <Box flexWrap="wrap">
                {rowActions($, row, tab).map(a => (
                  <Button key={`sa-${a.id}-${row.key}`} label={a.label} variant={a.primary ? 'primary' : undefined}
 tone={a.tone} onPress={act($, a.run)} />
                ))}
                {team && team.next && team.started > 0 && team.isReady && (
                  <Button key={`snext-${row.key}`} label={`▶ ${team.next.name}`} variant="primary"
 onPress={act($, () => startRole($, row, team.team))} />
                )}
                <Button key={`smore-${row.key}`} label={T().btnDetails(more)}
 onPress={() => update($, sideMore, x => !x)} />
              </Box>
              {!more && row.task && !row.inboxId && reviewBox(row)}
              {more && detail(row, tab, true)}
            </Box>
          )}
        </Box>
      )
    }

    // Narrow: shorter workspace, state only if the item does not already say it.
    const stateOf = (t: Tab) => longText(t, seen, now) ?? (isNarrow && ATTENTION.has(t.state) ? '' : stateWord(t.state))
    const stateWidth = Math.max(0, ...shownItems.map(it => (it.kind === 'tab' ? stateOf(it.tab).length : 0)))
    const sideTabItem = (tab: Tab) => {
      const key = `tab:${tab.ref}`
      const isOpen = open === key
      const isLoud = ATTENTION.has(tab.state)
      const lng = longText(tab, seen, now)
      const state = stateOf(tab)
      const nameWidth = Math.max(8, width - 2 - wsWidth - (stateWidth ? stateWidth + 1 : 0) - 1)
      return (
        <Box key={`stab-${tab.ref}`} flexDirection="column">
          <Box>
            <Box width={2} flexShrink={0}><Text color={tabColor(tab)}>●</Text></Box>
            {wsWidth > 0 && <Box width={wsWidth} flexShrink={0}><Text dimColor wrap="truncate-end">{tab.workspace}</Text></Box>}
            <Box flexGrow={1} flexShrink={1}>
              <Button key={`stt-${tab.ref}`} label={short(tab.name, nameWidth)} onPress={() => toggleOpen(key)} />
            </Box>
            {stateWidth > 0 && (
              <Box width={stateWidth + 1} flexShrink={0} justifyContent="flex-end">
                <Text color={lng ? 'red' : tabColor(tab)} dimColor={!lng && !isLoud}>{state}</Text>
              </Box>
            )}
          </Box>
          {isOpen && (
            <Box flexDirection="column" marginLeft={2} marginBottom={1} paddingX={1} borderStyle="round" borderDimColor>
              <Text wrap="truncate-end">
                <Text dimColor>{tab.workspace}</Text>
                <Text color={lng ? 'red' : tabColor(tab)}>{`  ${lng ?? stateWord(tab.state)}`}</Text>
              </Text>
              {tab.name.length > nameWidth && <Text wrap="wrap" bold>{tab.name}</Text>}
              {filedBy(tab, v) && <Text color="green">{T().resultFiledLong}</Text>}
              {tab.last && <Text wrap="wrap" dimColor>{short(tab.last, 400)}</Text>}
              <Box flexWrap="wrap">
                <Button key={`sj-${tab.ref}`} label={T().btnToTab} variant="primary" onPress={() => jump($, tab)} />
                {tabButtons(tab)}
              </Box>
              {Input && (
                <Input key={`si-${tab.ref}`} placeholder={T().msgPlaceholder} submitLabel={T().btnSend}
                  onSubmit={(text: string) => send($, tab, text)} />
              )}
            </Box>
          )}
        </Box>
      )
    }

    const firstRow = shownItems.findIndex(it => it.kind !== 'tab')
    return (
      <Box flexDirection="column">
        <Box>
          <Text dimColor>{`${T().asOf} `}</Text>
          <Text dimColor>{v ? v.collectedAt : '…'}{busy ? ' ⟳' : ''}</Text>
          <Box flexGrow={1} />
          <Box flexShrink={0}>
            <Button key="s-reload" label="⟳" onPress={() => startLoad($, 'full')} />
            <Text>  </Text>
            <Button key="s-help" label="?" selected={help} onPress={() => update($, showHelp, x => !x)} />
            <Text>  </Text>
            <Button key="s-close" role="dismiss" label="✕" 
 onPress={() => (inChat ? update($, isClosed, () => true) : $.ui.close({ id: PANE }))} />
          </Box>
        </Box>
        {pageBar}
        <Box flexWrap="wrap">
          {(['all', 'now', 'give', 'work', 'later', 'tabs'] as const).map(id => (
            <Box key={`stb-${id}`} marginRight={2}>
              {tabSel === id ? (
                <Text bold underline color={id === 'tabs' || id === 'all' ? undefined : SECTION_COLOR[id]}>
                  {id === 'all' ? NAMES[id] : `${NAMES[id]} ${counts[id]}`}
                </Text>
              ) : (
                <Button key={`st-${id}`} label={id === 'all' ? NAMES[id] : `${NAMES[id]} ${counts[id]}`} 
 onPress={async () => {
 await update($, sideTab, () => id)
 await update($, sidePage, () => 0)
 }} />
              )}
            </Box>
          ))}
        </Box>
        <Text wrap="truncate-end">
          <Text color={waiting.length ? 'yellow' : 'green'}>{T().waitCount(waiting.length)}</Text>
          {longCount > 0 && <Text color="red">{` ${T().longCount(longCount)}`}</Text>}
          <Text color="green">{`  ${T().workingCount(busyTabs)}`}</Text>
          {alarmCount > 0 && <Text color="red">{`  ✗ ${alarmCount} ${alarmPage?.title ?? ''}`}</Text>}
        </Text>
        {tabErr && <Text color="red" wrap="truncate-end">{tabErr}</Text>}
        <Box height={1} overflow="hidden"><Text dimColor>{RULE}</Text></Box>
        {help ? (
          <Box flexDirection="column">
            <Box>
              <Button key="s-de" label={LANG_NAME.de} selected={lang === 'de'} onPress={() => update($, helpLang, () => 'de')} />
              <Button key="s-en" label={LANG_NAME.en} selected={lang === 'en'} onPress={() => update($, helpLang, () => 'en')} />
            </Box>
            {TABLES[lang].help.map(([what, does]) => (
              <Box key={`sh-${what}`} flexDirection="column">
                <Text bold>{what}</Text>
                <Box paddingLeft={2}><Text wrap="wrap" dimColor>{does}</Text></Box>
              </Box>
            ))}
            {inCmux && <Text dimColor>{backupText}</Text>}
            <Box flexWrap="wrap">
              {inCmux && <Button key="s-snap" label={T().btnSave} onPress={() => snapshot($, true)} />}
              {v && <Button key="s-overview" label={T().btnSort} 
 onPress={() => ask($, overview(v, lay.sections.flatMap(x => x.all)))} />}
              {v && <Button key="s-plan" label={T().btnPlan} 
 onPress={async () => ask($, planDay(v, lay.sections.flatMap(x => x.all),
 (await read($, tabs)).filter(t => isWaiting(t, v))))} />}
              <Button key="s-evening" label={T().btnEvening} 
 onPress={async () => ask($, evening(await read($, tabs), await read($, tabSeen), await $.clock.now()))} />
            </Box>
          </Box>
        ) : (
          <Box flexDirection="column">
            {pickedRows.length > 0 && (
              <Box flexWrap="wrap">
                <Text bold>{`${T().picked(pickedRows.length)} `}</Text>
                <Button key="sp-do" label={T().btnDo} variant="primary" onPress={act($, () => doIt($, pickedRows))} />
                <Button key="sp-adv" label={T().btnAdvise} onPress={act($, () => advise($, pickedRows))} />
                <Button key="sp-clear" label="✕" onPress={() => update($, selected, () => [])} />
              </Box>
            )}
            {items.length === 0 && <Text dimColor>{`   ${T().nothingHere}`}</Text>}
            {shownItems.map((it, i) => (
              <Box key={`si-${keyOf(it)}`} flexDirection="column">
                {groupBreak > 0 && i === firstRow && i > 0 && (
                  <Box height={1} overflow="hidden"><Text dimColor>{`${T().inboxRule} ${RULE}`}</Text></Box>
                )}
                {it.kind === 'head' ? (
                  <Box marginTop={i > 0 ? 1 : 0}>
                    <Box flexShrink={0}>
                      <Text bold color={SECTION_COLOR[it.id]}>{T().section[it.id]}</Text>
                      <Text dimColor>{` ${it.count} `}</Text>
                    </Box>
                    <Box flexGrow={1} width={0} height={1} overflow="hidden"><Text dimColor>{RULE}</Text></Box>
                    <Box flexShrink={0}>
                      <Button key={`sgo-${it.id}`} label={T().showAll} onPress={async () => {
 await update($, sideTab, () => it.id)
 await update($, sidePage, () => 0)
 }} />
                    </Box>
                  </Box>
                ) : it.kind === 'more' ? (
                  <Box paddingLeft={7}>
                    <Button key={`smr-${it.id}`} label={T().moreArrow(it.count)} onPress={async () => {
 await update($, sideTab, () => it.id)
 await update($, sidePage, () => 0)
 }} />
                  </Box>
                ) : it.kind === 'tab' ? sideTabItem(it.tab)
                  : it.kind === 'row' ? sideRow(it.row)
                    : (
                      <Box>
                        <Box flexGrow={1} flexShrink={1}>
                          <Text dimColor wrap="truncate-end">{`    ${it.row.title}`}</Text>
                        </Box>
                        <Text dimColor>{` ${T().hiddenUntil(hide[it.row.key] ?? '')} `}</Text>
                        <Button key={`su-${it.row.key}`} label={T().btnShow} onPress={() => unhide($, it.row)} />
                      </Box>
                    )}
              </Box>
            ))}
            {pages > 1 && (
              <Box>
                <Button key="s-prev" label="◂" 
 onPress={async () => {
 await update($, expanded, () => null)
 await update($, sidePage, () => Math.max(0, pageNow - 1))
 }} />
                <Text dimColor>{` ${pageNow + 1}/${pages} `}</Text>
                <Button key="s-next" label="▸" 
 onPress={async () => {
 await update($, expanded, () => null)
 await update($, sidePage, () => Math.min(pages - 1, pageNow + 1))
 }} />
              </Box>
            )}
          </Box>
        )}
        {log[0] && <Text dimColor wrap="truncate-end">{log[0]}</Text>}
      </Box>
    )
  }

  return (
    <Box flexDirection="column" borderStyle={inChat ? 'round' : undefined} borderDimColor paddingX={inChat ? 1 : 0}>
      <Box>
        <Text dimColor>{`${T().asOf} `}</Text>
        <Text dimColor>
          {v ? `${v.collectedAt}${v.isFull ? '' : ` ${T().noTracker}`}` : T().loading}
          {busy ? ` · ${T().loadingWhat(busy)}` : ''}
        </Text>
        <Box flexGrow={1} />
        <Box flexShrink={0}>
          <Button key="reload" label={T().btnReload} onPress={() => startLoad($, 'full')} />
          <Text>   </Text>
          <Button key="all" label={all ? T().btnCompact : T().btnAll} selected={all} onPress={() => update($, showAll, x => !x)} />
          <Text>   </Text>
          {v && (
            <Button key="overview" label={T().btnSort} 
 onPress={() => ask($, overview(v, lay.sections.flatMap(s => s.all)))} />
          )}
          {v && <Text>   </Text>}
          {v && (
            <Button key="plan" label={T().btnPlan} 
 onPress={async () => ask($, planDay(v, lay.sections.flatMap(s => s.all),
 (await read($, tabs)).filter(t => isWaiting(t, v))))} />
          )}
          {v && <Text>   </Text>}
          <Button key="evening" label={T().btnEvening} 
 onPress={async () => ask($, evening(await read($, tabs), await read($, tabSeen), await $.clock.now()))} />
          <Text>   </Text>
          {inChat && <Button key="pane" label={T().btnSidebar} onPress={() => openPane($)} />}
          {inChat && <Text>   </Text>}
          <Button key="help" label="?" selected={help} onPress={() => update($, showHelp, x => !x)} />
          <Text>   </Text>
          <Button key="close" role="dismiss" label="✕" 
 onPress={() => (inChat ? update($, isClosed, () => true) : $.ui.close({ id: PANE }))} />
        </Box>
      </Box>
      {pageBar}
      <Text wrap="truncate-end">
        {hasTabs && <Text color={waiting.length ? 'yellow' : 'green'} bold>{T().tabsWaiting(waiting.length)}</Text>}
        {hasTabs && longCount > 0 && <Text color="red">{` ${T().longCount(longCount)}`}</Text>}
        {hasTabs && <Text color="green">{`   ${T().workingCount(busyTabs)}`}</Text>}
        <Text dimColor>{`${hasTabs ? '   ' : ''}${T().counts(byId.now.all.length, give.all.length, byId.work.all.length,
          laterSection.all.length + lay.hiddenRows.length)}`}</Text>
      </Text>
      {tabErr && <Text color="red" wrap="truncate-end">{tabErr}</Text>}
      {v?.headline && <Text wrap="truncate-end">{v.headline}</Text>}
      {v && !busy && lay.sections.every(x => x.all.length === 0) && waiting.length === 0 && (
        <Text dimColor wrap="wrap">{T().emptyHint}</Text>
      )}
      {v && v.agenda.length > 0 && (
        <Text dimColor wrap="truncate-end">{T().agenda}{v.agenda.slice(0, 3).map(a => `${a.when} ${a.title}`).join(' · ')}</Text>
      )}
      {alarmPage && (
        <Box>
          <Text color="red">{`${T().alarmUnder(alarmCount, alarmPage.title)} `}</Text>
          <Button key="to-alarm" label={T().btnView} onPress={() => goPage(alarmPage.id)} />
        </Box>
      )}
      {helpBox}
      {showOv && ovList.length > 0 && overviewBox(true)}

      {pickedRows.length > 0 && (
        <Box marginTop={1}>
          <Text bold>{`${T().picked(pickedRows.length)}: `}</Text>
          <Button key="pick-do" label={T().btnDo} variant="primary" onPress={() => doIt($, pickedRows)} />
          <Button key="pick-advise" label={T().btnAdvise} onPress={() => advise($, pickedRows)} />
          <Button key="pick-ws" label={T().btnEachOwnWs} onPress={() => doIt($, pickedRows, 'workspace')} />
          <Button key="pick-clear" label={T().btnClear} onPress={() => update($, selected, () => [])} />
        </Box>
      )}

      {block('now')}
      {block('give')}
      {block('work')}

      {(laterSection.all.length > 0 || lay.hiddenRows.length > 0) && (
        <Box flexDirection="column" marginTop={1}>
          <Box>
            <Box flexShrink={0}>
              <Text bold color={SECTION_COLOR.later}>{T().section.later}</Text>
              <Text dimColor>{` ${laterSection.all.length}${lay.hiddenRows.length ? T().hiddenCount(lay.hiddenRows.length) : ''} `}</Text>
              <Button key="later-toggle" label={`${laterOpen ? T().btnClose : T().btnShow} `} onPress={() => setSection('later')} />
            </Box>
            <Box flexGrow={1} width={0} height={1} overflow="hidden"><Text dimColor>{RULE}</Text></Box>
          </Box>
          {laterOpen && laterSection.shown.map(row => rowLine(row, numberOf(row)))}
          {laterOpen && lay.hiddenRows.map(row => (
            <Box key={`hidden-${row.key}`}>
              <Text dimColor>{`      ${short(row.title, width - 40)} · ${T().hiddenUntil(hide[row.key] ?? '')} `}</Text>
              <Button key={`unhide-${row.key}`} label={T().btnShowAgain} onPress={() => unhide($, row)} />
            </Box>
          ))}
        </Box>
      )}

      {hasTabs && <Box marginTop={1} flexWrap="wrap">
        <Button key="tabs-toggle" label={tabsOpen ? T().tabsClose : T().tabsAll(tabList.length)} 
 onPress={() => update($, showTabs, x => !x)} />
        {inCmux && <Text dimColor>{`   ${backupText}: `}</Text>}
        {inCmux && <Button key="snap-now" label={T().btnSave} onPress={() => snapshot($, true)} />}
        {inCmux && <Text dimColor> · </Text>}
        {inCmux && <Button key="snap-list" label={snapList ? T().btnClose : T().btnList} 
 onPress={async () => ((await read($, snapshots)) ? update($, snapshots, () => null) : listSnapshots($))} />}
      </Box>}
      {tabsOpen && tabList.filter(t => !waiting.includes(t)).map(tabLine)}
      {snapList && (
        <Box flexDirection="column" paddingLeft={2}>
          {snapList.map((line, i) => <Text key={`snap-${i}`} dimColor>{short(line, width - 2)}</Text>)}
          <Text dimColor>{T().restoreHint}</Text>
        </Box>
      )}

      {(all ? log : log.slice(0, 1)).map((line, i) => (
        <Text key={`note-${i}`} dimColor>{short(line, width)}</Text>
      ))}
    </Box>
  )
}

// ---------------------------------------------------------------- Module

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const started = await next(e)
    const found = await loadConfig($)
    const loaded = 'cfg' in found ? found.cfg : null
    await update($, configError, () => ('error' in found ? found.error : null))
    // A tab that the bridge started for an item stays quiet: no band, no beat, no greeting.
    const isAgentTab = Boolean(await $.env.get('BRIDGE_TAB_SLUG'))
    const cfg = loaded && isAgentTab ? { ...loaded, band: false, morningHint: false } : loaded
    await update($, config, () => cfg)
    if (!cfg) {
      // Installed but switched off, in a Bridge: /briefing-ui still answers, with how to switch it on.
      // Outside a Bridge the mod stays silent and registers nothing.
      const cwd = await $.session.cwd()
      if (await $.fs.exists(`${cwd}/bridge-config.yaml`)) {
        await $.command.register({ name: 'briefing-ui', description: T().cmdDesc })
      }
      return started
    }
    // The help follows the configured language; its switcher holds until the next load.
    await update($, helpLang, () => cfg.language)

    const stored = (await $.store.get(STORE_VIEW)) as View | undefined
    if (stored && (await read($, view)) === null) await update($, view, () => stored)
    const today = isoDate(await $.clock.now())
    const kept = Object.fromEntries(
      Object.entries(((await $.store.get(STORE_HIDDEN)) ?? {}) as Record<string, string>).filter(([, d]) => d > today),
    )
    await update($, hidden, () => kept)
    // Older versions stored only the team name; that counts as "nothing started yet".
    const storedTeams = ((await $.store.get(STORE_TEAMS)) ?? {}) as Record<string, unknown>
    const chosenTeams = Object.fromEntries(Object.entries(storedTeams).filter(
      ([, v]) => typeof v === 'object' && v !== null && Array.isArray((v as TeamRun).roles))) as Record<string, TeamRun>
    await update($, teamOf, () => chosenTeams)

    await $.command.register({
      name: 'briefing-ui',
      description: T().cmdDesc,
    })
    await $.command.register({
      name: 'briefing-ui-off',
      description: T().cmdOffDesc,
    })

    if (isAgentTab) return started
    // Only after the start: the session does not wait for cmux.
    $.clock.after(0, () => void loadTabs($, cfg))
    $.clock.every(cfg.statusSeconds * 1000, () => {
      void loadTabs($, cfg)
    })
    // The layout backup saves cmux workspaces: a session outside cmux has none to save.
    if (cfg.snapshotMinutes > 0 && (await $.env.get('CMUX_SURFACE_ID'))) {
      // Save only in the control workspace (or if none is known): otherwise every session saves the same thing.
      const maybeSnap = async () => {
        if ((await read($, isControl)) !== false) await snapshot($, false)
      }
      $.clock.after(60000, () => void maybeSnap())
      $.clock.every(cfg.snapshotMinutes * 60000, () => void maybeSnap())
    }

    if (cfg.morningHint) {
      if ((await $.store.get(STORE_DAY)) !== today) {
        await $.store.set(STORE_DAY, today)
        $.ui.toast(T().morning)
      }
    }
    return started
  })

  on('command.run', { command: 'briefing-ui' }, async $ => {
    const cfg = await read($, config)
    if (!cfg) {
      const error = await read($, configError)
      return { text: error === null ? T().cmdDisabled : T().readFailed(error) }
    }
    startLoad($, 'auto')
    void loadTabs($, cfg)
    const id = String(await $.clock.now())
    await update($, cardId, () => id)
    await update($, isClosed, () => false)
    if (cfg.surface === 'pane') await openPane($)
    return { text: T().cmdOutput(id) }
  })

  on('command.run', { command: 'briefing-ui-off' }, async $ => {
    await update($, isBandHidden, () => true)
    return { text: T().bandOff }
  })

  // Shortcuts like "1a 3b 4v" without a model turn, numbers as on the card:
  // a Do it yourself, b Later (tomorrow), c Away, v Advise me, w Do it yourself in own workspace.
  on('prompt.submit', async ($, e, next) => {
    const cfg = await read($, config)
    const text = e.text.trim().toLowerCase()
    if (!cfg?.shortcuts || !SHORTCUT.test(text)) return next(e)
    const v = await read($, view)
    const now = await $.clock.now()
    // Only if the dashboard is open in this session and is from today: otherwise "2b"
    // might be the answer to a question in the conversation and not a click on row 2.
    const isShown = (await read($, cardId)) !== null && !(await read($, isClosed))
    // Only on the briefing tab: on another the numbers are not visible.
    if (!v || !isShown || isoDate(v.collectedMs) !== isoDate(now) || (await read($, page)) !== 'briefing') return next(e)
    const tabList = await read($, tabs)
    const rows = layout(v, await read($, settled), await read($, hidden), isoDate(now),
      await read($, openSection), await read($, showAll), tabList).numbered
    const said: string[] = []
    const groups: Record<'do' | 'advise' | 'ws', Row[]> = { do: [], advise: [], ws: [] }
    for (const code of text.split(/\s+/)) {
      const n = Number(code.slice(0, -1))
      const letter = code.slice(-1)
      const row = rows[n - 1]
      if (!row) {
        said.push(T().scMissing(n))
        continue
      }
      const open = tabFor(row, tabList)
      if (open && isLive(open) && 'avw'.includes(letter)) {
        // has a tab already: jump to it instead of starting a second one
        await jump($, open)
        said.push(T().scHasTab(n, short(row.title, 30)))
      } else if ('aw'.includes(letter) && ((row.inboxId && row.gate === 'only-you') || row.bucket === 'waiting'
        || row.inboxState === 'approved')) {
        // the same limits as the buttons of the card
        said.push(`${n} (${short(row.title, 30)}): ${row.inboxState === 'approved' ? T().scApproved
          : row.bucket === 'waiting' ? T().scWaiting : T().scOnlyYou}`)
      } else if (letter === 'b') said.push(`${n} (${short(row.title, 30)}) ${await later($, row, isoDate(now + DAY))}`)
      else if (letter === 'c') said.push(`${n} (${short(row.title, 30)}) ${await drop($, row)}`)
      else if (letter === 'v') groups.advise.push(row)
      else if (letter === 'w') groups.ws.push(row)
      else groups.do.push(row)
    }
    if (groups.do.length) said.push(`${groups.do.length} ${await doIt($, groups.do)}`)
    if (groups.ws.length) said.push(`${groups.ws.length} ${await doIt($, groups.ws, 'workspace')}`)
    if (groups.advise.length) said.push(`${groups.advise.length} ${await advise($, groups.advise)}`)
    return { drop: T().scResult(said.join(' · ')) }
  })

  // The whole dashboard as a card in the conversation: the output line of /briefing-ui.
  on('ui.render', { component: 'CommandOutput' }, async ($, e, next) => {
    if (!e.props.command.endsWith('briefing-ui') || e.props.isErrored || !(await read($, config))) return next(e)
    const resolved = $.ui.resolve(e)
    const { Box, Text } = resolved
    const Button = framed(resolved.Button, Text)
    const id = CARD_ID.exec(e.props.text)?.[1] ?? null
    // Only the newest card is the dashboard; older lines in the history become one line.
    if (id !== (await read($, cardId))) {
      return <Text dimColor>{T().olderCard(id ? clockTime(Number(id)) : T().earlier)}</Text>
    }
    if (await read($, isClosed)) {
      const tabList = await read($, tabs)
      const cur = await read($, view)
      const waiting = tabList.filter(t => isWaiting(t, cur)).length
      return (
        <Box>
          <Text dimColor>{`${T().closedCard(waiting)} `}</Text>
          <Button key="reopen" label={T().btnReopen} onPress={() => update($, isClosed, () => false)} />
        </Box>
      )
    }
    return dashboard($, e, e.viewport?.columns ?? 100, true, e.viewport?.rows ?? 40)
  })

  // Band above the prompt: the numbers worth a glance, and a button to the card.
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const cfg = await read($, config)
    if (!cfg?.band || e.props.hasSurvey || (await read($, isBandHidden))) return next(e)
    const tabList = await read($, tabs)
    const cur = await read($, view)
    const lay = layout(cur, await read($, settled), await read($, hidden),
      isoDate(await $.clock.now()), null, false, tabList)
    const now = await $.clock.now()
    const seen = await read($, tabSeen)
    const waiting = tabList.filter(t => isWaiting(t, cur)).length
    const longCount = tabList.filter(t => longText(t, seen, now) !== null).length
    const nowCount = lay.sections[0]?.all.length ?? 0
    const giveCount = lay.sections[1]?.all.length ?? 0
    if (waiting + longCount + nowCount + giveCount === 0) return next(e)
    const resolved = $.ui.resolve(e)
    const { Box, Text } = resolved
    const Button = framed(resolved.Button, Text)
    // Half width: the same numbers in short form, so the band stays one line.
    const isShort = (e.viewport?.columns ?? 120) < 90
    return (
      <Box>
        <Text color={waiting ? 'yellow' : undefined}>{isShort ? T().bandShort(waiting) : T().bandLong(waiting)}</Text>
        {longCount > 0 && <Text color="red">{T().bandLongCount(longCount)}</Text>}
        <Text dimColor>{isShort ? T().bandCountsShort(nowCount, giveCount) : T().bandCountsLong(nowCount, giveCount)}</Text>
        <Button key="open" label={T().btnDashboard}
 onPress={async () => {
 await $.command.run({ command: 'briefing-ui' })
 }} />
        <Text> </Text>
        <Button key="hide" label="✕" onPress={() => update($, isBandHidden, () => true)} />
      </Box>
    )
  })

  // Width and height of the panel itself, not of the terminal: the conversation sits beside it.
  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) =>
    dashboard($, e, e.props.bodyColumns || 40, false, e.props.scroll.bodyRows || 30))
}
