// Actions of the card that reach the Bridge scripts or the conversation: approve all, plan my day, reload.
import { test, expect } from 'claude-code/testing'
import { approvable, cardProps, collect, item, openCard, tab, world } from './world'

const LANGS = ['de', 'en'] as const
const WIDE = { columns: 140, rows: 60 }

const APPROVE_ALL = { de: 'alle 4 freigeben', en: 'approve all 4' }
const APPROVE_ASK = { de: 'Wirklich alle 4 freigeben?', en: 'Approve all 4?' }
const PLAN = {
  de: { agenda: 'Termine:', tabs: 'Agenten-Tabs, die auf mich warten:', state: 'wartet' },
  en: { agenda: 'Appointments:', tabs: 'Agent tabs waiting for me:', state: 'waiting' },
}

const approvals = (calls: string[][]) =>
  calls.filter(argv => argv[1] === 'scripts/inbox.py' && argv[2] === 'approve').map(argv => argv.slice(1))
const skipsOf = (argv: string[]) => argv.flatMap((x, i) => (x === '--skip' ? [argv[i + 1]] : []))
const isCollect = (argv: string[]) => argv[1] === 'scripts/briefing.py' && argv[2] === 'collect'

for (const lang of LANGS) {
  test(`approve all counts the visible rows, asks, and Cancel approves nothing (${lang})`, async ($, on) => {
    // six rows wait for a yes, the compact card shows four of them
    const w = world(on, { language: lang, collect: collect({ buckets: [{ id: 'delegate',
      items: [1, 2, 3, 4, 5, 6].map(approvable) }] }) })
    const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
      props: cardProps(await openCard($, w)), viewport: WIDE })
    expect((await ui.find({ type: 'Button', key: 'approve-all' }))?.props.label).toBe(`${APPROVE_ALL[lang]} `)
    await ui.press({ key: 'approve-all' })
    expect(await ui.find({ type: 'Text', text: APPROVE_ASK[lang] })).toBeDefined()
    expect(await ui.find({ type: 'Button', key: 'approve-all' })).toBeUndefined()
    await ui.press({ key: 'approve-no' })
    expect(approvals(w.calls)).toEqual([])
    expect(await ui.find({ type: 'Button', key: 'approve-yes' })).toBeUndefined()
    expect(await ui.find({ type: 'Button', key: 'approve-all' })).toBeDefined()
  })
}

test('approve all, Yes: approves exactly the visible rows, never one beyond the cap', async ($, on) => {
  const free = item('beta-corp: read the contract', { bucket: 'delegate', inbox_id: '20261009-0800-beta-free',
    gate: 'free', has_action: false, inbox_state: 'open' })
  const done = { ...approvable(9), inbox_state: 'approved' }
  const w = world(on, { collect: collect({ buckets: [{ id: 'delegate',
    items: [approvable(1), free, done, approvable(2), approvable(3), approvable(4), approvable(5)] }] }) })
  const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
    props: cardProps(await openCard($, w)), viewport: WIDE })
  // shown: 1, free, done, 2; approvable among them: 1 and 2
  expect((await ui.find({ type: 'Button', key: 'approve-all' }))?.props.label).toBe('approve all 2 ')
  await ui.press({ key: 'approve-all' })
  await ui.press({ key: 'approve-yes' })
  expect(approvals(w.calls)).toEqual([
    ['scripts/inbox.py', 'approve', '20261009-0800-beta-1'],
    ['scripts/inbox.py', 'approve', '20261009-0800-beta-2'],
  ])
  // nothing else was started for these rows: a yes is all an action needs
  expect(w.calls.filter(argv => argv[2] === 'launch')).toEqual([])
})

for (const lang of LANGS) {
  test(`plan my day submits the agenda, the rows with their marks and the waiting tabs (${lang})`, async ($, on) => {
    const w = world(on, {
      language: lang,
      status: [tab('surface:12', 'waiting', { workspace: 'acme', name: 'alpha review' })],
      collect: collect({
        agenda: [{ when: '09:30-10:00', title: 'acme sync' }],
        buckets: [{ id: 'do', items: [item('alpha rollout', { task: 'alpha-rollout', sources: ['tasks'],
          priority: 'P1', mark: { label: 'beta-corp', color: 'cyan' } })] }],
      }),
    })
    const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
      props: cardProps(await openCard($, w)), viewport: WIDE })
    await ui.press({ key: 'plan' })
    expect(w.prompts).toHaveLength(1)
    const prompt = w.prompts[0] ?? ''
    expect(prompt).toContain(`${PLAN[lang].agenda}\n- 09:30-10:00 acme sync`)
    expect(prompt).toContain('1. [now P1 beta-corp] alpha rollout')
    expect(prompt).toContain(`${PLAN[lang].tabs}\n- acme / alpha review: ${PLAN[lang].state}`)
  })
}

test('the quick pass on open skips exactly tracker and command; reload runs collect with --fresh', async ($, on) => {
  const w = world(on)
  const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
    props: cardProps(await openCard($, w)), viewport: WIDE })
  const opened = w.calls.filter(isCollect)
  // nothing cached: the quick pass, then the full one
  expect(opened.map(skipsOf)).toEqual([['tracker', 'command'], []])
  expect(opened.some(argv => argv.includes('--fresh'))).toBe(false)
  const before = w.calls.length
  await ui.press({ key: 'reload' })
  await w.clock.settle()
  const reloaded = w.calls.slice(before).filter(isCollect)
  expect(reloaded.length).toBeGreaterThan(0)
  expect(reloaded.every(argv => argv.includes('--fresh'))).toBe(true)
  expect(reloaded.map(skipsOf)).toEqual([['tracker', 'command'], []])
})

// ---------------------------------------------------------------- tasks: open a row, start it where you want

const TASKS = [{ slug: 'alpha', label: 'Alpha rollout', area: 'acme', area_aliases: [], priority: 'P1', blocked_by: null,
  stale: false, age: 0, type: 'feature' }]
const TASK_PAGE = { id: 'tasks', title: 'Tasks', sections: [{ id: 'tasks', kind: 'tasks', title: 'Tasks', status: 'ok',
  reason: '', alarm: false, empty: 'nothing', total: 1, weight: 1, bad: 0, as_of: null, items: [
    { title: 'Alpha rollout', when: '07.10', detail: 'P1 · acme', tone: null, url: null, task: 'alpha', ask: false,
      mark: null, priority: 'P1', state: 'doing',
      lines: [{ kind: 'origin', text: 'asked in the acme sync' }, { kind: 'step', text: 'write the rollout note' }] }] }] }
const START = {
  de: { do: 'Mach du', tab: 'als Tab hier', area: 'im Bereich acme', ws: 'im eigenen Workspace', step: 'Schritt: ',
    state: 'in Arbeit' },
  en: { do: 'Do it', tab: 'as a tab here', area: 'in area acme', ws: 'in its own workspace', step: 'Step: ',
    state: 'doing' },
}
const launches = (calls: string[][]) => calls.filter(argv => argv[1] === 'scripts/workplace.py' && argv[2] === 'launch')
const flag = (argv: string[], name: string) => argv[argv.indexOf(name) + 1]
const PANE = { title: 'Briefing', isFocused: true, bodyColumns: 60, placement: 'dock' as const,
  scroll: { offset: 0, bodyRows: 60 }, view: {} }

for (const lang of LANGS) {
  test(`a row on the tasks page opens to its details and starts where you pick (${lang})`, async ($, on) => {
    const w = world(on, { language: lang, tasks: TASKS, collect: collect({ pages: [TASK_PAGE] }) })
    const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
      props: cardProps(await openCard($, w)), viewport: WIDE })
    await ui.press({ key: 'pgb-tasks' })
    expect(await ui.find({ type: 'Text', text: /write the rollout note/ })).toBeUndefined()
    await ui.press({ key: 'px-tasks-0' })
    expect((await ui.find({ type: 'Text', text: /write the rollout note/ }))?.text).toContain(START[lang].step)
    expect(await ui.find({ type: 'Text', text: /asked in the acme sync/ })).toBeDefined()
    // the status in words of the card's language, never the raw enum
    expect((await ui.find({ type: 'Text', text: /^P1 · acme · / }))?.text).toBe(`P1 · acme · ${START[lang].state} · 07.10`)
    expect((await ui.find({ type: 'Button', key: 'ta-do-task:alpha' }))?.props.label).toBe(START[lang].do)
    expect((await ui.find({ type: 'Button', key: 'ts-tab-task:alpha' }))?.props.label).toBe(START[lang].tab)
    expect((await ui.find({ type: 'Button', key: 'ts-area-task:alpha' }))?.props.label).toBe(START[lang].area)
    expect((await ui.find({ type: 'Button', key: 'ts-workspace-task:alpha' }))?.props.label).toBe(START[lang].ws)
    // the rest of the row's detail: later, priority, team, context
    expect(await ui.find({ type: 'Button', key: 'l1-task:alpha' })).toBeDefined()
    expect(await ui.find({ type: 'Button', key: 'p-P0-task:alpha' })).toBeDefined()
    await ui.press({ key: 'ts-workspace-task:alpha' })
    const calls = launches(w.calls)
    expect(calls).toHaveLength(1)
    expect([flag(calls[0]!, '--items'), flag(calls[0]!, '--mode'), flag(calls[0]!, '--target')])
      .toEqual(['alpha', 'go', 'workspace'])
  })

  test(`a start in the area names the area in its note (${lang})`, async ($, on) => {
    const w = world(on, { language: lang, tasks: TASKS, collect: collect({ pages: [TASK_PAGE] }) })
    const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
      props: cardProps(await openCard($, w)), viewport: WIDE })
    await ui.press({ key: 'pgb-tasks' })
    await ui.press({ key: 'px-tasks-0' })
    await ui.press({ key: 'ts-area-task:alpha' })
    expect(w.toasts.join('\n')).toContain(START[lang].area)
  })
}

test('the tasks page opens a row in the narrow sidebar too', async ($, on) => {
  const w = world(on, { tasks: TASKS, collect: collect({ pages: [TASK_PAGE] }) })
  await openCard($, w)
  const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'Pane',
    requestId: 'briefing-ui', props: PANE })
  await ui.press({ key: 'pgb-tasks' })
  await ui.press({ key: 'px-tasks-0' })
  expect(await ui.find({ type: 'Button', key: 'ts-area-task:alpha' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'ta-do-task:alpha' })).toBeDefined()
})

test('an opened task with a running agent tab offers the tab, not a second start', async ($, on) => {
  const w = world(on, { tasks: TASKS, collect: collect({ pages: [TASK_PAGE] }),
    status: [tab('surface:12', 'waiting', { slug: 'alpha', name: 'Alpha rollout' })] })
  const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
    props: cardProps(await openCard($, w)), viewport: WIDE })
  await ui.press({ key: 'pgb-tasks' })
  await ui.press({ key: 'px-tasks-0' })
  expect((await ui.find({ type: 'Button', key: 'ta-hin-task:alpha' }))?.props.label).toBe('Go to tab')
  expect(await ui.find({ type: 'Button', key: 'go-surface:12' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'ts-tab-task:alpha' })).toBeUndefined()
})

test('a dead shell tab of a task does not block it: the row offers restart next to the tab', async ($, on) => {
  const w = world(on, { tasks: TASKS, status: [tab('surface:12', 'shell', { slug: 'alpha', name: 'Alpha rollout' })] })
  const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
    props: cardProps(await openCard($, w)), viewport: WIDE })
  expect((await ui.find({ type: 'Button', key: 'restart-task:alpha' }))?.props.label).toBe('Restart')
  expect(await ui.find({ type: 'Button', key: 'hin-task:alpha' })).toBeDefined()
  await ui.press({ key: 'restart-task:alpha' })
  const calls = launches(w.calls)
  expect(calls).toHaveLength(1)
  expect(flag(calls[0]!, '--items')).toBe('alpha')
})

test('a second click while a start is under way starts nothing more', async ($, on) => {
  const w = world(on, { tasks: TASKS })
  const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
    props: cardProps(await openCard($, w)), viewport: WIDE })
  await ui.press({ key: 'do-task:alpha' })
  await ui.press({ key: 'do-task:alpha' })
  expect(launches(w.calls)).toHaveLength(1)
  expect(w.toasts.join('\n')).toContain('is already starting')
  // once the grace has passed (the tab list knows the tab by then) a click starts again
  await w.clock.advance(20000)
  await ui.press({ key: 'do-task:alpha' })
  expect(launches(w.calls)).toHaveLength(2)
})

test('a start that finds the agent already running switches to its tab', async ($, on) => {
  const w = world(on, { tasks: TASKS, status: [tab('surface:12', 'working', { ws_ref: 'workspace:7' })],
    launch: () => ({ ok: true, report: ['already open: Alpha rollout (surface:12) in acme'],
      items: [{ item: 'alpha', kind: 'task', label: 'Alpha rollout', skipped: 'open', ref: 'surface:12' }] }) })
  const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
    props: cardProps(await openCard($, w)), viewport: WIDE })
  await ui.press({ key: 'do-task:alpha' })
  await w.clock.settle()
  expect(w.calls.filter(argv => argv[1] === 'focus-panel')).toEqual([
    ['cmux', 'focus-panel', '--panel', 'surface:12', '--workspace', 'workspace:7']])
  expect(w.toasts.join('\n')).toContain('already running')
  // nothing started, so no note says so, and the driver's raw line stays out of the card
  expect(w.toasts.some(t => /"text":"started|already open:/.test(t))).toBe(false)
})

test('the dashboard waits longer for a start than the router and the driver may take', async ($, on) => {
  const w = world(on, { tasks: TASKS })
  const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
    props: cardProps(await openCard($, w)), viewport: WIDE })
  await ui.press({ key: 'do-task:alpha' })
  const timeout = w.timeouts[w.calls.findIndex(argv => argv[2] === 'launch')] ?? 0
  expect(timeout).toBeGreaterThanOrEqual(150000)
})

const TEAMS = [{ id: 'pair', label: 'Pair', for_types: ['feature'],
  roles: [{ id: 'dev', name: 'Dev', mode: 'go' }, { id: 'rev', name: 'Review', mode: 'report' }] }]

test('a team start while the task is still starting stores no team run', async ($, on) => {
  const w = world(on, { tasks: TASKS, teams: TEAMS, collect: collect({ pages: [TASK_PAGE] }) })
  const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
    props: cardProps(await openCard($, w)), viewport: WIDE })
  await ui.press({ key: 'pgb-tasks' })
  await ui.press({ key: 'px-tasks-0' })
  await ui.press({ key: 'ta-do-task:alpha' })
  await ui.press({ key: 'team-pair-task:alpha' })
  expect(launches(w.calls)).toHaveLength(1)
  // the team was not taken as started: its button is still on offer, no progress line
  expect(await ui.find({ type: 'Button', key: 'team-pair-task:alpha' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'team-next-task:alpha' })).toBeUndefined()
})
