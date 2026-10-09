// A newcomer's setup: no cmux, no briefing profile of their own, a backup interval other than an hour.
import { test, expect } from 'claude-code/testing'
import { approvable, cardProps, collect, CWD, openCard, tab, world } from './world'

const WIDE = { columns: 140, rows: 60 }
const LAYOUT = 'skills/cmux/scripts/cmux_layout.py'
const isSnapshot = (argv: string[]) => argv[1] === LAYOUT && argv[2] === 'snapshot'
const isCollect = (argv: string[]) => argv[1] === 'scripts/briefing.py' && argv[2] === 'collect'

test('outside cmux the layout backup never runs, however long the session lasts', async ($, on) => {
  const w = world(on, { env: {}, ui: { snapshot_minutes: 30 } })
  await $.session.start({ cwd: CWD, surface: 'terminal', isInteractive: true })
  await w.clock.settle()
  await w.clock.advance(61000)
  await w.clock.advance(30 * 60000)
  expect(w.calls.filter(isSnapshot)).toEqual([])
})

test('inside cmux the layout backup runs once a minute after the start (control for the test above)', async ($, on) => {
  const w = world(on, { ui: { snapshot_minutes: 30 } })
  await $.session.start({ cwd: CWD, surface: 'terminal', isInteractive: true })
  await w.clock.settle()
  await w.clock.advance(61000)
  expect(w.calls.filter(isSnapshot)).toHaveLength(1)
})

test('outside cmux the card claims no backup, even when tabs are listed', async ($, on) => {
  const w = world(on, { env: {}, ui: { snapshot_minutes: 30 }, status: [tab('surface:12', 'working')] })
  const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
    props: cardProps(await openCard($, w)), viewport: WIDE })
  expect(await ui.find({ type: 'Button', key: 'tabs-toggle' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Backup/ })).toBeUndefined()
  expect(await ui.find({ type: 'Button', key: 'snap-now' })).toBeUndefined()
})

test('the backup line names the configured interval, not always hourly', async ($, on) => {
  const w = world(on, { ui: { snapshot_minutes: 30 } })
  const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
    props: cardProps(await openCard($, w)), viewport: WIDE })
  expect(await ui.find({ type: 'Text', text: /Backup every 30 min/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /hourly/ })).toBeUndefined()
})

test('a profile without a view is collected once more in the triage view, and then straight away', async ($, on) => {
  const { view: _none, ...bare } = collect()
  const triage = collect({ buckets: [{ id: 'delegate', items: [approvable(1)] }] })
  const w = world(on, { collectBy: argv => (argv.includes('--style') ? triage : bare) })
  const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
    props: cardProps(await openCard($, w)), viewport: WIDE })
  const runs = w.calls.filter(isCollect)
  expect(runs[0]).not.toContain('--style')
  expect(runs.length).toBeGreaterThanOrEqual(2)
  for (const argv of runs.slice(1)) expect(argv.join(' ')).toContain('--style triage')
  expect(await ui.find({ type: 'Text', text: /beta-corp invoice 1/ })).toBeDefined()
  // a reload in the same session does not ask for the bare view again
  const before = w.calls.length
  await ui.press({ key: 'reload' })
  await w.clock.settle()
  const again = w.calls.slice(before).filter(isCollect)
  expect(again.length).toBeGreaterThan(0)
  for (const argv of again) expect(argv.join(' ')).toContain('--style triage')
})
