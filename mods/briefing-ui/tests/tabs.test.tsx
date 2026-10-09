// Steering agent tabs from the card: answering a permission prompt, closing a finished tab,
// and which of two sessions in the control workspace polls and files the shared tab state.
import { test, expect } from 'claude-code/testing'
import { cardProps, collect, CWD, item, openCard, tab, world } from './world'

const WIDE = { columns: 140, rows: 60 }
const SHARED = '.bridge/briefing-ui/tabs.json'
// The mod names the file relative to the session's working directory; the engine resolves it before any hook.
const isShared = (path: string) => path === SHARED || path.endsWith(`/${SHARED}`)

const indexOf = (calls: string[][], pick: (argv: string[]) => boolean, from = 0) =>
  calls.findIndex((argv, i) => i >= from && pick(argv))
const isStatus = (argv: string[]) => argv[1] === 'scripts/workplace.py' && argv[2] === 'status'
const isSendKey = (argv: string[]) => argv[1] === 'send-key'

test('Yes on a tab that needs you sends 1 to that tab, after a fresh status still says needs-you', async ($, on) => {
  const w = world(on, { status: [tab('surface:12', 'needs-you', { ws_ref: 'workspace:5' })] })
  const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
    props: cardProps(await openCard($, w)), viewport: WIDE })
  const before = w.calls.length
  await ui.press({ key: 'yes-surface:12' })
  const status = indexOf(w.calls, isStatus, before)
  const send = indexOf(w.calls, isSendKey, before)
  expect(status).toBeGreaterThanOrEqual(before)
  expect(send).toBeGreaterThan(status)
  expect(w.calls.filter(isSendKey)).toEqual([['cmux', 'send-key', '--workspace', 'workspace:5', '--surface',
    'surface:12', '1']])
})

test('Yes sends nothing when the fresh status says the tab is working again', async ($, on) => {
  const w = world(on, { status: [tab('surface:12', 'needs-you')] })
  const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
    props: cardProps(await openCard($, w)), viewport: WIDE })
  expect(await ui.find({ type: 'Button', key: 'yes-surface:12' })).toBeDefined()
  // the card still says needs-you, the tab has moved on meanwhile
  w.status = [tab('surface:12', 'working')]
  const before = w.calls.length
  await ui.press({ key: 'yes-surface:12' })
  await w.clock.advance(5000)
  expect(indexOf(w.calls, isStatus, before)).toBeGreaterThanOrEqual(before)
  expect(w.calls.filter(isSendKey)).toEqual([])
  expect(w.toasts.join('\n')).toContain('is no longer asking')
})

test('No on a tab that needs you sends escape to that tab', async ($, on) => {
  const w = world(on, { status: [tab('surface:12', 'needs-you')] })
  const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
    props: cardProps(await openCard($, w)), viewport: WIDE })
  await ui.press({ key: 'no-surface:12' })
  expect(w.calls.filter(isSendKey)).toEqual([['cmux', 'send-key', '--workspace', 'workspace:2', '--surface',
    'surface:12', 'escape']])
})

test('Close tab on a waiting tab with a filed result closes exactly that surface in its workspace', async ($, on) => {
  const w = world(on, {
    status: [tab('surface:14', 'waiting', { slug: 'alpha-docs', ws_ref: 'workspace:7' }),
      tab('surface:15', 'waiting', { ws_ref: 'workspace:8' })],
    collect: collect({ buckets: [{ id: 'delegate', items: [item('alpha docs: result', {
      bucket: 'delegate', inbox_id: '20261009-0700-alpha-docs', inbox_key: 'tab-alpha-docs-20261009', gate: 'free',
      task: 'alpha-docs', inbox_state: 'open' })] }] }),
  })
  const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
    props: cardProps(await openCard($, w)), viewport: WIDE })
  // the tab with the filed result no longer waits for you: it sits in the list of all tabs
  await ui.press({ key: 'tabs-toggle' })
  // the other waiting tab has no result: it gets "go on", not "close"
  expect(await ui.find({ type: 'Button', key: 'close-surface:15' })).toBeUndefined()
  await ui.press({ key: 'close-surface:14' })
  expect(w.calls.filter(argv => argv[1] === 'close-surface')).toEqual([['cmux', 'close-surface', '--surface',
    'surface:14', '--workspace', 'workspace:7']])
})

// Two Claude sessions in the control workspace "ctl": surface:3 and surface:7, plus a plain shell at surface:1
// that does not count. Only surface:3 polls cmux and files the shared tab state for the others.
const CONTROL = [
  tab('surface:1', 'shell', { workspace: 'ctl', id: 'uuid-1' }),
  tab('surface:3', 'working', { workspace: 'ctl', id: 'uuid-3' }),
  tab('surface:7', 'working', { workspace: 'ctl', id: 'uuid-7' }),
  tab('surface:9', 'waiting', { workspace: 'acme', id: 'uuid-9' }),
]

test('in the control workspace the session with the lower surface ref polls and files the shared tab state', async ($, on) => {
  const w = world(on, { control: 'ctl', env: { CMUX_SURFACE_ID: 'uuid-3' }, status: CONTROL })
  await $.session.start({ cwd: CWD, surface: 'terminal', isInteractive: true })
  await w.clock.settle()
  expect(w.writes.filter(x => isShared(x.path))).toHaveLength(1)
  const filed = JSON.parse(w.writes[0]?.text ?? '{}') as { at: number; tabs: { ref: string; is_self: boolean }[] }
  expect(filed.tabs.map(t => t.ref)).toEqual(['surface:1', 'surface:3', 'surface:7', 'surface:9'])
  expect(filed.tabs.every(t => t.is_self === false)).toBe(true)
  const polled = w.calls.filter(isStatus).length
  await w.clock.advance(60000)
  expect(w.calls.filter(isStatus).length).toBe(polled + 1)
  expect(w.writes.filter(x => isShared(x.path))).toHaveLength(2)
})

test('the session with the higher surface ref never writes the shared file and reads it instead of polling', async ($, on) => {
  const w = world(on, {
    control: 'ctl', env: { CMUX_SURFACE_ID: 'uuid-7' }, status: CONTROL,
    files: { [SHARED]: JSON.stringify({ at: new Date(2026, 9, 9, 8, 0, 30).getTime(), tabs: CONTROL }) },
  })
  await $.session.start({ cwd: CWD, surface: 'terminal', isInteractive: true })
  await w.clock.settle()
  // the first beat has to ask cmux itself: only the answer says who is control
  const polled = w.calls.filter(isStatus).length
  expect(polled).toBe(1)
  await w.clock.advance(60000)
  expect(w.calls.filter(isStatus).length).toBe(polled)
  expect(w.writes.filter(x => isShared(x.path))).toEqual([])
})
