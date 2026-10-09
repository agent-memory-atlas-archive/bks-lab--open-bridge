import type {
  Bucket, Info, InfoPage, Mark, Review, Row, SectionId, Tab, TabSeen, TaskInfo, Team, TeamRun, UiConfig, View,
} from '../types'
import { T } from './text'

/**
 * Pure functions of the mod: reading the script outputs, ordering of the card, texts to Claude.
 * Nothing here touches `$`; the tests exercise them without Claude Code.
 */

export const ATTENTION = new Set(['needs-you', 'waiting'])

/** State of a tab in words */
export function stateWord(state: string): string {
  return T().state[state] ?? state
}

/** Color of the dot before a tab: needs you red, waits yellow, works green, terminal gray */
export function tabColor(tab: Tab): string {
  return tab.state === 'needs-you' ? 'red' : tab.state === 'waiting' ? 'yellow' : tab.state === 'working' ? 'green' : 'gray'
}
export const BUCKET_ORDER = ['do', 'plan', 'delegate', 'waiting', 'drop', 'tasks', 'resting']
export const SHORTCUT = /^(\d+[abcvw])(\s+\d+[abcvw])*$/

/** Rows per block in the compact view; Later stays closed. */
export const CAP: Record<SectionId, number> = { now: 4, give: 4, work: 5, later: 0 }

/** Status tabs: which sections sit on which tab and what goes in which column is set by the
 * briefing profile (view.pages, docs/briefings.md § Dashboard pages); collect delivers them ready. */
export const BRIEFING_PAGE = 'briefing'

export function parseMark(x: unknown): Mark | null {
  const m = x as Record<string, unknown> | null
  if (!m || typeof m !== 'object' || typeof m.label !== 'string' || !m.label) return null
  return { label: m.label, color: typeof m.color === 'string' ? m.color : null }
}

export function parseInfo(i: Record<string, unknown>): Info {
  const tone = i.tone === 'bad' || i.tone === 'warn' || i.tone === 'dim' ? i.tone : null
  const lines = (Array.isArray(i.lines) ? i.lines as Record<string, unknown>[] : [])
    .filter(l => l && typeof l.kind === 'string' && typeof l.text === 'string' && l.text)
    .map(l => ({ kind: asText(l.kind), text: asText(l.text) }))
  return { title: asText(i.title), detail: asText(i.detail), when: asText(i.when), tone, url: asTextOrNull(i.url),
    task: asTextOrNull(i.task), ask: i.ask === true, mark: parseMark(i.mark), priority: asTextOrNull(i.priority),
    state: asTextOrNull(i.state), lines }
}

/** A task as a row, so a status tab takes the same paths as the card (find tab, start tab) */
export function taskRow(slug: string, title: string): Row {
  return { key: `task:${slug}`, bucket: 'do', title, why: [], sources: [], inboxId: null, gate: null, task: slug,
    ref: null, url: null, priority: null, urgency: null, area: null, areaNames: [], taskType: null, hasAction: false,
    inboxState: null, inboxKey: null, mark: null }
}

/** A task as a full row from the task list (area, priority, type, why it rests), as the card has it */
export function taskRowFor(slug: string, title: string, list: TaskInfo[]): Row {
  const t = list.find(x => x.slug === slug)
  if (!t) return taskRow(slug, title)
  const why = t.blockedBy ? [T().blocked(t.blockedBy)] : t.stale ? [T().quietFor(t.age)] : []
  return { ...taskRow(slug, title || t.label), why, sources: ['tasks'], priority: t.priority, area: t.area,
    areaNames: t.areaNames, taskType: t.type }
}

/** Question to the conversation about a row of a status tab */
export function askInfo(section: string, it: Info): string {
  const extra = [it.detail, it.url && /^https?:/.test(it.url) ? it.url : ''].filter(Boolean).join(', ')
  return T().askInfo(section, it.title, extra)
}

export function parsePages(data: Record<string, unknown>): InfoPage[] {
  return ((data.pages as Record<string, unknown>[] | undefined) ?? []).map(p => ({
    id: asText(p.id),
    title: asText(p.title),
    sections: ((p.sections as Record<string, unknown>[] | undefined) ?? []).map(x => {
      const items = ((x.items as Record<string, unknown>[] | undefined) ?? []).map(parseInfo)
      return {
        id: asText(x.id),
        kind: asText(x.kind),
        title: asText(x.title),
        status: asText(x.status),
        reason: asText(x.reason),
        alarm: x.alarm === true,
        empty: asText(x.empty) || T().empty,
        items,
        count: items.length,
        weight: typeof x.weight === 'number' ? x.weight : 0,
        bad: typeof x.bad === 'number' ? x.bad : 0,
        asOf: asTextOrNull(x.as_of),
      }
    }),
  })).filter(p => p.id && p.id !== BRIEFING_PAGE && p.sections.length > 0)
}

/** Number on the tab: red findings, else what counts (yellow, if they are findings), else ✓ */
export function pageBadge(pg: InfoPage): { text: string; color?: string } {
  const bad = pg.sections.reduce((n, x) => n + x.bad, 0)
  if (bad > 0) return { text: `✗${bad}`, color: 'red' }
  const weight = pg.sections.reduce((n, x) => n + x.weight, 0)
  const isWarn = pg.sections.some(x => x.weight > 0 && x.items.some(it => it.tone === 'warn'))
  if (weight > 0) return { text: String(weight), color: isWarn ? 'yellow' : undefined }
  return pg.sections.every(x => x.status === 'ok') ? { text: '✓', color: 'green' } : { text: '' }
}

// ---------------------------------------------------------------- Helpers

export function short(text: string, max: number): string {
  const line = text.replace(/\s+/g, ' ').trim()
  return line.length > max ? line.slice(0, Math.max(1, max - 1)) + '…' : line
}

export function pad(n: number): string {
  return String(n).padStart(2, '0')
}

export function isoDate(ms: number): string {
  const d = new Date(ms)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function clockTime(ms: number): string {
  const d = new Date(ms)
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export const DAY = 86400000

export function nextMonday(ms: number): number {
  const day = new Date(ms).getDay()
  return ms + ((8 - day) % 7 || 7) * DAY
}

/** "2026-10-14", "14.10." or "14.10.2026" as YYYY-MM-DD; else null. */
export function parseDate(text: string, now: number): string | null {
  const t = text.trim()
  if (/^\d{4}-\d{2}-\d{2}$/.test(t)) return isoDate(new Date(`${t}T12:00:00`).getTime()) === t ? t : null
  const m = /^(\d{1,2})\.(\d{1,2})\.?(\d{4})?$/.exec(t)
  if (!m) return null
  const year = m[3] ? Number(m[3]) : new Date(now).getFullYear()
  const probe = new Date(year, Number(m[2]) - 1, Number(m[1]))
  if (probe.getMonth() !== Number(m[2]) - 1 || probe.getDate() !== Number(m[1])) return null   // 31.02., 99.99. (invalid dates)
  const date = `${year}-${pad(Number(m[2]))}-${pad(Number(m[1]))}`
  // without a year and already past: next year
  return !m[3] && date < isoDate(now) ? `${year + 1}-${pad(Number(m[2]))}-${pad(Number(m[1]))}` : date
}

export function asText(value: unknown): string {
  return typeof value === 'string' ? value : value == null ? '' : String(value)
}

export function asTextOrNull(value: unknown): string | null {
  return typeof value === 'string' && value !== '' ? value : null
}

export function rowKey(row: Omit<Row, 'key'>): string {
  if (row.inboxId) return `inbox:${row.inboxId}`
  if (row.task) return `task:${row.task}`
  if (row.ref) return `ref:${row.ref}`
  return `title:${row.title.slice(0, 60)}`
}

/** What a new tab can take over: an inbox entry or a task. */
export function launchItem(row: Row): string | null {
  return row.inboxId ?? row.task
}

export function githubUrl(ref: string | null): string | null {
  const m = ref ? /^([\w.-]+\/[\w.-]+)#(\d+)$/.exec(ref) : null
  return m ? `https://github.com/${m[1]}/issues/${m[2]}` : null
}

export function rowUrl(row: Row): string | null {
  if (row.url && /^https?:\/\//.test(row.url)) return row.url
  return githubUrl(row.ref)
}

export function parseView(raw: unknown, isFull: boolean, now: number): View {
  const data = (raw ?? {}) as Record<string, unknown>
  const v = (data.view ?? {}) as Record<string, unknown>
  const buckets: Bucket[] = []
  const seenKeys = new Set<string>()
  for (const b of (v.buckets as Record<string, unknown>[] | undefined) ?? []) {
    const rows: Row[] = []
    for (const i of (b.items as Record<string, unknown>[] | undefined) ?? []) {
      const base = {
        bucket: asText(b.id),
        title: asText(i.title),
        why: Array.isArray(i.why) ? i.why.map(asText).filter(Boolean) : [],
        sources: Array.isArray(i.sources) ? i.sources.map(asText) : [],
        inboxId: asTextOrNull(i.inbox_id),
        gate: asTextOrNull(i.gate),
        task: asTextOrNull(i.task),
        ref: asTextOrNull(i.ref),
        url: asTextOrNull(i.url),
        priority: asTextOrNull(i.priority),
        urgency: asTextOrNull(i.urgency),
        area: null,
        areaNames: [],
        taskType: null,
        hasAction: i.has_action === true,
        inboxState: asTextOrNull(i.inbox_state),
        inboxKey: asTextOrNull(i.inbox_key),
        mark: parseMark(i.mark),
      }
      // Same key twice (same number from two trackers): the second gets the block added.
      const key = rowKey(base)
      rows.push({ ...base, key: seenKeys.has(key) ? `${key}@${base.bucket}:${rows.length}` : key })
      seenKeys.add(key)
    }
    buckets.push({ id: asText(b.id), title: asText(b.title), rows })
  }
  buckets.sort((a, b) => BUCKET_ORDER.indexOf(a.id) - BUCKET_ORDER.indexOf(b.id))
  const agenda = ((v.agenda as Record<string, unknown>[] | undefined) ?? [])
    .filter(a => !a.info)
    .map(a => ({ when: asText(a.when), title: asText(a.title) }))
  const status = ((v.status as Record<string, unknown>[] | undefined) ?? []).map(s => ({
    title: asText(s.title),
    count: typeof s.count === 'number' ? s.count : 0,
    isHealthy: s.health !== false,
  }))
  return {
    headline: asText(v.headline),
    collectedAt: clockTime(now),
    collectedMs: now,
    isFull,
    fullMs: isFull ? now : 0,
    skipped: ((data.sections as Record<string, unknown>[] | undefined) ?? [])
      .filter(x => x.status === 'skipped').map(x => asText(x.id)),
    buckets,
    agenda,
    status,
    pages: parsePages(data),
  }
}

export function parseConfig(raw: Record<string, unknown>): UiConfig {
  const launch = (raw.launch ?? {}) as Record<string, unknown>
  const seconds = typeof raw.status_seconds === 'number' ? raw.status_seconds : 60
  const where = launch.target
  return {
    enabled: raw.enabled === true,
    band: raw.band !== false,
    shortcuts: raw.shortcuts !== false,
    morningHint: raw.morning_hint !== false,
    voice: raw.voice === true,
    statusSeconds: Math.max(15, seconds),
    fullMinutes: typeof raw.full_minutes === 'number' ? Math.max(1, raw.full_minutes) : 10,
    target: where === 'tab' || where === 'workspace' || where === 'auto' ? where : 'area',
    surface: raw.surface === 'pane' ? 'pane' : 'chat',
    snapshotMinutes: typeof raw.snapshot_minutes === 'number' ? Math.max(0, raw.snapshot_minutes) : 60,
    control: typeof raw._control === 'string' && raw._control ? raw._control : null,
    // own setting before language.conversation; without both, English
    language: languageOf(typeof raw.language === 'string' && raw.language ? raw.language : raw._language),
  }
}

export function languageOf(value: unknown): 'de' | 'en' {
  return typeof value === 'string' && value.toLowerCase().startsWith('de') ? 'de' : 'en'
}

export type { TaskInfo }

export function parseTasks(out: string): TaskInfo[] {
  return (JSON.parse(out) as Record<string, unknown>[]).map(t => ({
    slug: asText(t.slug),
    label: asText(t.label),
    area: asText(t.area),
    areaNames: [asText(t.area), ...(Array.isArray(t.area_aliases) ? t.area_aliases.map(asText) : [])],
    priority: asTextOrNull(t.priority),
    blockedBy: asTextOrNull(t.blocked_by),
    stale: t.stale === true,
    age: typeof t.age === 'number' ? t.age : 0,
    type: asTextOrNull(t.type),
    isStream: t.kind === 'streams',
  }))
}

const VERDICTS = ['close', 'continue', 'waiting', 'stale', 'unclear'] as const

function toReview(slug: string, r: Record<string, unknown>, cached: boolean): Review {
  const verdict = VERDICTS.find(v => v === r.verdict) ?? 'unclear'
  const sig = (r.signals && typeof r.signals === 'object' ? r.signals : {}) as Record<string, unknown>
  return { slug, verdict, reason: asText(r.reason), confidence: asText(r.confidence), model: asTextOrNull(r.model),
    cached, kept: r.kept === true, resolved: r.resolved === true, unblocked: sig.blocker_resolved === true,
    closedRefs: Array.isArray(sig.closed_refs) ? sig.closed_refs.map(asText) : [] }
}

/** The answer of `task.py review --json`: one recommendation per task, what it cost, which models answered. */
export function parseReview(out: string): { reviews: Record<string, Review>; count: number; toClose: number
  costUsd: number; costKnown: boolean; models: string[]; mismatch: string[] } {
  const raw = JSON.parse(out) as Record<string, unknown>
  const tasks = (Array.isArray(raw.tasks) ? raw.tasks : []) as Record<string, unknown>[]
  const reviews: Record<string, Review> = {}
  for (const t of tasks) if (t && t.slug) reviews[asText(t.slug)] = toReview(asText(t.slug), t, t.cached === true)
  const mismatch = (Array.isArray(raw.model_mismatch) ? raw.model_mismatch : []) as Record<string, unknown>[]
  return {
    reviews, count: tasks.length,
    toClose: Object.values(reviews).filter(r => (r.verdict === 'close' || r.resolved) && !r.kept).length,
    costUsd: typeof raw.cost_usd === 'number' ? raw.cost_usd : 0,
    costKnown: raw.cost_known !== false,
    models: Array.isArray(raw.models_used) ? raw.models_used.map(asText) : [],
    mismatch: mismatch.map(m => `${asText(m.requested)} → ${(Array.isArray(m.used) ? m.used.map(asText) : []).join(', ')}`),
  }
}

/** The cache file of `task.py review` (.bridge/task-review.json): the last verdicts, without asking a model. */
export function parseReviewCache(text: string): Record<string, Review> {
  try {
    const raw = JSON.parse(text) as { tasks?: Record<string, Record<string, unknown>> }
    const out: Record<string, Review> = {}
    for (const [slug, r] of Object.entries(raw.tasks ?? {})) if (r && typeof r === 'object') out[slug] = toReview(slug, r, true)
    return out
  } catch {
    return {}
  }
}

/** claude-haiku-5-5 → Haiku 5.5; anything else stays as it is */
export function modelShort(id: string | null): string {
  if (!id) return '?'
  const m = /^claude-([a-z]+)-(\d+)-(\d+)(?:-\d{8})?$/.exec(id)
  return m ? `${m[1]!.charAt(0).toUpperCase()}${m[1]!.slice(1)} ${m[2]}.${m[3]}` : id
}

export function parseTeams(out: string): Team[] {
  return (JSON.parse(out) as Record<string, unknown>[]).map(t => ({
    id: asText(t.id),
    label: asText(t.label),
    forTypes: Array.isArray(t.for_types) ? t.for_types.map(asText) : [],
    roles: ((t.roles as Record<string, unknown>[] | undefined) ?? []).map(r => ({
      id: asText(r.id),
      name: asText(r.name),
      mode: r.mode === 'report' ? 'report' as const : 'go' as const,
    })),
  }))
}

/**
 * All active tasks onto the card: rows of the briefing with a task get
 * their area, the remaining tasks come in as rows of their own (dormant ones extra).
 */
export function withTasks(v: View, list: TaskInfo[]): View {
  const bySlug = new Map(list.map(t => [t.slug, t]))
  const seen = new Set<string>()
  const inboxCount = new Map<string, number>()
  const buckets = v.buckets.filter(b => b.id !== 'tasks' && b.id !== 'resting').map(b => ({
    ...b,
    rows: b.rows.map(r => {
      const t = r.task ? bySlug.get(r.task) : undefined
      if (!t) return r
      // An inbox entry is a part of its task, never the task itself: the task keeps its own row.
      if (r.inboxId) inboxCount.set(t.slug, (inboxCount.get(t.slug) ?? 0) + 1)
      else seen.add(t.slug)
      // An inbox entry shows the area of its task, but not its priority.
      return { ...r, area: t.area, areaNames: t.areaNames, priority: r.inboxId ? r.priority : r.priority ?? t.priority, taskType: t.type }
    }),
  }))
  const toRow = (t: TaskInfo, bucket: string): Row => {
    const why = t.blockedBy ? [T().blocked(t.blockedBy)] : t.stale ? [T().quietFor(t.age)] : []
    if (inboxCount.get(t.slug)) why.push(T().inboxOpen(inboxCount.get(t.slug) ?? 0))
    const base = { bucket, title: t.label, why, sources: ['tasks'], inboxId: null, gate: null, task: t.slug,
      ref: null, url: null, priority: t.priority, urgency: null, area: t.area, areaNames: t.areaNames, taskType: t.type, hasAction: false,
      inboxState: null, inboxKey: null, mark: null }
    return { ...base, key: rowKey(base) }
  }
  const rest = list.filter(t => !seen.has(t.slug))
  const active = rest.filter(t => !t.blockedBy && !t.stale).map(t => toRow(t, 'tasks'))
  const resting = rest.filter(t => t.blockedBy || t.stale).map(t => toRow(t, 'resting'))
  if (active.length) buckets.push({ id: 'tasks', title: T().bucketTasks, rows: active })
  if (resting.length) buckets.push({ id: 'resting', title: T().bucketResting, rows: resting })
  return { ...v, buckets }
}

// ---------------------------------------------------------------- Order of the card

export function prioRank(row: Row): number {
  const m = row.priority ? /^P(\d)$/.exec(row.priority) : null
  return m ? Number(m[1]) : 4
}

export function urgencyRank(row: Row): number {
  return row.urgency === 'now' ? 0 : row.urgency === 'today' ? 1 : 2
}

/** Which block an open row belongs in. */
export function classify(row: Row): SectionId {
  if (row.urgency === 'now' || row.urgency === 'today' || row.bucket === 'do') return 'now'
  if (row.bucket === 'drop' || row.bucket === 'waiting' || row.bucket === 'resting') return 'later'
  if (row.inboxId) return row.gate === 'your-yes' || row.gate === 'free' ? 'give' : 'later'
  if (row.task || row.ref) return 'work'
  return 'later'
}

/** The inbox entry that a tab filed for its task (key tab-<slug>-...) */
export function filedBy(tab: Tab, v: View | null): Row | undefined {
  if (!tab.slug || !v) return undefined
  const prefix = `tab-${tab.slug}-`
  // The tab files with --task <slug>; only without a task does the key count (open-bridge is the start of open-bridge-x).
  return v.buckets.flatMap(b => b.rows).find(r => r.inboxId !== null && (r.inboxKey ?? '').startsWith(prefix)
    && (r.task === null || r.task === tab.slug))
}

/** Does the tab really wait for you? A finished tab whose result sits in the inbox no longer does. */
export function isWaiting(tab: Tab, v: View | null): boolean {
  if (tab.state === 'needs-you') return true
  return tab.state === 'waiting' && filedBy(tab, v) === undefined
}

/** Does an agent run in the tab? A tab in state shell holds none: its command never ran, or the agent ended. */
export function isLive(tab: Tab): boolean {
  return tab.state !== 'shell'
}

/** The tab of a row: one that waits for you first, then any live one, a dead shell tab only as the last resort. */
export function tabFor(row: Row, list: Tab[]): Tab | undefined {
  const mine = list.filter(t => (row.task !== null && t.slug === row.task) || (row.inboxId !== null && t.item === row.inboxId))
  return mine.find(t => ATTENTION.has(t.state)) ?? [...mine].reverse().find(isLive) ?? mine[mine.length - 1]
}

export type TeamState = { team: Team; started: number; next: Team['roles'][number] | null; isReady: boolean
  waitingFor: string | null }

/** From here a tab counts as long: waits an hour for you, or works an hour without end. */
export const LONG_MS = 3600000

export function duration(ms: number): string {
  const min = Math.floor(ms / 60000)
  return min < 60 ? `${min} min` : `${Math.floor(min / 60)}:${pad(min % 60)} h`
}

/** Does a tab wait or run for a conspicuously long time? Then the text for it, else null. */
export function longText(tab: Tab, seen: Record<string, TabSeen>, now: number): string | null {
  const s = seen[tab.ref]
  if (!s || s.state !== tab.state || now - s.since < LONG_MS) return null
  if (ATTENTION.has(tab.state)) return T().waitingFor(duration(now - s.since))
  return tab.state === 'working' ? T().runningFor(duration(now - s.since)) : null
}

/** A freshly started tab needs a moment until cmux reports it; until then the role counts as "starting". */
export const START_GRACE = 90000

/**
 * How far a task's team has got. The card remembers by itself what it started
 * (role names like "Review" exist in several recipes, the tab name alone does not say the team
 * for sure). The next role is due only once the previous one's tab waits; if it is missing
 * for longer than START_GRACE (closed), it carries on anyway.
 */
export function teamState(row: Row, runs: Record<string, TeamRun>, list: Team[], tabList: Tab[], now: number): TeamState | null {
  const run = row.task ? runs[row.task] : undefined
  const team = run ? list.find(t => t.id === run.team) : undefined
  if (!run || !team) return null
  const started = team.roles.filter(r => run.roles.includes(r.id)).length
  const next = team.roles[started] ?? null
  const last = team.roles[started - 1]
  const lastTab = last ? tabList.find(t => t.slug === row.task && t.role === last.id) : undefined
  const isReady = started === 0 || (lastTab ? ATTENTION.has(lastTab.state) : now - run.at > START_GRACE)
  return { team, started, next, isReady, waitingFor: isReady || !last ? null : last.name }
}

export type Section = { id: SectionId; all: Row[]; shown: Row[] }
/** numbered: all rows in card order; numbers: row -> its fixed number (independent of expanding) */
export type Layout = { sections: Section[]; hiddenRows: Row[]; numbered: Row[]; numbers: Map<string, number> }

/**
 * The card as a pure function of the state: the same calculation for drawing
 * and for the shortcuts, so that "3a" hits the row that the 3 stands before.
 */
export function layout(
  v: View | null, done: string[], hide: Record<string, string>, today: string,
  open: SectionId | null, all: boolean, tabList: Tab[],
): Layout {
  const groups: Record<SectionId, Row[]> = { now: [], give: [], work: [], later: [] }
  const hiddenRows: Row[] = []
  const rows = v ? v.buckets.flatMap(b => b.rows.filter(r => !done.includes(r.key))) : []
  for (const row of rows) {
    if ((hide[row.key] ?? '') > today) hiddenRows.push(row)
    else groups[classify(row)].push(row)
  }
  const order = (a: Row, b: Row) => urgencyRank(a) - urgencyRank(b) || prioRank(a) - prioRank(b)
  const sections = (['now', 'give', 'work', 'later'] as const).map(id => {
    const list = [...groups[id]].sort(order)
    if (all || open === id) return { id, all: list, shown: list }
    // Tasks compact: only P0 to P2 and what already has a tab
    const pool = id === 'work' ? list.filter(r => prioRank(r) <= 2 || tabFor(r, tabList)) : list
    return { id, all: list, shown: pool.slice(0, CAP[id]) }
  })
  const numbered = sections.flatMap(s => s.all)
  return { sections, hiddenRows, numbered, numbers: new Map(numbered.map((r, i) => [r.key, i + 1])) }
}

/**
 * Two runs into one view: what `fresh` left out (skipped) comes from `base`, everything else from `fresh`.
 * Rows are taken over by `base` only if all their sections were left out in `fresh`.
 */
export function mergeView(base: View, fresh: View): View {
  const gone = new Set(fresh.skipped)
  const keys = new Set(fresh.buckets.flatMap(b => b.rows.map(r => r.key)))
  const ids = [...new Set([...fresh.buckets.map(b => b.id), ...base.buckets.map(b => b.id)])]
  const buckets = ids.map(id => {
    const b = fresh.buckets.find(o => o.id === id) ?? { ...base.buckets.find(o => o.id === id)!, rows: [] }
    const old = base.buckets.find(o => o.id === id)
    const extra = (old?.rows ?? []).filter(r => r.sources.length > 0 && r.sources.every(src => gone.has(src))
      && !keys.has(r.key))
    return { ...b, rows: [...b.rows, ...extra] }
  }).filter(b => b.rows.length > 0)
  buckets.sort((a, b) => BUCKET_ORDER.indexOf(a.id) - BUCKET_ORDER.indexOf(b.id))
  const baseSections = (base.pages ?? []).flatMap(pg => pg.sections)
  const pages = (fresh.pages ?? []).map(pg => ({
    ...pg,
    sections: pg.sections.map(q => (gone.has(q.id) ? baseSections.find(f => f.id === q.id) ?? q : q)),
  }))
  // The headline counts every row and names the next date: a run that left out sections the earlier
  // one had would undercount, so the earlier headline stays until a run as complete as it comes.
  const freshHasInbox = !fresh.skipped.some(id => id === 'inbox')
  const freshHasCalendar = !fresh.skipped.some(id => id === 'calendar')
  const freshIsPartial = fresh.skipped.some(id => !(base.skipped ?? []).includes(id))
  return {
    ...fresh,
    headline: freshIsPartial ? base.headline : fresh.headline,
    status: freshHasInbox ? fresh.status : base.status,
    agenda: freshHasCalendar ? fresh.agenda : base.agenda,
    isFull: fresh.isFull || base.isFull,
    fullMs: Math.max(fresh.fullMs || 0, base.fullMs || 0),
    // A saved view of an older version does not know skipped yet.
    skipped: fresh.skipped.filter(id => (base.skipped ?? []).includes(id)),
    buckets,
    pages,
  }
}

export function toTab(t: Record<string, unknown>): Tab {
  return {
    name: asText(t.name), workspace: asText(t.workspace), ref: asText(t.ref), wsRef: asText(t.ws_ref),
    state: asText(t.state), last: asText(t.last), slug: asTextOrNull(t.slug), item: asTextOrNull(t.item),
    team: asTextOrNull(t.team), role: asTextOrNull(t.role),
  }
}

export function refNumber(ref: unknown): number {
  const m = /(\d+)$/.exec(asText(ref))
  return m ? Number(m[1]) : Number.MAX_SAFE_INTEGER
}

export function askAbout(row: Row): string {
  const where = row.ref ?? row.url ?? row.task ?? row.inboxId ?? ''
  return T().askAbout(row.title, where)
}

export function followUp(row: Row): string {
  return T().followUp(row.title, row.why.join(', '))
}

export function overview(v: View, rows: Row[]): string {
  const lines = rows.slice(0, 25).map((r, i) => `${i + 1}. [${classify(r)}] ${short(r.title, 140)}`)
  return [T().overviewHead(v.collectedAt, v.headline), ...lines, T().overviewTail].join('\n')
}

/** Plan for today: appointments, inbox, tasks and waiting tabs as one assignment to Claude */
export function planDay(v: View, rows: Row[], waiting: Tab[]): string {
  const agenda = v.agenda.map(a => `- ${a.when} ${short(a.title, 80)}`)
  const lines = rows.slice(0, 30).map((r, i) =>
    `${i + 1}. [${classify(r)}${r.priority ? ` ${r.priority}` : ''}${r.mark ? ` ${r.mark.label}` : ''}] ${short(r.title, 120)}`)
  const tabs = waiting.map(t => `- ${t.workspace} / ${t.name}: ${stateWord(t.state)}`)
  return [
    T().planHead(v.collectedAt, v.headline),
    ...(agenda.length ? [T().planAgenda, ...agenda] : []),
    T().planRows, ...lines,
    ...(tabs.length ? [T().planTabs, ...tabs] : []),
    T().planTail,
  ].join('\n')
}

/** End of day with the open agent tabs: what of them stays open overnight belongs in the report. */
export function evening(list: Tab[], seen: Record<string, TabSeen>, now: number): string {
  const open = list.filter(t => t.state !== 'shell')
  if (open.length === 0) return T().evening
  const lines = open.map(t => `- ${t.workspace} / ${t.name}: ${stateWord(t.state)}` +
    `${seen[t.ref] ? T().eveningSince(duration(now - seen[t.ref]!.since)) : ''}${t.last ? T().eveningLast(short(t.last, 80)) : ''}`)
  return [T().evening, T().eveningTabs, ...lines].join('\n')
}
