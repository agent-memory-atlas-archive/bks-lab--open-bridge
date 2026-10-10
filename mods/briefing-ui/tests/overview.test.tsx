// The review overview: strip, filter chips, comparable rows, selection and bulk actions.
import { test, expect } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import { cardProps, collect, openCard, world } from './world'

const WIDE = { columns: 160, rows: 80 }
const t = (slug: string, verdict: string, extra: Record<string, unknown> = {}) => ({
  slug, title: `${slug} work`, verdict, reason: `${slug} reason`, confidence: 'medium', model: 'claude-haiku-5-5',
  cached: true, kept: false, resolved: false, signals: { own_refs_closed: false, blocker_resolved: false, closed_refs: [] },
  status: 'doing', priority: 'P2', days_since_activity: 4, chips: [], previous_verdict: null, changed: false, ...extra })
const RUN = {
  tasks: [
    t('alpha', 'continue', { resolved: true, priority: 'P1', days_since_activity: 6,
      signals: { own_refs_closed: true, blocker_resolved: true, closed_refs: ['example-org/x#49 2026-10-03'] },
      chips: [{ kind: 'ref', ref: 'example-org/x#49', state: 'closed', date: '2026-10-03' }, { kind: 'unblocked' },
        { kind: 'steps', count: 3 }, { kind: 'inbox', count: 2 }] }),
    t('beta', 'stale', { previous_verdict: 'continue', changed: true, priority: 'P3', days_since_activity: 40 }),
    t('gamma', 'waiting', { priority: 'P0', days_since_activity: 2 }),
    t('delta', 'continue', { days_since_activity: 1 }),
    t('eps', 'unclear', { confidence: 'low', days_since_activity: null }),
    t('zeta', 'stale', { priority: 'P1', days_since_activity: 30 }),
  ],
  cost_usd: 0.009, cost_known: true, models_used: ['claude-haiku-5-5', 'claude-sonnet-5-5'], model_mismatch: [],
  reviewed: 6, to_close: 1, reviewed_at: '2026-10-09T07:55:00', duration_sec: 24.4, escalate_call_usd: 0.021,
}
const CACHE = JSON.stringify({ version: 1, tasks: {}, last: RUN })
const TASKS = RUN.tasks.map(x => ({ slug: x.slug, label: x.title, area: 'acme', area_aliases: [], priority: x.priority,
  blocked_by: null, stale: false, age: 0, type: 'feature', kind: 'tasks' }))
const TASK_PAGE = { id: 'tasks', title: 'Tasks', sections: [{ id: 'tasks', kind: 'tasks', title: 'Tasks', status: 'ok',
  reason: '', alarm: false, empty: 'nothing', total: 1, weight: 1, bad: 0, as_of: null, items: [
    { title: 'alpha work', when: '07.10', detail: '', tone: null, url: null, task: 'alpha', ask: false, mark: null,
      priority: 'P1', state: 'doing', lines: [] }] }] }

type Opts = Parameters<typeof world>[1]
function setup(on: Parameters<typeof world>[0], lang: 'de' | 'en' = 'de', extra: Opts = {}) {
  return world(on, { language: lang, tasks: TASKS, collect: collect({ pages: [TASK_PAGE] }),
    files: { '.bridge/task-review.json': CACHE }, taskPy: () => ({ stdout: '{}' }), ...extra })
}
async function page($: Engine, w: ReturnType<typeof world>, viewport = WIDE) {
  const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
    props: cardProps(await openCard($, w)), viewport })
  await ui.press({ key: 'pgb-tasks' })
  return ui
}
const rowsOf = async (ui: Awaited<ReturnType<typeof page>>) =>
  (await ui.findAll({ type: 'Button' })).map(b => b.key ?? '').filter(k => k.startsWith('ov-pick-'))
    .map(k => k.slice('ov-pick-'.length))
const taskCalls = (calls: string[][], sub: string) => calls.filter(a => a[1] === 'scripts/task.py' && a[2] === sub)
  .map(a => a.slice(2))

test('the strip counts the verdicts with words, names cost, models, duration and age, with no model call', async ($, on) => {
  const w = setup(on)
  const ui = await page($, w)
  expect(await ui.find({ type: 'Text', text: '1 schließen? · 2 steht · 1 wartet · 1 weiter · 1 unklar' })).toBeDefined()
  expect(await ui.find({ type: 'Text',
    text: '6 geprüft · 0,9 ct · Haiku 5.5, Sonnet 5.5 · 24 s · Stand: vor 5 Min' })).toBeDefined()
  expect(taskCalls(w.calls, 'review')).toEqual([])
})

test('each filter chip shows its tasks only; the changed chip shows what changed since the last review', async ($, on) => {
  const w = setup(on)
  const ui = await page($, w)
  const want: Record<string, [string, string[]]> = {
    all: ['Alle 6', ['alpha', 'beta', 'zeta', 'gamma', 'eps', 'delta']],
    close: ['Schließen? 1', ['alpha']], stale: ['Steht 2', ['beta', 'zeta']], waiting: ['Wartet 1', ['gamma']],
    continue: ['Weiter 1', ['delta']], unclear: ['Unklar 1', ['eps']], changed: ['Geändert 1', ['beta']],
  }
  for (const [id, [label, slugs]] of Object.entries(want)) {
    expect((await ui.find({ type: 'Button', key: `ov-f-${id}` }))?.props.label).toBe(label)
    await ui.press({ key: `ov-f-${id}` })
    expect((await rowsOf(ui)).sort()).toEqual([...slugs].sort())
  }
})

test('rows are grouped by verdict, close first, and sort by priority or quiet', async ($, on) => {
  const w = setup(on)
  const ui = await page($, w)
  // within a verdict: priority, then slug
  expect(await rowsOf(ui)).toEqual(['alpha', 'zeta', 'beta', 'gamma', 'eps', 'delta'])
  expect(await ui.find({ type: 'Text', text: 'schließen? (1)' })).toBeDefined()
  await ui.press({ key: 'ov-s-priority' })
  expect(await rowsOf(ui)).toEqual(['gamma', 'alpha', 'zeta', 'eps', 'delta', 'beta'])
  await ui.press({ key: 'ov-s-activity' })
  expect(await rowsOf(ui)).toEqual(['beta', 'zeta', 'alpha', 'gamma', 'delta', 'eps'])
})

test('a row lines up tag, confidence, days, evidence chips and the reason; ▾ opens the full row', async ($, on) => {
  const w = setup(on)
  const ui = await page($, w)
  expect(await ui.find({ type: 'Box', key: 'ov-tag-alpha', text: 'schließen?' })).toBeDefined()
  expect(await ui.find({ type: 'Box', key: 'ov-conf-alpha', text: '●●○' })).toBeDefined()
  expect(await ui.find({ type: 'Box', key: 'ov-conf-eps', text: '●○○' })).toBeDefined()
  expect(await ui.find({ type: 'Box', key: 'ov-days-beta', text: '40 T' })).toBeDefined()
  expect((await ui.find({ type: 'Box', key: 'ov-chips-alpha' }))?.text)
    .toBe('#49 zu 03.10. · Blocker erledigt · 3 Schritte offen · 2 im Posteingang')
  await ui.press({ key: 'ov-x-alpha' })
  expect(await ui.find({ type: 'Button', key: 'done-task:alpha' })).toBeDefined()
})

test('select all takes the current filter; bulk close asks once, then closes each, stale ones declined', async ($, on) => {
  const w = setup(on)
  const ui = await page($, w)
  await ui.press({ key: 'ov-f-stale' })
  await ui.press({ key: 'ov-all' })
  await ui.press({ key: 'ov-f-close' })
  await ui.press({ key: 'ov-pick-alpha' })
  expect((await ui.find({ type: 'Button', key: 'ov-close' }))?.props.label).toBe('Ausgewählte schließen (3)')
  await ui.press({ key: 'ov-close' })
  expect(taskCalls(w.calls, 'close')).toEqual([])
  expect((await ui.find({ type: 'Button', key: 'ov-close' }))?.props.label).toBe('Wirklich 3 schließen?')
  await ui.press({ key: 'ov-close' })
  await w.clock.settle()
  expect(taskCalls(w.calls, 'close')).toEqual([
    ['close', 'alpha', '--reason', 'alpha reason', '--json'],
    ['close', 'zeta', '--reason', 'zeta reason', '--declined', '--json'],
    ['close', 'beta', '--reason', 'beta reason', '--declined', '--json'],
  ])
  await ui.press({ key: 'ov-f-all' })
  expect(await rowsOf(ui)).toEqual(['gamma', 'eps', 'delta'])
})

test('bulk keep sends one keep for the selection', async ($, on) => {
  const w = setup(on)
  const ui = await page($, w)
  await ui.press({ key: 'ov-pick-beta' })
  await ui.press({ key: 'ov-pick-gamma' })
  await ui.press({ key: 'ov-keep' })
  await w.clock.settle()
  expect(taskCalls(w.calls, 'review')).toEqual([['review', '--keep', 'beta', 'gamma', '--json']])
})

test('check closer asks task.py once for the selected tasks and names its estimated cost', async ($, on) => {
  const w = setup(on, 'en', { taskPy: argv => (argv.includes('--escalate')
    ? { stdout: JSON.stringify({ ...RUN, tasks: [{ ...RUN.tasks[4], verdict: 'stale', confidence: 'high',
      model: 'claude-sonnet-5-5' }], cost_usd: 0.02 }) } : { stdout: '{}' }) })
  const ui = await page($, w)
  await ui.press({ key: 'ov-pick-eps' })
  await ui.press({ key: 'ov-pick-delta' })
  expect((await ui.find({ type: 'Button', key: 'ov-esc' }))?.props.label).toBe('Check closer (2) ≈ 2.1 ct')
  await ui.press({ key: 'ov-esc' })
  await w.clock.settle()
  expect(taskCalls(w.calls, 'review')).toEqual([['review', '--escalate', 'eps', 'delta', '--json']])
  expect(await ui.find({ type: 'Box', key: 'ov-tag-eps', text: 'stale' })).toBeDefined()
})

test('open tab starts the selected continue and stale tasks through the existing launch', async ($, on) => {
  const w = setup(on, 'en')
  const ui = await page($, w)
  await ui.press({ key: 'ov-pick-beta' })
  await ui.press({ key: 'ov-pick-delta' })
  await ui.press({ key: 'ov-pick-gamma' })
  expect((await ui.find({ type: 'Button', key: 'ov-tab' }))?.props.label).toBe('Start agent (2)')
  await ui.press({ key: 'ov-tab' })
  const launch = w.calls.filter(a => a[1] === 'scripts/workplace.py' && a[2] === 'launch')
  expect(launch).toHaveLength(1)
  expect(launch[0]![launch[0]!.indexOf('--items') + 1]).toBe('beta,delta')
})

test('narrow: bar and chips stay, rows lose their evidence chips', async ($, on) => {
  const w = setup(on)
  await openCard($, w)
  const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'Pane', requestId: 'briefing-ui',
    props: { title: 'Briefing', isFocused: true, bodyColumns: 50, placement: 'dock' as const,
      scroll: { offset: 0, bodyRows: 80 }, view: {} } })
  await ui.press({ key: 'pgb-tasks' })
  expect(await ui.find({ type: 'Text', text: '1 schließen? · 2 steht · 1 wartet · 1 weiter · 1 unklar' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'ov-f-stale' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'ov-pick-alpha' })).toBeDefined()
  expect(await ui.find({ type: 'Box', key: 'ov-chips-alpha' })).toBeUndefined()
})

test('the card reaches the overview from its tasks header after a check', async ($, on) => {
  const w = world(on, { language: 'en', tasks: TASKS, taskPy: () => ({ stdout: JSON.stringify(RUN) }) })
  const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
    props: cardProps(await openCard($, w)), viewport: WIDE })
  expect(await ui.find({ type: 'Button', key: 'review-overview' })).toBeUndefined()
  await ui.press({ key: 'review-all-work' })
  await w.clock.settle()
  await ui.press({ key: 'review-overview' })
  expect(await ui.find({ type: 'Text', text: '1 close? · 2 stale · 1 waiting · 1 continue · 1 unclear' })).toBeDefined()
})
