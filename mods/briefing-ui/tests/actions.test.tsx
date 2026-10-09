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
