/** tab: in the caller's workspace · workspace: a new one per item · area: in the workspace of its area ·
 * auto: a small model picks the area or a dedicated workspace per item (workplace.router) */
export type Target = 'tab' | 'workspace' | 'area' | 'auto'
/** report: read and maintain · go: get started · context: look for missing context and note it */
export type Mode = 'report' | 'go' | 'context'

export type UiConfig = {
  enabled: boolean
  band: boolean
  shortcuts: boolean
  morningHint: boolean
  voice: boolean
  statusSeconds: number
  target: Target
  surface: 'chat' | 'pane'
  /** every how many minutes the cmux layout is saved, 0 = never */
  snapshotMinutes: number
  /** Name of the control workspace (workplace.control.name); only the session in it polls and reports */
  control: string | null
  /** UI language: briefing.claude_code_ui.language, else language.conversation, else en */
  language: 'de' | 'en'
  /** How old the full run may be when the dashboard opens before it runs again (full_minutes) */
  fullMinutes: number
}

/** Mark from view.marks in the profile (customer, project): word and color live only there, never in code */
export type Mark = { label: string; color: string | null }

export type Row = {
  key: string
  bucket: string
  title: string
  why: string[]
  sources: string[]
  inboxId: string | null
  gate: string | null
  task: string | null
  ref: string | null
  url: string | null
  priority: string | null
  urgency: string | null
  /** Area (workspace) of a task */
  area: string | null
  /** Name and alias names of the area, as cmux workspaces may be called */
  areaNames: string[]
  /** Kind of task (feature, research, ...), for the team suggestion */
  taskType: string | null
  /** Inbox entry with an executable action: a yes runs it; without one it needs a tab */
  hasAction: boolean
  /** State of the inbox entry: approved means the yes is given and the runner executes it */
  inboxState: string | null
  /** Key of the inbox entry; tab-<slug>-... means the task's tab filed it */
  inboxKey: string | null
  mark: Mark | null
}

/** One row of the status tabs, ready from collect (pages): columns When, Title, Detail, Link */
export type Info = {
  title: string
  /** State or place, to the right */
  detail: string
  /** Time or figure up front */
  when: string
  tone: 'bad' | 'warn' | 'dim' | null
  /** Web address or file:// link to a file of the bridge */
  url: string | null
  /** Task the row belongs to: "to the tab" or "open tab" */
  task: string | null
  /** Finding or issue: "ask" brings it into the conversation */
  ask: boolean
  mark: Mark | null
  /** Task rows only: priority and status, and what opening the row shows (origin, next, blocked, steps, log) */
  priority: string | null
  state: string | null
  lines: InfoLine[]
}
/** One line of an opened task row; the kind picks its label in the card's language */
export type InfoLine = { kind: string; text: string }
/** A section on a tab; skipped means: only in the full run. weight and bad count toward the number on the tab */
export type InfoSection = {
  id: string; kind: string; title: string; status: string
  /** Reason if the section could not be read (invalid token, timeout, ...) */
  reason: string
  /** each row is a finding (red), empty means all green */
  alarm: boolean
  /** Text for an empty section */
  empty: string
  items: Info[]; count: number; weight: number; bad: number
  /** From the cache (cache_minutes): when the source last answered; null = fresh */
  asOf: string | null
}
/** A tab next to the briefing, as the profile describes it (view.pages) */
export type InfoPage = { id: string; title: string; sections: InfoSection[] }
/** briefing or the id of a tab from the profile */
export type PageId = string

export type Bucket = { id: string; title: string; rows: Row[] }

export type View = {
  headline: string
  collectedAt: string
  /** Time of the collection in ms, for the cache of the full version */
  collectedMs: number
  isFull: boolean
  /** Time of the last full collection (tracker, calendar), for the cache */
  fullMs: number
  /** Sections this collection left out (quick version) */
  skipped: string[]
  buckets: Bucket[]
  agenda: { when: string; title: string }[]
  status: { title: string; count: number; isHealthy: boolean }[]
  pages: InfoPage[]
}

export type Tab = {
  name: string
  workspace: string
  ref: string
  wsRef: string
  state: string
  last: string
  /** Task the tab works on */
  slug: string | null
  /** Inbox entry the tab works on */
  item: string | null
  /** Team recipe and role, if the tab is one role of a team */
  team: string | null
  role: string | null
}

/** Since when a tab has been in its state, and whether it has already been reported for it */
export type TabSeen = { state: string; since: number; isWarned: boolean }

export type TeamRole = { id: string; name: string; mode: 'report' | 'go' }
export type Team = { id: string; label: string; forTypes: string[]; roles: TeamRole[] }
/** What the card started for a task: team, roles in order, time of the last start */
export type TeamRun = { team: string; roles: string[]; at: number }

/** now: waits for you · give: to hand off · work: your tasks · later: later */
export type SectionId = 'now' | 'give' | 'work' | 'later'
/** The tabs of the sidebar: everything stacked, the four blocks individually, and the tabs */
export type SideTab = 'all' | SectionId | 'tabs'

/** One active task from `workplace.py tasks --json` */
export type TaskInfo = { slug: string; label: string; area: string; areaNames: string[]; priority: string | null
  blockedBy: string | null; stale: boolean; age: number; type: string | null
  /** a long-runner under work/streams/: it never closes */
  isStream: boolean }

/** One recommendation of `task.py review`: what to do with a task, why, and which model said so */
export type Review = { slug: string; verdict: 'close' | 'continue' | 'waiting' | 'stale' | 'unclear'; reason: string
  confidence: string; model: string | null; cached: boolean; kept: boolean
  /** GitHub says done (own refs closed, or the blocker resolved): a close is recommended whatever the model said */
  resolved: boolean; closedRefs: string[]
  /** what blocked_by names is closed or merged: a hint, never a close by itself */
  unblocked: boolean }

declare module 'claude-code' {
  interface PluginState {
    'briefing-ui': {
      config: UiConfig | null
      view: View | null
      loading: string | null
      tabs: Tab[]
      selected: string[]
      settled: string[]
      expanded: string | null
      notes: string[]
      isBandHidden: boolean
      messageTo: string | null
      /** Row key -> hidden until (YYYY-MM-DD, exclusive) */
      hidden: Record<string, string>
      openSection: SectionId | null
      showAll: boolean
      showTabs: boolean
      /** Id of the newest card in the chat; older ones draw as a single line */
      cardId: string | null
      isClosed: boolean
      showHelp: boolean
      helpLang: 'de' | 'en'
      teams: Team[]
      /** Task -> what the card started from the team */
      teamOf: Record<string, TeamRun>
      /** Tab ref -> since when in which state */
      tabSeen: Record<string, TabSeen>
      /** Last save of the cmux layout (time) and the list of saves, when expanded */
      lastSnapshot: string | null
      snapshots: string[] | null
      /** Sidebar: selected tab, page, whether "more" under the open row is expanded */
      sideTab: SideTab
      sidePage: number
      sideMore: boolean
      page: PageId
      /** Duration of the last quick run and second run (rest) in ms, for the loading indicator */
      loadTook: Record<string, number>
      /** Why the tab state is not current, and since when; null = current */
      tabsError: string | null
      /** This session is the control workspace (in the workspace from workplace.control): only it polls and reports.
       * null = not yet known or without cmux (then as before: each session on its own) */
      isControl: boolean | null
      /** Items (task slugs, inbox ids) whose tab is starting right now: a second click does not start a second one */
      starting: string[]
      /** The active tasks as workplace.py tasks lists them; an opened task row of a page takes area and priority from it */
      taskInfo: TaskInfo[]
      /** the last recommendation per task slug (task.py review, or its cache file on open) */
      reviews: Record<string, Review>
      /** a review is running: 'all' or the slugs it checks */
      reviewing: string | null
      /** the first click on Done/Close: the second within a few seconds closes */
      confirmClose: { slug: string; at: number } | null
      /** tasks closed from the card in this session: their rows stay away */
      closedTasks: string[]
      /** "release all N" pressed: the confirmation prompt is showing */
      confirmAll: boolean
      /** why bridge-config.yaml could not be read; null when it was read */
      configError: string | null
      /** collect is asked for the triage view: an earlier answer had no view */
      askTriage: boolean
    }
  }
}
