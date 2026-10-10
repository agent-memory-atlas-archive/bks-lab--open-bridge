// Every clickable thing is a framed, coloured button; the new labels in German and English.
import { test, expect } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { FoundElement } from 'claude-code/testing'
import { cardProps, collect, item, openCard, tab, world } from './world'

const WIDE = { columns: 160, rows: 80 }
const t = (slug: string, verdict: string) => ({
  slug, title: `${slug} work`, verdict, reason: `${slug} reason`, confidence: 'medium', model: 'claude-haiku-5-5',
  cached: true, kept: false, resolved: false, signals: { own_refs_closed: false, blocker_resolved: false, closed_refs: [] },
  status: 'doing', priority: 'P2', days_since_activity: 4, chips: [], previous_verdict: null, changed: false })
const RUN = { tasks: [t('alpha', 'close'), t('beta', 'stale')], cost_usd: 0.002, cost_known: true,
  models_used: ['claude-haiku-5-5'], model_mismatch: [], reviewed: 2, to_close: 1, reviewed_at: '2026-10-09T07:00:00',
  duration_sec: 20, escalate_call_usd: 0.021 }
const TASKS = ['alpha', 'beta'].map(slug => ({ slug, label: `${slug} work`, area: 'acme', area_aliases: [],
  priority: 'P2', blocked_by: null, stale: false, age: 0, type: 'feature', kind: 'tasks' }))
const TASK_PAGE = { id: 'tasks', title: 'Tasks', sections: [{ id: 'tasks', kind: 'tasks', title: 'Tasks', status: 'ok',
  reason: '', alarm: false, empty: 'nothing', total: 1, weight: 1, bad: 0, as_of: null, items: [
    { title: 'alpha work', when: '07.10', detail: '', tone: null, url: 'https://example.org/alpha', task: 'alpha',
      ask: true, mark: null, priority: 'P2', state: 'doing', lines: [] }] }] }
const card = async ($: Engine, w: ReturnType<typeof world>) =>
  $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
    props: cardProps(await openCard($, w)), viewport: WIDE })

for (const [lang, want] of [
  ['de', { show: 'Tab zeigen', details: 'Details ▾', less: 'Details ▴', ask: 'Im Chat fragen', go: 'Weitermachen',
    check: '⟳ Aufgaben prüfen', start: 'Agent starten', done: 'Als erledigt schließen', one: 'Prüfen lassen' }],
  ['en', { show: 'Show tab', details: 'Details ▾', less: 'Details ▴', ask: 'Ask in chat', go: 'Go on',
    check: '⟳ Check tasks', start: 'Start agent', done: 'Mark done', one: 'Check' }],
] as const) {
  test(`the new labels (${lang})`, async ($, on) => {
    const w = world(on, { language: lang, tasks: TASKS, collect: collect({ pages: [TASK_PAGE] }),
      status: [tab('surface:12', 'waiting', { slug: 'alpha', name: 'alpha work' })] })
    const ui = await card($, w)
    expect((await ui.find({ type: 'Button', key: 'hin-task:alpha' }))?.props.label).toBe(want.show)
    expect((await ui.find({ type: 'Button', key: 'go-surface:12' }))?.props.label).toBe(want.go)
    expect((await ui.find({ type: 'Button', key: 'review-all-work' }))?.props.label).toBe(want.check)
    expect((await ui.find({ type: 'Button', key: 'more-task:alpha' }))?.props.label).toBe(want.details)
    await ui.press({ key: 'more-task:alpha' })
    expect((await ui.find({ type: 'Button', key: 'more-task:alpha' }))?.props.label).toBe(want.less)
    expect((await ui.find({ type: 'Button', key: 'ask-task:alpha' }))?.props.label).toBe(want.ask)
    expect((await ui.find({ type: 'Button', key: 'done-task:alpha' }))?.props.label).toBe(want.done)
    expect((await ui.find({ type: 'Button', key: 'rv-one-task:alpha' }))?.props.label).toBe(want.one)
    await ui.press({ key: 'pgb-tasks' })
    expect((await ui.find({ type: 'Button', key: 'pt-tasks-0' }))?.props.label).toBe(want.show)
    expect((await ui.find({ type: 'Button', key: 'px-tasks-0' }))?.props.label).toBe(want.details)
  })
}

test('a page row without a running tab offers to start an agent', async ($, on) => {
  const w = world(on, { tasks: TASKS, collect: collect({ pages: [TASK_PAGE] }) })
  const ui = await card($, w)
  await ui.press({ key: 'pgb-tasks' })
  expect((await ui.find({ type: 'Button', key: 'pt-tasks-0' }))?.props.label).toBe('Start agent')
})

test('the section arrow is a framed "show all" and back', async ($, on) => {
  const rows = [1, 2, 3, 4, 5, 6].map(n => item(`acme item ${n}`, { bucket: 'do', urgency: 'now' }))
  const w = world(on, { collect: collect({ buckets: [{ id: 'do', items: rows }] }) })
  const ui = await card($, w)
  expect((await ui.find({ type: 'Button', key: 'more-now' }))?.props.label).toBe('Show all (+2) ›')
  await ui.press({ key: 'more-now' })
  expect((await ui.find({ type: 'Button', key: 'less-now' }))?.props.label).toBe('Show less ‹')
})

/** The rule: framed and coloured, never plain or dim; a checkbox may be plain, as checkboxes are. */
function offenders(buttons: FoundElement[]): string[] {
  return buttons.filter(b => b.props.dimColor || (b.props.plain && !/^\[[ x]\]$/.test(String(b.props.label))))
    .map(b => `${b.key}: ${String(b.props.label)}`)
}

test('guard: no plain or dim button on the card, the tasks page, the overview, the pane and the band', async ($, on) => {
  const w = world(on, { language: 'de', tasks: TASKS, ui: { band: true },
    files: { '.bridge/task-review.json': JSON.stringify({ version: 1, tasks: {}, last: RUN }) },
    status: [tab('surface:12', 'needs-you', { slug: 'alpha' }), tab('surface:13', 'waiting')],
    collect: collect({ pages: [TASK_PAGE], buckets: [
      { id: 'do', items: [item('alpha work', { task: 'alpha', sources: ['tasks'] })] },
      { id: 'delegate', items: [1, 2].map(n => item(`beta mail ${n}`, { bucket: 'delegate',
        inbox_id: `20261009-0800-b${n}`, gate: 'your-yes', has_action: true, inbox_state: 'open' })) }] }) })
  const ui = await card($, w)
  await ui.press({ key: 'review-overview' })
  await ui.press({ key: 'more-task:alpha' })
  expect(offenders(await ui.findAll({ type: 'Button' }))).toEqual([])
  await ui.press({ key: 'pgb-tasks' })
  await ui.press({ key: 'ov-x-alpha' })
  await ui.press({ key: 'ov-pick-alpha' })
  expect(offenders(await ui.findAll({ type: 'Button' }))).toEqual([])
  const pane = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'Pane', requestId: 'briefing-ui',
    props: { title: 'Briefing', isFocused: true, bodyColumns: 60, placement: 'dock' as const,
      scroll: { offset: 0, bodyRows: 80 }, view: {} } })
  expect(offenders(await pane.findAll({ type: 'Button' }))).toEqual([])
  const band = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'AbovePrompt',
    props: { hasSurvey: false, isWorking: false, maxRows: 3, bodyColumns: 140, scroll: { offset: 0, bodyRows: 3 }, view: {} }, viewport: { columns: 140, rows: 3 } })
  expect((await band.findAll({ type: 'Button' })).length).toBeGreaterThan(0)
  expect(offenders(await band.findAll({ type: 'Button' }))).toEqual([])
})
