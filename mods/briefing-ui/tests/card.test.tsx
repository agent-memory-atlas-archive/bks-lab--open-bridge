// The card as the engine draws it: language, switched off, marks, as-of times, life without cmux.
import { test, expect } from 'claude-code/testing'
import { cardProps, collect, item, openCard, runInput, tab, world } from './world'

const LANGS = ['de', 'en'] as const
const WIDE = { columns: 140, rows: 60 }

const PLAN = { de: 'Plan für heute', en: 'Plan my day' }
const RELOAD = { de: '⟳ neu', en: '⟳ reload' }
const OFF = {
  de: 'briefing-ui ist aus: briefing.claude_code_ui.enabled in bridge-config.yaml auf true setzen.',
  en: 'briefing-ui is off: set briefing.claude_code_ui.enabled to true in bridge-config.yaml.',
}
const AS_OF = { de: 'Stand 07:46', en: 'as of 07:46' }
const TABS_WAITING = { de: /Tabs warten/, en: /tabs waiting/ }
const BACKUP = { de: /Sicherung/, en: /Backup/ }

const SIDE_NOW = { de: 'Jetzt 1', en: 'Now 1' }
const PANE_PROPS = { title: 'Briefing', isFocused: true, bodyColumns: 60, placement: 'dock' as const,
  scroll: { offset: 0, bodyRows: 40 }, view: {} }

for (const lang of LANGS) {
  for (const surface of ['terminal', 'desktop'] as const) {
    test(`the card draws its buttons in the configured language (${lang}, ${surface})`, async ($, on) => {
      const w = world(on, { language: lang })
      const ui = await $.ui.mount({ plugin: 'briefing-ui', surface, component: 'CommandOutput',
        props: cardProps(await openCard($, w)), viewport: WIDE })
      expect((await ui.find({ type: 'Button', key: 'plan' }))?.props.label).toBe(PLAN[lang])
      expect((await ui.find({ type: 'Button', key: 'reload' }))?.props.label).toBe(RELOAD[lang])
      const other = lang === 'de' ? 'en' : 'de'
      expect(await ui.find({ type: 'Button', text: PLAN[other] })).toBeUndefined()
    })
  }

  test(`the sidebar pane draws its tabs in the configured language (${lang})`, async ($, on) => {
    const w = world(on, { language: lang, collect: collect({ buckets: [{ id: 'do', items: [item('alpha rollout',
      { task: 'alpha-rollout', sources: ['tasks'] })] }] }) })
    await openCard($, w)
    const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'Pane',
      requestId: 'briefing-ui', props: PANE_PROPS })
    expect((await ui.find({ type: 'Button', key: 'st-now' }))?.props.label).toBe(SIDE_NOW[lang])
  })

  test(`switched off inside a Bridge, /briefing-ui still exists and says how to switch it on (${lang})`, async ($, on) => {
    const w = world(on, { language: lang, enabled: false })
    await $.session.start({ cwd: '/fake/bridge', surface: 'terminal', isInteractive: true })
    await w.clock.settle()
    expect(w.registered).toEqual(['briefing-ui'])
    const out = await $.command.run(runInput())
    expect(out).toMatchObject({ text: OFF[lang] })
    await w.clock.settle()
    expect(w.find('scripts/briefing.py')).toHaveLength(0)
    expect(w.find('scripts/workplace.py')).toHaveLength(0)
  })

  test(`a row's mark label is drawn before its title, a cached section shows its as-of time (${lang})`, async ($, on) => {
    const w = world(on, {
      language: lang,
      collect: collect({
        buckets: [{ id: 'do', items: [item('alpha rollout', { task: 'alpha-rollout', sources: ['tasks'],
          mark: { label: 'beta-corp', color: 'cyan' } })] }],
        pages: [{ id: 'trackers', title: 'Trackers', sections: [{
          id: 'tracker', kind: 'tracker', title: 'Issues', status: 'ok', reason: '', alarm: false, empty: 'nothing',
          items: [{ title: 'acme/alpha#7 login fails', when: '08:10', detail: 'open', tone: null, url: null,
            task: null, ask: false, mark: null }],
          total: 1, weight: 1, bad: 0, as_of: '07:46',
        }] }],
      }),
    })
    const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
      props: cardProps(await openCard($, w)), viewport: WIDE })
    const title = await ui.find({ type: 'Text', text: /alpha rollout/ })
    expect(title?.text).toStartWith('beta-corp alpha rollout')
    expect(title?.children[0]).toMatchObject({ type: 'Text', props: { color: 'cyan' }, children: ['beta-corp '] })
    // the as-of time belongs to the status tab, not to the briefing
    expect(await ui.find({ type: 'Text', text: AS_OF[lang] })).toBeUndefined()
    await ui.press({ key: 'pgb-trackers' })
    expect(await ui.find({ type: 'Text', text: AS_OF[lang] })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /acme\/alpha#7 login fails/ })).toBeDefined()
  })

  test(`without cmux there is no tab line and no backup line; an empty view points at the docs (${lang})`, async ($, on) => {
    const w = world(on, { language: lang, env: {}, status: [] })
    const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
      props: cardProps(await openCard($, w)), viewport: WIDE })
    expect(await ui.find({ type: 'Text', text: TABS_WAITING[lang] })).toBeUndefined()
    expect(await ui.find({ type: 'Text', text: BACKUP[lang] })).toBeUndefined()
    expect(await ui.find({ type: 'Button', key: 'snap-now' })).toBeUndefined()
    expect(await ui.find({ type: 'Button', key: 'tabs-toggle' })).toBeUndefined()
    expect((await ui.find({ type: 'Text', text: /docs\/briefing-dashboard\.md/ }))?.text).toBeDefined()
  })
}

test('outside a Bridge the mod registers nothing and runs nothing', async ($, on) => {
  const w = world(on, { isBridge: false })
  await $.session.start({ cwd: '/fake/bridge', surface: 'terminal', isInteractive: true })
  await w.clock.settle()
  expect(w.registered).toEqual([])
  expect(w.calls).toEqual([])
})

test('with cmux the tab line and the backup line are there (control for the test above)', async ($, on) => {
  const w = world(on, { status: [tab('surface:12', 'working')] })
  const ui = await $.ui.mount({ plugin: 'briefing-ui', surface: 'terminal', component: 'CommandOutput',
    props: cardProps(await openCard($, w)), viewport: WIDE })
  expect(await ui.find({ type: 'Text', text: /tabs waiting/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Backup/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'snap-now' })).toBeDefined()
  // a working tab does not wait for you: the empty hint still stands
  expect(await ui.find({ type: 'Text', text: /docs\/briefing-dashboard\.md/ })).toBeDefined()
})
