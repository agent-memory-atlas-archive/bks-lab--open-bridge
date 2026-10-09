// Check all, the verdict per task, and closing a finished task from the card.
import { test, expect } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import { cardProps, collect, openCard, world } from './world'

const LANGS = ['de', 'en'] as const
const WIDE = { columns: 140, rows: 60 }

const TASKS = [{ slug: 'alpha', label: 'Alpha rollout', area: 'acme', area_aliases: [], priority: 'P1', blocked_by: null,
  stale: false, age: 0, type: 'feature' }]
const PAGE_ITEM = { title: 'Alpha rollout', when: '07.10', detail: 'P1 · acme', tone: null, url: null, task: 'alpha',
  ask: false, mark: null, priority: 'P1', state: 'doing', lines: [{ kind: 'step', text: 'write the rollout note' }] }
const TASK_PAGE = { id: 'tasks', title: 'Tasks', sections: [{ id: 'tasks', kind: 'tasks', title: 'Tasks', status: 'ok',
  reason: '', alarm: false, empty: 'nothing', total: 1, weight: 1, bad: 0, as_of: null, items: [PAGE_ITEM] }] }
const REASON = 'example-org/x#49 was closed as completed six days ago'
const REVIEW = {
  tasks: [{ slug: 'alpha', title: 'Alpha rollout', verdict: 'close', reason: REASON, confidence: 'high',
    model: 'claude-haiku-5-5', cached: false, kept: false, evidence_summary: 'doing · example-org/x#49 CLOSED' },
  { slug: 'beta', title: 'Beta', verdict: 'continue', reason: 'r', confidence: 'high', model: 'claude-haiku-5-5',
    cached: true, kept: false, evidence_summary: '' },
  { slug: 'gamma', title: 'Gamma', verdict: 'stale', reason: 'r', confidence: 'medium', model: 'claude-sonnet-5-5',
    cached: false, kept: false, evidence_summary: '' }],
  cost_usd: 0.0009, models_used: ['claude-haiku-5-5', 'claude-sonnet-5-5'], model_mismatch: [],
}
const T = {
  de: { all: '⟳ Aufgaben prüfen', done: '3 geprüft, 1 zum Schließen, 0,09 ct', tag: 'schließen?',
    rec: 'Empfehlung (Haiku 5.5): ', close: 'Schließen', keep: 'Offen lassen', finished: 'Als erledigt schließen',
    sure: 'Wirklich schließen?', one: 'Prüfen lassen', dashboard: 'aus dem Dashboard geschlossen' },
  en: { all: '⟳ Check tasks', done: '3 reviewed, 1 to close, 0.09 ct', tag: 'close?',
    rec: 'Recommendation (Haiku 5.5): ', close: 'Close', keep: 'Keep open', finished: 'Mark done',
    sure: 'Really close?', one: 'Check', dashboard: 'closed from the dashboard' },
}
const taskCalls = (calls: string[][], sub: string) => calls.filter(a => a[1] === 'scripts/task.py' && a[2] === sub)
  .map(a => a.slice(2))

function setup(on: Parameters<typeof world>[0], lang: 'de' | 'en', extra: Parameters<typeof world>[1] = {}) {
  return world(on, { language: lang, tasks: TASKS, collect: collect({ pages: [TASK_PAGE] }),
    taskPy: argv => (argv[2] === 'review' && argv.includes('--all') ? { stdout: JSON.stringify(REVIEW) }
      : argv[2] === 'review' ? { stdout: JSON.stringify({ ...REVIEW, tasks: [REVIEW.tasks[0]] }) }
        : { stdout: '{}' }), ...extra })
}

async function tasksPage($: Engine, w: ReturnType<typeof world>) {
  const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
    props: cardProps(await openCard($, w)), viewport: WIDE })
  await ui.press({ key: 'pgb-tasks' })
  return ui
}

for (const lang of LANGS) {
  test(`check all runs one review of every task and reports count, to close and cost (${lang})`, async ($, on) => {
    const w = setup(on, lang)
    const ui = await tasksPage($, w)
    expect((await ui.find({ type: 'Button', key: 'review-all-tasks' }))?.props.label).toBe(T[lang].all)
    expect(await ui.find({ type: 'Text', text: new RegExp(T[lang].tag.replace('?', '\\?')) })).toBeUndefined()
    await ui.press({ key: 'review-all-tasks' })
    await w.clock.settle()
    expect(taskCalls(w.calls, 'review')).toEqual([['review', '--all', '--json']])
    const at = w.calls.findIndex(a => a[1] === 'scripts/task.py' && a[2] === 'review')
    expect(w.timeouts[at]).toBeGreaterThanOrEqual(240000)
    expect(w.toasts.join('\n')).toContain(T[lang].done)
    // the collapsed row carries the verdict as a short tag
    expect(await ui.find({ type: 'Text', text: new RegExp(T[lang].tag.replace('?', '\\?')) })).toBeDefined()
  })

  test(`an opened row shows the recommendation, Keep dismisses it (${lang})`, async ($, on) => {
    const w = setup(on, lang)
    const ui = await tasksPage($, w)
    await ui.press({ key: 'review-all-tasks' })
    await w.clock.settle()
    await ui.press({ key: 'px-tasks-0' })
    // the overview above the sections shows the reason too; the opened row says whose recommendation it is
    expect(await ui.find({ type: 'Text', text: `${T[lang].rec}${REASON}` })).toBeDefined()
    expect((await ui.find({ type: 'Button', key: 'rv-close-task:alpha' }))?.props.label).toBe(T[lang].close)
    expect((await ui.find({ type: 'Button', key: 'rv-keep-task:alpha' }))?.props.label).toBe(T[lang].keep)
    await ui.press({ key: 'rv-keep-task:alpha' })
    expect(taskCalls(w.calls, 'review').at(-1)).toEqual(['review', '--keep', 'alpha', '--json'])
    expect(await ui.find({ type: 'Button', key: 'rv-close-task:alpha' })).toBeUndefined()
    expect(await ui.find({ type: 'Text', text: `${T[lang].rec}${REASON}` })).toBeUndefined()
  })

  test(`Done asks once more, the second click closes with the recommendation's reason (${lang})`, async ($, on) => {
    const w = setup(on, lang)
    const ui = await tasksPage($, w)
    await ui.press({ key: 'review-all-tasks' })
    await w.clock.settle()
    await ui.press({ key: 'px-tasks-0' })
    expect((await ui.find({ type: 'Button', key: 'done-task:alpha' }))?.props.label).toBe(T[lang].finished)
    await ui.press({ key: 'done-task:alpha' })
    expect(taskCalls(w.calls, 'close')).toEqual([])
    expect((await ui.find({ type: 'Button', key: 'done-task:alpha' }))?.props.label).toBe(T[lang].sure)
    await ui.press({ key: 'done-task:alpha' })
    await w.clock.settle()
    expect(taskCalls(w.calls, 'close')).toEqual([['close', 'alpha', '--reason', REASON, '--json']])
    // the row is gone from the page
    expect(await ui.find({ type: 'Button', key: 'px-tasks-0' })).toBeUndefined()
    expect(await ui.find({ type: 'Text', text: /Alpha rollout/ })).toBeUndefined()
  })
}

test('the confirmation runs out: a second click after a few seconds asks again', async ($, on) => {
  const w = setup(on, 'en')
  const ui = await tasksPage($, w)
  await ui.press({ key: 'px-tasks-0' })
  await ui.press({ key: 'done-task:alpha' })
  await w.clock.advance(6000)
  expect((await ui.find({ type: 'Button', key: 'done-task:alpha' }))?.props.label).toBe('Mark done')
  await ui.press({ key: 'done-task:alpha' })
  expect(taskCalls(w.calls, 'close')).toEqual([])
})

test('Done without a recommendation closes with the dashboard reason; Close from the recommendation asks too',
  async ($, on) => {
    const w = setup(on, 'de')
    const ui = await tasksPage($, w)
    await ui.press({ key: 'px-tasks-0' })
    await ui.press({ key: 'done-task:alpha' })
    await ui.press({ key: 'done-task:alpha' })
    await w.clock.settle()
    expect(taskCalls(w.calls, 'close')).toEqual([['close', 'alpha', '--reason', T.de.dashboard, '--json']])
  })

test('check one task from its opened row', async ($, on) => {
  const w = setup(on, 'en')
  const ui = await tasksPage($, w)
  await ui.press({ key: 'px-tasks-0' })
  expect((await ui.find({ type: 'Button', key: 'rv-one-task:alpha' }))?.props.label).toBe('Check')
  await ui.press({ key: 'rv-one-task:alpha' })
  await w.clock.settle()
  expect(taskCalls(w.calls, 'review')).toEqual([['review', 'alpha', '--json']])
  expect(await ui.find({ type: 'Text', text: new RegExp(REASON) })).toBeDefined()
})

test('the card offers check all on its tasks block and tags a task row', async ($, on) => {
  // a task the briefing does not name lands in the tasks block from the task list
  const w = world(on, { tasks: TASKS, taskPy: () => ({ stdout: JSON.stringify(REVIEW) }) })
  const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
    props: cardProps(await openCard($, w)), viewport: WIDE })
  expect((await ui.find({ type: 'Button', key: 'review-all-work' }))?.props.label).toBe('⟳ Check tasks')
  await ui.press({ key: 'review-all-work' })
  await w.clock.settle()
  expect(await ui.find({ type: 'Text', text: /close\?/ })).toBeDefined()
})

test('verdicts of an earlier review come from the cache file when the card opens', async ($, on) => {
  const w = setup(on, 'en', { files: { '.bridge/task-review.json': JSON.stringify({ version: 1, tasks: {
    alpha: { verdict: 'stale', reason: 'no activity since August', confidence: 'medium', model: 'claude-haiku-5-5',
      kept: false } } }) } })
  const ui = await tasksPage($, w)
  expect(await ui.find({ type: 'Text', text: /stale\?/ })).toBeDefined()
  expect(taskCalls(w.calls, 'review')).toEqual([])
})

test('a failed check names the error and leaves the rows alone', async ($, on) => {
  const w = setup(on, 'en', { taskPy: () => ({ exitCode: 1, stderr: 'task: boom' }) })
  const ui = await tasksPage($, w)
  await ui.press({ key: 'review-all-tasks' })
  await w.clock.settle()
  expect(w.toasts.join('\n')).toContain('boom')
  expect(await ui.find({ type: 'Button', key: 'px-tasks-0' })).toBeDefined()
})

// ---------------------------------------------------------------- the signal, low confidence, the sidebar

const SIGNAL = { ...REVIEW, tasks: [{ ...REVIEW.tasks[0]!, verdict: 'continue', confidence: 'medium',
  reason: 'steps still open', resolved: true,
  signals: { own_refs_closed: true, blocker_resolved: true, closed_refs: ['example-org/x#49 2026-10-03'] } }] }

test('a resolved signal shows close? and Close even when the model said continue', async ($, on) => {
  const w = setup(on, 'de', { taskPy: () => ({ stdout: JSON.stringify(SIGNAL) }) })
  const ui = await tasksPage($, w)
  await ui.press({ key: 'review-all-tasks' })
  await w.clock.settle()
  expect(await ui.find({ type: 'Text', text: /schließen\?/ })).toBeDefined()
  expect(w.toasts.join('\n')).toContain('1 geprüft, 1 zum Schließen')
  await ui.press({ key: 'px-tasks-0' })
  expect(await ui.find({ type: 'Button', key: 'rv-close-task:alpha' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /example-org\/x#49 2026-10-03/ })).toBeDefined()
})

test('a low confidence shows as a question mark after the tag', async ($, on) => {
  const low = { ...REVIEW, tasks: [{ ...REVIEW.tasks[0]!, verdict: 'stale', confidence: 'low' }] }
  const w = setup(on, 'en', { taskPy: () => ({ stdout: JSON.stringify(low) }) })
  const ui = await tasksPage($, w)
  await ui.press({ key: 'review-all-tasks' })
  await w.clock.settle()
  expect(await ui.find({ type: 'Text', text: /stale\?\?/ })).toBeDefined()
})

test('the narrow sidebar opens a task with Done, Close, Keep and check', async ($, on) => {
  const w = world(on, { tasks: TASKS, taskPy: () => ({ stdout: JSON.stringify(REVIEW) }) })
  await openCard($, w)
  const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'Pane',
    requestId: 'briefing-ui', props: { title: 'Briefing', isFocused: true, bodyColumns: 60, placement: 'dock' as const,
      scroll: { offset: 0, bodyRows: 60 }, view: {} } })
  await ui.press({ key: 'stitle-task:alpha' })
  expect(await ui.find({ type: 'Button', key: 'done-task:alpha' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'rv-one-task:alpha' })).toBeDefined()
  await ui.press({ key: 'rv-one-task:alpha' })
  await w.clock.settle()
  expect(await ui.find({ type: 'Button', key: 'rv-close-task:alpha' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'rv-keep-task:alpha' })).toBeDefined()
})


// ---------------------------------------------------------------- review round two

test('a resolved blocker alone is a hint: no close tag, no Close button', async ($, on) => {
  const hint = { ...REVIEW, tasks: [{ ...REVIEW.tasks[0]!, verdict: 'continue', confidence: 'medium', reason: 'steps open',
    resolved: false, signals: { own_refs_closed: false, blocker_resolved: true, closed_refs: ['example-org/x#49 2026-10-03'] } }] }
  const w = setup(on, 'de', { taskPy: () => ({ stdout: JSON.stringify(hint) }) })
  const ui = await tasksPage($, w)
  await ui.press({ key: 'review-all-tasks' })
  await w.clock.settle()
  expect(await ui.find({ type: 'Text', text: /schließen\?/ })).toBeUndefined()
  await ui.press({ key: 'px-tasks-0' })
  expect((await ui.find({ type: 'Text', text: /Blocker erledigt/ }))?.text).toBe('Blocker erledigt: example-org/x#49 2026-10-03')
  expect(await ui.find({ type: 'Button', key: 'rv-close-task:alpha' })).toBeUndefined()
  expect(await ui.find({ type: 'Button', key: 'done-task:alpha' })).toBeDefined()
})

test('Close on a stale verdict closes as declined; Done stays a completed close', async ($, on) => {
  const stale = { ...REVIEW, tasks: [{ ...REVIEW.tasks[0]!, verdict: 'stale', reason: 'quiet since August' }] }
  const w = setup(on, 'en', { taskPy: argv => (argv[2] === 'review' ? { stdout: JSON.stringify(stale) } : { stdout: '{}' }) })
  const ui = await tasksPage($, w)
  await ui.press({ key: 'review-all-tasks' })
  await w.clock.settle()
  await ui.press({ key: 'px-tasks-0' })
  await ui.press({ key: 'rv-close-task:alpha' })
  await ui.press({ key: 'rv-close-task:alpha' })
  await w.clock.settle()
  expect(taskCalls(w.calls, 'close')).toEqual([['close', 'alpha', '--reason', 'quiet since August', '--declined', '--json']])
})

test('a stream row offers neither Done nor Close', async ($, on) => {
  const w = world(on, { tasks: [{ ...TASKS[0]!, kind: 'streams' }], taskPy: () => ({ stdout: JSON.stringify(REVIEW) }) })
  const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
    props: cardProps(await openCard($, w)), viewport: WIDE })
  await ui.press({ key: 'more-task:alpha' })
  expect(await ui.find({ type: 'Button', key: 'l1-task:alpha' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'done-task:alpha' })).toBeUndefined()
  expect(await ui.find({ type: 'Button', key: 'rv-close-task:alpha' })).toBeUndefined()
})

test('a task row that is no stream opens with Done (control for the test above)', async ($, on) => {
  const w = world(on, { tasks: [{ ...TASKS[0]!, kind: 'tasks' }] })
  const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
    props: cardProps(await openCard($, w)), viewport: WIDE })
  await ui.press({ key: 'more-task:alpha' })
  expect(await ui.find({ type: 'Button', key: 'done-task:alpha' })).toBeDefined()
})
