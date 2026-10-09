// Tests of the mod's pure functions (without Claude Code): merging two runs,
// number on the tab, who is really waiting, tabs from collect, the two text tables.
//
//   npx -y -p typescript@5.6.3 -c 'node mods/briefing-ui/tests/pure.test.mjs'
//
// TypeScript comes from the tsc on PATH (npx puts it there) or from TS=<path to typescript.js>.
//
// The script compiles every file under hooks/ with TypeScript to .mjs in a temp directory,
// appends '.mjs' to relative imports, replaces the import from 'claude-code' with simple
// stand-ins and checks the exported functions with node:test.
import { execSync } from 'node:child_process'
import { createRequire } from 'node:module'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { pathToFileURL, fileURLToPath } from 'node:url'
import test from 'node:test'
import assert from 'node:assert/strict'

const here = path.dirname(fileURLToPath(import.meta.url))
function findTypeScript() {
  if (process.env.TS) return process.env.TS
  let tsc = ''
  try {
    tsc = execSync('command -v tsc', { shell: '/bin/sh', stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim()
  } catch { /* no tsc on PATH */ }
  const lib = tsc && path.join(path.dirname(fs.realpathSync(tsc)), '..', 'lib', 'typescript.js')
  if (lib && fs.existsSync(lib)) return lib
  console.error("briefing-ui tests need TypeScript. Run them as: npx -y -p typescript@5.6.3 -c 'node mods/briefing-ui/tests/pure.test.mjs'"
    + ' (or set TS to the path of typescript.js)')
  process.exit(2)
}
const ts = createRequire(import.meta.url)(findTypeScript())

const hooks = path.join(here, '..', 'hooks')
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'briefing-ui-'))
for (const name of fs.readdirSync(hooks).filter(f => /\.tsx?$/.test(f))) {
  let js = ts.transpileModule(fs.readFileSync(path.join(hooks, name), 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.React,
      jsxFactory: 'h', jsxFragmentFactory: 'Fragment' },
  }).outputText
  js = js.replace(/import \{[^}]*\} from 'claude-code';?/, 'const atom = (k, d) => ({ key: k.key, d }); const read = async () => null; const update = async () => {}')
  js = js.replace(/(from\s+'\.\/[\w-]+)'/g, "$1.mjs'")
  fs.writeFileSync(path.join(dir, name.replace(/\.tsx?$/, '.mjs')), js)
}
const load = name => import(pathToFileURL(path.join(dir, `${name}.mjs`)).href)
const m = await load('logic')
const text = await load('text')
// loads the module itself: every import must resolve
await load('register')

const row = (key, sources, extra = {}) => ({ key, bucket: 'do', title: key, why: [], sources, inboxId: null, gate: null,
  task: null, ref: null, url: null, priority: null, urgency: null, area: null, areaNames: [], taskType: null,
  hasAction: false, inboxState: null, inboxKey: null, ...extra })
const section = (id, status, extra = {}) => ({ id, kind: 'x', title: id, status, reason: '', alarm: false, empty: 'nothing',
  items: [], count: 0, weight: 0, bad: 0, ...extra })
const view = (extra) => ({ headline: '', collectedAt: '', collectedMs: 0, isFull: false, fullMs: 0, skipped: [],
  buckets: [], agenda: [], status: [], pages: [], ...extra })

test('a quick run takes over from the previous one only what it left out', () => {
  const base = view({ isFull: true, fullMs: 5, headline: 'old', agenda: [{ when: '9', title: 'Meeting' }],
    buckets: [{ id: 'do', title: 'Do', rows: [row('gh#1', ['github']), row('old-inbox', ['inbox'])] }],
    pages: [{ id: 'g', title: 'GitHub', sections: [section('github', 'ok', { count: 1, weight: 1 })] }] })
  const fresh = view({ headline: 'new', skipped: ['github', 'calendar'],
    buckets: [{ id: 'do', title: 'Do', rows: [row('new-inbox', ['inbox'])] }],
    pages: [{ id: 'g', title: 'GitHub', sections: [section('github', 'skipped')] }] })
  const v = m.mergeView(base, fresh)
  assert.deepEqual(v.buckets[0].rows.map(r => r.key), ['new-inbox', 'gh#1'])   // a completed inbox row stays gone
  assert.equal(v.pages[0].sections[0].status, 'ok')
  assert.equal(v.headline, 'old')   // without a calendar the headline of the full run stays (it names dates)
  assert.deepEqual(v.agenda, [{ when: '9', title: 'Meeting' }])
  assert.equal(v.isFull, true)
  assert.equal(v.fullMs, 5)
  assert.deepEqual(v.skipped, [])
})

test('the second run keeps the headline and inbox of the first', () => {
  const quick = view({ headline: '3 for you', skipped: ['github'],
    buckets: [{ id: 'do', title: 'Do', rows: [row('inbox-1', ['inbox'])] }] })
  const rest = view({ headline: '', isFull: true, fullMs: 9, skipped: ['inbox'],
    buckets: [{ id: 'do', title: 'Do', rows: [row('gh#2', ['github'])] }] })
  const v = m.mergeView(quick, rest)
  assert.equal(v.headline, '3 for you')
  assert.deepEqual(v.buckets[0].rows.map(r => r.key).sort(), ['gh#2', 'inbox-1'])
})

test('an old saved view without skipped does not break the merge', () => {
  const stored = view({ skipped: undefined })
  assert.doesNotThrow(() => m.mergeView(stored, view({ skipped: ['calendar'] })))
})

test('number on the tab: red for findings, yellow only from sections that count, else ✓', () => {
  const warnItem = { title: 'x', detail: '', when: '', tone: 'warn', url: null, task: null, ask: false }
  assert.deepEqual(m.pageBadge({ id: 'a', title: 'A', sections: [section('s', 'ok', { bad: 2 })] }), { text: '✗2', color: 'red' })
  assert.deepEqual(m.pageBadge({ id: 'a', title: 'A', sections: [section('s', 'ok', { weight: 3, items: [warnItem] })] }),
    { text: '3', color: 'yellow' })
  // a yellow row in a section with badge: false does not color the number
  assert.deepEqual(m.pageBadge({ id: 'a', title: 'A', sections: [section('s', 'ok', { weight: 2 }),
    section('t', 'ok', { weight: 0, items: [warnItem] })] }), { text: '2', color: undefined })
  assert.deepEqual(m.pageBadge({ id: 'a', title: 'A', sections: [section('s', 'ok')] }), { text: '✓', color: 'green' })
})

test('a finished tab whose result sits in the inbox no longer waits', () => {
  const tab = (state, slug) => ({ name: slug, workspace: 'W', ref: `surface:${slug}`, wsRef: 'workspace:1', state, last: '',
    slug, item: null, team: null, role: null })
  const v = view({ buckets: [{ id: 'do', title: 'Do', rows: [row('r', ['inbox'], { inboxId: 'i1', inboxKey: 'tab-alpha-result' })] }] })
  assert.equal(m.isWaiting(tab('waiting', 'alpha'), v), false)
  assert.ok(m.filedBy(tab('waiting', 'alpha'), v))
  assert.equal(m.isWaiting(tab('waiting', 'beta'), v), true)
  assert.equal(m.isWaiting(tab('needs-you', 'alpha'), v), true)   // a permission prompt always waits
  assert.equal(m.isWaiting(tab('working', 'beta'), v), false)
})

test('a result belongs to exactly one tab via --task, even if one name is the start of another', () => {
  const tab = (slug) => ({ name: slug, workspace: 'W', ref: `surface:${slug}`, wsRef: 'workspace:1', state: 'waiting',
    last: '', slug, item: null, team: null, role: null })
  const v = view({ buckets: [{ id: 'do', title: 'Do', rows: [
    row('r', ['inbox'], { inboxId: 'i1', inboxKey: 'tab-alpha-beta-result', task: 'alpha-beta' })] }] })
  assert.equal(m.filedBy(tab('alpha'), v), undefined)
  assert.ok(m.filedBy(tab('alpha-beta'), v))
})

test('tabs from collect: briefing and empty tabs drop out, reasons and fields come along', () => {
  const pages = m.parsePages({ pages: [
    { id: 'briefing', title: 'X', sections: [{ id: 'a' }] },
    { id: 'empty', title: 'Empty', sections: [] },
    { id: 'gh', title: 'GitHub', sections: [{ id: 'mine', status: 'error', reason: 'gh: token invalid', items: [
      { title: 'T', when: '09:30', detail: 'open', tone: 'warn', url: 'https://x.test', task: 'alpha', ask: true }] }] },
  ] })
  assert.deepEqual(pages.map(p => p.id), ['gh'])
  const s = pages[0].sections[0]
  assert.equal(s.reason, 'gh: token invalid')
  assert.deepEqual(s.items[0], { title: 'T', detail: 'open', when: '09:30', tone: 'warn', url: 'https://x.test',
    task: 'alpha', ask: true, mark: null, priority: null, state: null, lines: [] })
  assert.equal(s.asOf, null)
})

test('mark and as-of time from collect arrive at row and section', () => {
  const pages = m.parsePages({ pages: [{ id: 'gh', title: 'GitHub', sections: [{ id: 'mine', status: 'ok', as_of: '08:46',
    items: [{ title: 'T', mark: { label: 'ACME', color: 'magenta' } }, { title: 'U', mark: { label: '' } }] }] }] })
  const s = pages[0].sections[0]
  assert.equal(s.asOf, '08:46')
  assert.deepEqual(s.items[0].mark, { label: 'ACME', color: 'magenta' })
  assert.equal(s.items[1].mark, null)   // without a word, no mark
  const v = m.parseView({ view: { buckets: [{ id: 'do', items: [{ title: 'X', sources: ['inbox'], mark: { label: 'ACME' } }] }] },
    sections: [] }, true, 0)
  assert.deepEqual(v.buckets[0].rows[0].mark, { label: 'ACME', color: null })
})

test('plan for today names appointments, open rows with mark and waiting tabs', () => {
  const v = view({ headline: '3 for you', collectedAt: '08:00', agenda: [{ when: '10:00', title: 'Weekly' }] })
  const text = m.planDay(v, [row('a', ['inbox'], { priority: 'P1', mark: { label: 'ACME', color: null } })],
    [{ name: 'fix', workspace: 'W', ref: 's:1', wsRef: 'w:1', state: 'needs-you', last: '', slug: 'fix', item: null, team: null, role: null }])
  assert.match(text, /10:00 Weekly/)
  assert.match(text, /P1 ACME\] a/)
  assert.match(text, /W \/ fix/)
})

test('configuration: own language before language.conversation, without both English', () => {
  assert.equal(m.parseConfig({ enabled: true, _language: 'de' }).language, 'de')
  assert.equal(m.parseConfig({ enabled: true, language: 'en', _language: 'de' }).language, 'en')
  assert.equal(m.parseConfig({ enabled: true, language: 'de-DE' }).language, 'de')
  assert.equal(m.parseConfig({ enabled: true }).language, 'en')
})

test('setLanguage: de... means German, everything else English', () => {
  text.setLanguage('de')
  assert.equal(text.T(), text.TABLES.de)
  text.setLanguage('fr')
  assert.equal(text.T(), text.TABLES.en)
  text.setLanguage('DE-at')
  assert.equal(text.T(), text.TABLES.de)
  text.setLanguage('en')
})

/** All texts of a table as [path, text]; functions with one sample value per parameter */
function leaves(value, at = '') {
  if (typeof value === 'string') return [[at, value]]
  if (typeof value === 'function') return [[`${at}()`, value(...new Array(Math.max(1, value.length)).fill(2))]]
  if (Array.isArray(value)) return value.flatMap((v, i) => leaves(v, `${at}[${i}]`))
  return Object.entries(value).flatMap(([k, v]) => leaves(v, at ? `${at}.${k}` : k))
}

function shape(value) {
  if (typeof value === 'string' || typeof value === 'function') return typeof value
  if (Array.isArray(value)) return value.map(shape)
  return Object.fromEntries(Object.keys(value).sort().map(k => [k, shape(value[k])]))
}

test('de and en have the same keys, nothing is empty', () => {
  const { de, en } = text.TABLES
  assert.deepEqual(shape(de), shape(en))
  for (const [where, value] of [...leaves(de), ...leaves(en)]) {
    assert.equal(typeof value, 'string', where)
    assert.ok(value.trim().length > 0, `empty: ${where}`)
  }
})

test('no dash in either table, no umlauts in the English one', () => {
  for (const [where, value] of [...leaves(text.TABLES.de), ...leaves(text.TABLES.en)]) {
    assert.doesNotMatch(value, /[—–]| - |--/, where)
  }
  for (const [where, value] of leaves(text.TABLES.en)) assert.doesNotMatch(value, /[äöüÄÖÜß]/, where)
})

test('the output of /briefing-ui carries the identifier of the card in both languages', () => {
  for (const t of Object.values(text.TABLES)) assert.match(t.cmdOutput('123'), /\(briefing-ui 123\)/)
})

test('the backup interval is named as configured: hourly only for 60 minutes', () => {
  const { de, en } = text.TABLES
  assert.equal(en.backupEvery(60), 'hourly')
  assert.equal(de.backupEvery(60), 'stündlich')
  assert.equal(en.backupEvery(30), 'every 30 min')
  assert.equal(de.backupEvery(30), 'alle 30 Min.')
})

// ---------------------------------------------------------------- tasks: rows, tabs, details

const ttab = (state, extra = {}) => ({ name: 'Alpha', workspace: 'W', ref: `surface:${state}`, wsRef: 'workspace:1', state,
  last: '', slug: 'alpha', item: null, team: null, role: null, ...extra })
const tinfo = (slug, extra = {}) => ({ slug, label: slug, area: 'Area', areaNames: ['Area'], priority: 'P1', blockedBy: null,
  stale: false, age: 0, type: null, ...extra })

test('a task with only inbox entries keeps its own row under the tasks, with the count of the entries', () => {
  text.setLanguage('en')
  const v = view({ buckets: [{ id: 'drop', title: 'Later', rows: [
    row('inbox:1', ['inbox'], { inboxId: '1', task: 'alpha', gate: 'only-you' }),
    row('inbox:2', ['inbox'], { inboxId: '2', task: 'alpha', gate: 'only-you' })] }] })
  const out = m.withTasks(v, [tinfo('alpha'), tinfo('beta')])
  const tasks = out.buckets.find(b => b.id === 'tasks').rows
  assert.deepEqual(tasks.map(r => r.key), ['task:alpha', 'task:beta'])
  assert.deepEqual(tasks[0].why, ['2 in the inbox'])
  // the inbox rows still carry the area of their task
  assert.equal(out.buckets[0].rows[0].area, 'Area')
})

test('a task that the briefing already lists as a task row is not added twice', () => {
  const v = view({ buckets: [{ id: 'do', title: 'Do', rows: [row('task:alpha', ['tasks'], { task: 'alpha' })] }] })
  const out = m.withTasks(v, [tinfo('alpha')])
  assert.equal(out.buckets.find(b => b.id === 'tasks'), undefined)
})

test('tabFor prefers a tab with a live agent over a dead shell tab of the same task', () => {
  const r = row('task:alpha', ['tasks'], { task: 'alpha' })
  assert.equal(m.tabFor(r, [ttab('working'), ttab('shell')]).state, 'working')
  assert.equal(m.tabFor(r, [ttab('shell')]).state, 'shell')     // still found: the card offers restart and jump
  assert.equal(m.isLive(ttab('shell')), false)
  assert.equal(m.isLive(ttab('waiting')), true)
})

test('a task row from the task list carries area, priority, type and why it rests', () => {
  const r = m.taskRowFor('alpha', 'Alpha title', [tinfo('alpha', { type: 'feature', blockedBy: 'vendor' })])
  assert.equal(r.key, 'task:alpha')
  assert.equal(r.area, 'Area')
  assert.equal(r.priority, 'P1')
  assert.equal(r.taskType, 'feature')
  assert.equal(r.why.length, 1)
  assert.equal(m.taskRowFor('gone', 'Gone', []).area, null)
})

test('a task row of a page brings its detail lines, priority and state', () => {
  const it = m.parseInfo({ title: 'A', task: 'alpha', priority: 'P2', state: 'doing',
    lines: [{ kind: 'step', text: 'first' }, { kind: 'log', text: '2026-10-07 x' }, { nope: 1 }] })
  assert.equal(it.priority, 'P2')
  assert.equal(it.state, 'doing')
  assert.deepEqual(it.lines, [{ kind: 'step', text: 'first' }, { kind: 'log', text: '2026-10-07 x' }])
  assert.deepEqual(m.parseInfo({ title: 'B' }).lines, [])
})
