import { mock } from 'claude-code/testing'
import type { Engine, MockClock } from 'claude-code/testing'
import type { On } from 'claude-code'

/**
 * A fake Bridge beneath the mod: every call the mod makes on `$` lands here.
 *
 * process.run answers by argv (the config reader, briefing.py collect, workplace.py,
 * inbox.py, cmux), every argv is recorded, and so are file writes, prompts and toasts.
 * Every fixture is synthetic: acme, beta-corp, alpha tasks.
 */

export const CWD = '/fake/bridge'
/** 2026-10-09 08:00 local time */
export const NOW = new Date(2026, 9, 9, 8, 0, 0).getTime()

export type Raw = Record<string, unknown>

/** One row of a bucket, in the shape scripts/lib/briefing_view.py build() emits. */
export function item(title: string, extra: Raw = {}): Raw {
  return {
    title, bucket: 'do', forced: false, mark: null, why: [], sources: ['inbox'], rank: 5, url: null, task: null,
    new: false, changed: false, ...extra,
  }
}

/** An inbox row waiting for a yes that runs an action. */
export function approvable(n: number): Raw {
  return item(`beta-corp invoice ${n}`, {
    bucket: 'delegate', inbox_id: `20261009-0800-beta-${n}`, inbox_key: `beta-${n}`, inbox_state: 'open',
    gate: 'your-yes', has_action: true,
  })
}

export type Section = Raw & { id: string }

/**
 * The output of `briefing.py collect --json --no-save`: sections, pages and the built view,
 * as scripts/briefing.py prints it.
 */
export function collect(opts: {
  buckets?: { id: string; title?: string; items: Raw[] }[]
  agenda?: { when: string; title: string }[]
  pages?: Raw[]
  headline?: string
  skipped?: string[]
} = {}): Raw {
  const skipped = opts.skipped ?? []
  const ids = ['inbox', 'advise', 'tasks', 'calendar', 'activity', 'tracker', 'command']
  return {
    profile: 'demo',
    title: 'Briefing',
    collected_at: '2026-10-09T08:00',
    sections: ids.map(id => ({ id, kind: id, title: id, status: skipped.includes(id) ? 'skipped' : 'ok', items: [],
      total: 0 })),
    owed: [],
    pages: opts.pages ?? [],
    view: {
      style: 'full', collected_at: '2026-10-09T08:00', headline: opts.headline ?? '', since: null,
      buckets: (opts.buckets ?? []).map(b => ({ id: b.id, title: b.title ?? b.id, options: [], items: b.items,
        total: b.items.length })),
      hygiene: [], workplace: [], more: 0, titles: {}, answer_keys: true, show_hygiene: true, color: 'auto',
      width: 100, labels: {}, activity: [], boards: [], overview: 'inline', status: [], report: {},
      agenda: (opts.agenda ?? []).map(a => ({ start: '2026-10-09T09:30', end: '2026-10-09T10:00', ...a })),
      clear: [], dayline: null,
    },
  }
}

/** A tab as `workplace.py status --json` lists it. */
export function tab(ref: string, state: string, extra: Raw = {}): Raw {
  const n = ref.replace(/\D/g, '')
  return {
    id: `uuid-${n}`, ref, ws_ref: 'workspace:2', workspace: 'acme', name: `alpha tab ${n}`, state, last: '',
    slug: null, item: null, team: null, role: null, ...extra,
  }
}

export type TaskAnswer = { exitCode?: number; stdout?: string; stderr?: string }

export type WorldOptions = {
  language?: 'de' | 'en'
  enabled?: boolean
  /** bridge-config.yaml and scripts/briefing.py exist at the cwd */
  isBridge?: boolean
  env?: Record<string, string>
  collect?: Raw
  /** answers briefing.py collect by its argv instead of `collect`, e.g. by --style */
  collectBy?: (argv: string[]) => Raw
  status?: Raw[]
  tasks?: Raw[]
  teams?: Raw[]
  /** what `workplace.py launch` answers (its --json output), by its argv */
  launch?: (argv: string[]) => Raw
  /** workplace.control.name */
  control?: string
  /** further claude_code_ui keys */
  ui?: Raw
  /** files the mod may read, by the path the mod passes (a relative one matches its resolved form) */
  files?: Record<string, string>
  /** what `task.py` answers (review, close), by its argv; default: an empty success */
  taskPy?: (argv: string[]) => TaskAnswer
  /** what the config reader (`python3 -c`) answers instead of the config, e.g. a YAML error */
  configRun?: { exitCode: number; stdout: string; stderr: string }
}

export type World = {
  calls: string[][]
  /** the timeout of each call in `calls`, at the same index */
  timeouts: number[]
  writes: { path: string; text: string }[]
  prompts: string[]
  toasts: string[]
  registered: string[]
  clock: MockClock
  /** what workplace.py status --json answers next; the test may change it */
  status: Raw[]
  collect: Raw
  /** argv of every call whose argv contains all the given words, in order of the calls */
  find: (...words: string[]) => string[][]
}

export function world(on: On, opts: WorldOptions = {}): World {
  const clock = mock.clock(on, { now: NOW })
  mock.store(on)
  mock.env(on, opts.env ?? { CMUX_SURFACE_ID: 'uuid-1' })
  const isBridge = opts.isBridge ?? true
  const config = {
    enabled: opts.enabled ?? true,
    language: opts.language ?? 'en',
    snapshot_minutes: 0,
    morning_hint: false,
    ...(opts.ui ?? {}),
    _control: opts.control ?? null,
    _language: null,
  }
  const w: World = {
    calls: [], timeouts: [], writes: [], prompts: [], toasts: [], registered: [], clock,
    status: opts.status ?? [],
    collect: opts.collect ?? collect(),
    find: (...words) => w.calls.filter(argv => words.every(x => argv.includes(x))),
  }
  const ok = (stdout: string) => ({ value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false,
    isStderrTruncated: false } })
  on('session.cwd', () => ({ value: CWD }))
  on('session.start', (_$, e) => ({ cwd: e.cwd }))
  on('fs.exists', (_$, e) => ({ value: isBridge && (e.path === `${CWD}/bridge-config.yaml`
    || e.path === `${CWD}/scripts/briefing.py`) }))
  on('fs.read', (_$, e) => {
    // a relative path reaches the hook resolved against the session's working directory
    const hit = Object.keys(opts.files ?? {}).find(k => e.path === k || e.path.endsWith(`/${k}`))
    const text = hit === undefined ? undefined : opts.files?.[hit]
    if (text === undefined) throw new Error(`ENOENT: ${e.path}`)
    return { value: text }
  })
  on('fs.write', (_$, e) => {
    w.writes.push({ path: e.path, text: e.text })
    return { value: undefined }
  })
  on('command.register', (_$, e) => {
    w.registered.push(e.name)
    return { value: { command: e.name } }
  })
  on('ui.toast', (_$, e) => {
    w.toasts.push(JSON.stringify(e))
    return { value: undefined }
  })
  on('ui.open', () => ({ value: { isPlaced: true as const } }))
  on('prompt.submit', (_$, e) => {
    w.prompts.push(e.text)
    return { text: e.text }
  })
  on('process.run', (_$, e) => {
    const argv = [...e.argv]
    w.calls.push(argv)
    w.timeouts.push(e.init?.timeoutMs ?? 0)
    if (argv[0] === 'python3' && argv[1] === '-c') {
      if (opts.configRun) return { value: { ...opts.configRun, isStdoutTruncated: false, isStderrTruncated: false } }
      return ok(JSON.stringify(config))
    }
    const script = argv[1] ?? ''
    if (script === 'scripts/briefing.py') return ok(JSON.stringify(opts.collectBy ? opts.collectBy(argv) : w.collect))
    if (script === 'scripts/workplace.py') {
      if (argv[2] === 'status') return ok(JSON.stringify(w.status))
      if (argv[2] === 'tasks') return ok(JSON.stringify(opts.tasks ?? []))
      if (argv[2] === 'teams') return ok(JSON.stringify(opts.teams ?? []))
      if (argv[2] === 'launch' && opts.launch) return ok(JSON.stringify(opts.launch(argv)))
      return ok('{"report": [], "items": []}')
    }
    if (script === 'scripts/inbox.py') return ok('')
    if (script === 'scripts/task.py' && opts.taskPy) {
      const answer = (r: TaskAnswer) => ({ value: { exitCode: r.exitCode ?? 0, stdout: r.stdout ?? '',
        stderr: r.stderr ?? '', isStdoutTruncated: false, isStderrTruncated: false } })
      return answer(opts.taskPy(argv))
    }
    // cmux send-key / close-surface / select-workspace / focus-panel, the layout snapshot
    return ok('')
  })
  return w
}

/** Starts the session and runs /briefing-ui; resolves with the text of its output row once loading settled. */
export async function openCard($: Engine, w: World): Promise<string> {
  await $.session.start({ cwd: CWD, surface: 'terminal', isInteractive: true })
  const out = await $.command.run(runInput())
  await w.clock.settle()
  return 'text' in out && typeof out.text === 'string' ? out.text : ''
}

/** /briefing-ui as the person types it at the prompt. */
export function runInput() {
  return { command: 'briefing-ui', args: '', origin: { kind: 'composer' as const },
    presentation: { isFullscreen: false, columns: 140 } }
}

/** The props of the /briefing-ui output row, for mounting the card. */
export function cardProps(text: string) {
  return { command: 'briefing-ui', args: '', text, isErrored: false }
}
