import type { SectionId, SideTab, Target } from '../types'

/**
 * Every text the mod shows or sends to Claude, in German and English.
 * The language comes from bridge-config.yaml (briefing.claude_code_ui.language, else
 * language.conversation); until the configuration has been read, English applies.
 */
export type Strings = {
  // States and names
  state: Record<string, string>
  urgency: Record<string, string>
  section: Record<SectionId, string>
  where: Record<Target, string>
  /** Short button texts under 120 columns, per action id */
  shortLabel: Record<string, string>
  side: Record<SideTab, string>
  help: [string, string][]
  briefing: string
  bucketTasks: string
  bucketResting: string
  empty: string
  blocked: (by: string) => string
  quietFor: (days: number) => string
  waitingFor: (d: string) => string
  runningFor: (d: string) => string

  // Results of an action (some of them already report themselves)
  resDo: string
  resLater: string
  resDrop: string
  resDone: string
  resStarted: string
  resPartly: string
  resFailed: string
  resHidden: string
  resAsked: string
  noInbox: string
  nothingToStart: string
  nothingToDo: string
  noTask: string
  allRolesStarted: string
  waitsForRole: (name: string) => string
  prevRole: string

  // Buttons
  btnDo: string
  btnAdvise: string
  btnDrop: string
  btnDone: string
  btnNudge: string
  btnAskClaude: string
  btnApproved: string
  btnToTab: string
  btnYes: string
  btnNo: string
  btnCloseTab: string
  btnGoOn: string
  btnOpenTab: string
  btnAsk: string
  btnOpen: string
  btnTomorrow: string
  btnMonday: string
  btnWeek: string
  btnUntil: string
  btnCollect: string
  btnNote: string
  btnOwnWs: string
  btnDoOwnWs: string
  btnEachOwnWs: string
  btnAskChat: string
  btnPickAll: string
  btnLess: string
  btnMore: string
  btnCompact: string
  btnAll: string
  btnReload: string
  btnSort: string
  btnPlan: string
  emptyHint: string
  approveAll: (n: number) => string
  approveAsk: (n: number) => string
  approveYes: string
  approveNo: string
  sourceAsOf: (time: string) => string
  planHead: (at: string, headline: string) => string
  planAgenda: string
  planRows: string
  planTabs: string
  planTail: string
  btnEvening: string
  btnSidebar: string
  btnSave: string
  btnList: string
  btnClose: string
  btnShow: string
  btnShowAgain: string
  btnClear: string
  btnSend: string
  btnReopen: string
  btnDashboard: string
  btnView: string
  tabsClose: string
  tabsAll: (n: number) => string

  // Card and sidebar
  asOf: string
  loading: string
  loadingWhat: (what: string) => string
  noTracker: string
  resultFiled: string
  resultFiledLong: string
  toTabLabel: string
  toTabPlaceholder: string
  msgPlaceholder: string
  tabInfo: (ws: string, name: string, state: string) => string
  laterPrefix: string
  hidePrefix: string
  datePlaceholder: string
  noDate: (text: string) => string
  urgencyPrefix: string
  prioPrefix: string
  teamPrefix: string
  teamProgress: (label: string, started: number, all: number) => string
  teamStillWorking: (name: string) => string
  teamNew: string
  contextPrefix: string
  notePlaceholder: string
  adoptPrefix: string
  moreRows: (n: number) => string
  moreWork: string
  moreArrow: (n: number) => string
  helpTitle: string
  skippedSection: string
  unreadable: (why: string) => string
  startingTab: string
  btnRestart: string
  startPrefix: string
  inboxOpen: (n: number) => string
  /** Label before a line of an opened task row, by its kind (origin, next, blocked, step, log) */
  lineKind: Record<string, string>
  /** A task's status (frontmatter enum) in words; an unknown value is shown as it is */
  taskState: Record<string, string>
  /** "in area <name>": a start into the workspace of a named area */
  whereArea: (name: string) => string
  alreadyOpen: (label: string) => string
  startingAlready: (title: string) => string
  nothingHere: string
  waitCount: (n: number) => string
  longCount: (n: number) => string
  workingCount: (n: number) => string
  tabsWaiting: (n: number) => string
  counts: (now: number, give: number, work: number, later: number) => string
  inboxRule: string
  backup: string
  backupAt: (time: string) => string
  /** how often the layout is saved, from snapshot_minutes (0: only on Save) */
  backupEvery: (minutes: number) => string
  picked: (n: number) => string
  hiddenUntil: (date: string) => string
  hiddenCount: (n: number) => string
  agenda: string
  alarmUnder: (n: number, title: string) => string
  restoreHint: string
  olderCard: (when: string) => string
  earlier: string
  closedCard: (n: number) => string
  bandShort: (n: number) => string
  bandLong: (n: number) => string
  bandLongCount: (n: number) => string
  bandCountsShort: (now: number, give: number) => string
  bandCountsLong: (now: number, give: number) => string

  // Feedback
  alreadyLoading: string
  loadTasks: string
  loadQuick: (guess: string) => string
  loadRest: (guess: string) => string
  seconds: (n: number) => string
  loadFailed: (err: string) => string
  viewUnreadable: (err: string) => string
  statusFailed: string
  tabsStale: (time: string, why: string) => string
  tabToast: (name: string, state: string) => string
  voiceWaiting: (name: string) => string
  saved: string
  saveFailed: (err: string) => string
  listUnreadable: (err: string) => string
  approveFailed: (err: string) => string
  approvedNote: string
  approvedPending: (title: string) => string
  laterFailed: (err: string) => string
  laterBack: (until: string) => string
  hiddenNote: (until: string, title: string) => string
  urgencySet: (word: string, title: string) => string
  urgencyFailed: (err: string) => string
  prioFailed: (err: string) => string
  dropFailed: (err: string) => string
  dropped: string
  dropInboxNote: string
  doneFailed: (err: string) => string
  doneInboxNote: string
  launchTeam: (role: string) => string
  launchContext: string
  launchStart: (word: string, n: number, where: string) => string
  ownWs: string
  partlyStarted: (n: number) => string
  startFailed: string
  adopted: (tab: string, title: string) => string
  adoptFailed: (err: string) => string
  noteOnly: string
  noteAdded: (title: string, line: string) => string
  noteFailed: (err: string) => string
  jumpFailed: (err: string) => string
  notAsking: (name: string) => string
  keyFailed: (err: string) => string
  saidYes: string
  saidNo: string
  tabClosed: (name: string) => string
  closeFailed: (err: string) => string
  sentTo: (name: string, text: string) => string
  sendFailed: (err: string) => string
  goOnMessage: string

  // What the mod sends to Claude
  askAbout: (title: string, where: string) => string
  askInfo: (section: string, title: string, extra: string) => string
  followUp: (title: string, why: string) => string
  overviewHead: (at: string, headline: string) => string
  overviewTail: string
  evening: string
  eveningTabs: string
  eveningSince: (d: string) => string
  eveningLast: (last: string) => string

  // Commands, band, shortcuts
  cmdDesc: string
  cmdOffDesc: string
  cmdDisabled: string
  /** bridge-config.yaml exists but could not be read; the reason follows */
  readFailed: (err: string) => string
  /** must contain "(briefing-ui <id>)": that is how the card recognizes itself */
  cmdOutput: (id: string) => string
  bandOff: string
  morning: string
  scMissing: (n: number) => string
  scHasTab: (n: number, title: string) => string
  scApproved: string
  scWaiting: string
  scOnlyYou: string
  scResult: (said: string) => string
}

const de: Strings = {
  state: { 'needs-you': 'braucht dich', waiting: 'wartet', working: 'arbeitet', shell: 'Terminal' },
  urgency: { now: 'jetzt', today: 'heute', later: 'später' },
  section: { now: 'Wartet auf dich', give: 'Zum Weggeben', work: 'Deine Aufgaben', later: 'Später' },
  where: { area: 'im Bereich', tab: 'als Tab hier', workspace: 'im eigenen Workspace', auto: 'dort, wo es hinpasst' },
  shortLabel: { advise: 'Berate', nudge: 'Nachfass.', ask: 'fragen' },
  side: { all: 'Alles', now: 'Jetzt', give: 'Ja', work: 'Aufgaben', later: 'Später', tabs: 'Tabs' },
  help: [
    ['Reiter oben', 'Briefing: was wartet und was du weggibst · daneben die Reiter deines Briefing-Profils (view.pages in workflow/briefings/<id>.yaml, sonst je Art: Status, Termine, Tracker, Heute, Weitere) · Zahl: was zählt, ✗ rot Befunde, ✓ alles grün · ohne Tokens; GitHub und die Systemprüfungen kommen mit dem vollen Lauf (⟳, beim Öffnen, wenn der letzte älter ist als full_minutes) · „Stand 08:46“: so alt sind die Zeilen aus dem Zwischenspeicher, ⟳ fragt frisch'],
    ['Getestet', 'nur mit Claude Code und cmux; andere Agenten und Terminals folgen später'],
    ['Kopfzeile', '⟳ neu laden · alles: jeden Block aufklappen · einordnen: Claude priorisiert (Tokens) · Plan für heute: Claude legt die Reihenfolge in deine freien Zeiten (Tokens) · Feierabend · Leiste: Seitenleiste öffnen · ? Hilfe · ✕ Karte zuklappen, „aufklappen“ holt sie zurück'],
    ['Farben', '● rot braucht dich, gelb wartet, grün arbeitet · P0 rot, P1 gelb, P2 cyan · ! jetzt dringend'],
    ['Seitenleiste', 'auch die Karte unter 90 Spalten · Reiter oben: Alles (alle Blöcke untereinander, › öffnet einen), Jetzt, Ja, Aufgaben, Später, Tabs · Zeile anklicken: ganzer Text und Knöpfe, „mehr …“ für Später, Prio, Team, Kontext · ◂ ▸ blättert · ⟳ neu laden · ✕ schließt'],
    ['Blöcke', 'Wartet auf dich: wartende Tabs, „jetzt“ und „heute“ · Zum Weggeben: braucht nur dein Ja oder darf allein · Deine Aufgaben: P0 bis P2, Bereich davor · Später: Rest, Blockiertes, Ausgeblendetes'],
    ['Markierung', 'farbiges Wort vor der Zeile (z. B. ein Kunde): view.marks im Briefing-Profil, nie im Code'],
    ['alle freigeben', 'unter Zum Weggeben: gibt jeder Freigabe mit Aktion auf einmal dein Ja, nach einer Rückfrage'],
    ['Mach du', 'Eintrag mit Aktion: gilt als Ja, sie läuft beim nächsten Durchlauf des Posteingangs · sonst neuer Tab im Workspace des Bereichs, der es erledigt'],
    ['Tab zuordnen (▾)', 'ein schon laufender Tab im Bereich einer Aufgabe wird ihr zugeordnet, danach steht dort „zum Tab“'],
    ['Berate mich', 'neuer Tab liest den Kontext, berichtet kurz und wartet auf dich'],
    ['Erledigt · Weg', 'Eintrag schließen (nur du konntest es tun) · Eintrag verwerfen'],
    ['zum Tab · weiter · ✉', 'zum Tab springen · „Mach weiter.“ schicken · eigene Nachricht an den Tab · braucht dich (fragt um Erlaubnis): Ja oder Nein direkt beantworten · Ergebnis da: der Tab hat sein Ergebnis in den Posteingang gelegt, zählt nicht mehr als wartend, „Tab schließen“ räumt ihn weg'],
    ['Leitstand', 'nur die Sitzung im Leitstand-Workspace (workplace.control in bridge-config.yaml) fragt die Tabs ab, meldet und sichert; die anderen lesen ihren Stand mit und bleiben still · ist der Tab-Stand alt, steht rot warum'],
    ['▾ (Leiste: Titel)', 'Details, Später/Ausblenden bis Datum, Dringlichkeit, Prio, eigener Workspace, im Chat fragen, Link'],
    ['[ ]', 'markieren; oben erscheint „N markiert: Mach du · Berate mich“'],
    ['+N weitere', 'einen Block aufklappen · „alles“ klappt alle auf'],
    ['Team (▾)', 'mehrere Rollen-Tabs auf einer Aufgabe, nacheinander: Bauen (Umsetzung, Prüfung), TDD, Recherche (Belege, Gegenposition, Zusammenfassung), Antwort (Verlauf, Entwurf), Betrieb (Diagnose, Behebung) · ▶ startet die nächste Rolle, wenn die vorige wartet · Übergabe in team.md'],
    ['Lange · Sicherung', '„lange“: Tab wartet oder läuft seit über einer Stunde, einmal gemeldet · Workspaces und Tabs werden in cmux regelmäßig gesichert (snapshot_minutes, sonst stündlich), nur bei Änderung; „Liste“ zeigt die letzten'],
    ['Kontext (▾)', 'Notiz: selbst ergänzen, landet in STATUS.md oder am Eintrag · Kontext sammeln lassen: ein Tab sucht in Log, Posteingang, Commits, Issues, Mails, Protokollen und notiert die Fakten mit Quelle'],
    ['Kürzel', 'in die Eingabezeile, ohne Claude zu fragen: 3a Mach du · 3b Später · 3c Weg · 3v Berate mich · 3w eigener Workspace · mehrere: 1a 4v'],
    ['Tokens', 'nur „einordnen“, „Plan für heute“, „Feierabend“, „im Chat fragen“, „Nachfassen“ und jeder gestartete Tab · alles andere lokal'],
    ['Einstellungen', 'briefing.claude_code_ui in bridge-config.yaml (Band, Kürzel, Stimme, Ziel beim Starten, wie oft abgefragt wird, Frist für den vollen Lauf, Sprache)'],
  ],
  briefing: 'Briefing',
  bucketTasks: 'Aufgaben',
  bucketResting: 'Ruhend oder blockiert',
  empty: 'nichts',
  blocked: by => `blockiert: ${by}`,
  quietFor: days => `seit ${days} Tagen ruhig`,
  waitingFor: d => `wartet seit ${d}`,
  runningFor: d => `läuft seit ${d}`,

  resDo: 'Mach du',
  resLater: 'Später',
  resDrop: 'Weg',
  resDone: 'Erledigt',
  resStarted: 'gestartet',
  resPartly: 'teilweise gestartet',
  resFailed: 'fehlgeschlagen',
  resHidden: 'ausgeblendet',
  resAsked: 'gefragt',
  noInbox: 'kein Posteingangs-Eintrag',
  nothingToStart: 'nichts zu starten',
  nothingToDo: 'nichts zu tun',
  noTask: 'keine Aufgabe',
  allRolesStarted: 'alle Rollen gestartet',
  waitsForRole: name => `wartet auf ${name}`,
  prevRole: 'die vorige Rolle',

  btnDo: 'Mach du',
  btnAdvise: 'Berate mich',
  btnDrop: 'Weg',
  btnDone: 'Erledigt',
  btnNudge: 'Nachfassen',
  btnAskClaude: 'Claude fragen',
  btnApproved: 'Ja gegeben',
  btnToTab: 'zum Tab',
  btnYes: 'Ja',
  btnNo: 'Nein',
  btnCloseTab: 'Tab schließen',
  btnGoOn: 'weiter',
  btnOpenTab: 'Tab öffnen',
  btnAsk: 'fragen',
  btnOpen: 'öffnen',
  btnTomorrow: 'morgen',
  btnMonday: 'Montag',
  btnWeek: '1 Woche',
  btnUntil: 'bis',
  btnCollect: 'sammeln lassen',
  btnNote: 'notieren',
  btnOwnWs: 'eigener Workspace',
  btnDoOwnWs: 'Mach du im eigenen Workspace',
  btnEachOwnWs: 'je eigener Workspace',
  btnAskChat: 'im Chat fragen',
  btnPickAll: 'alle markieren',
  btnLess: 'weniger',
  btnMore: 'mehr …',
  btnCompact: 'kompakt',
  btnAll: 'alles',
  btnReload: '⟳ neu',
  btnSort: 'einordnen',
  btnPlan: 'Plan für heute',
  emptyHint: 'Nichts wartet auf dich. Was hier steht, legt dein Briefing-Profil fest (workflow/briefings/<id>.yaml); wie du es aufbaust: docs/briefing-dashboard.md',
  approveAll: n => `alle ${n} freigeben`,
  approveAsk: n => `Wirklich alle ${n} freigeben? Jede führt ihre Aktion beim nächsten Durchlauf aus.`,
  approveYes: 'Ja, alle',
  approveNo: 'Abbrechen',
  sourceAsOf: time => `Stand ${time}`,
  planHead: (at, headline) => `Plan für heute aus dem Dashboard (${at}): ${headline}`,
  planAgenda: 'Termine:',
  planRows: 'Offen (Block, Priorität, Markierung):',
  planTabs: 'Agenten-Tabs, die auf mich warten:',
  planTail: 'Mach mir einen Plan für heute: eine Reihenfolge mit Uhrzeiten in den freien Zeiten zwischen den Terminen, ' +
    'was du parallel in Tabs erledigen kannst, was ich selbst tun muss, und was bis morgen warten kann. ' +
    'Kurz, als Tabelle. Nichts ausführen und nichts nach außen ohne mein Ja.',
  btnEvening: 'Feierabend',
  btnSidebar: 'Leiste',
  btnSave: 'jetzt sichern',
  btnList: 'Liste',
  btnClose: 'zu',
  btnShow: 'zeigen',
  btnShowAgain: 'wieder zeigen',
  btnClear: 'leeren',
  btnSend: 'senden',
  btnReopen: 'aufklappen',
  btnDashboard: 'Dashboard',
  btnView: 'ansehen ›',
  tabsClose: 'Tabs zu',
  tabsAll: n => `alle ${n} Tabs`,

  asOf: 'Stand',
  loading: 'lädt …',
  loadingWhat: what => `lädt ${what}`,
  noTracker: '(ohne Tracker)',
  resultFiled: 'Ergebnis da',
  resultFiledLong: 'Ergebnis liegt im Posteingang, der Tab kann zu',
  toTabLabel: 'an den Tab',
  toTabPlaceholder: 'z. B. go on',
  msgPlaceholder: 'Nachricht an den Tab',
  tabInfo: (ws, name, state) => `Tab: ${ws} / ${name}, ${state}`,
  laterPrefix: 'Später: ',
  hidePrefix: 'Ausblenden bis: ',
  datePlaceholder: '14.10.',
  noDate: text => `kein Datum: ${text} (z. B. 14.10. oder 2026-10-14)`,
  urgencyPrefix: 'Dringlichkeit: ',
  prioPrefix: 'Prio: ',
  teamPrefix: 'Team: ',
  teamProgress: (label, started, all) => `Team ${label} ${started}/${all}: `,
  teamStillWorking: name => `${name} arbeitet noch `,
  teamNew: 'neu: ',
  contextPrefix: 'Kontext: ',
  notePlaceholder: 'Notiz: was fehlt, wer, bis wann',
  adoptPrefix: 'Läuft schon? Tab zuordnen: ',
  moreRows: n => `+ ${n} weitere`,
  moreWork: ' (P3, ohne Prio)',
  moreArrow: n => `+ ${n} weitere ›`,
  helpTitle: 'Hilfe',
  skippedSection: 'kommt mit dem vollen Briefing (⟳)',
  unreadable: why => `nicht lesbar: ${why}`,
  startingTab: 'startet …',
  btnRestart: 'Neu starten',
  startPrefix: 'Starten: ',
  inboxOpen: n => `${n} im Posteingang`,
  lineKind: { origin: 'Herkunft: ', next: 'Als Nächstes: ', blocked: 'Blockiert: ', step: 'Schritt: ', log: 'Log: ' },
  taskState: { backlog: 'Backlog', doing: 'in Arbeit', review: 'im Review', done: 'erledigt' },
  whereArea: name => `im Bereich ${name}`,
  alreadyOpen: label => `${label} läuft schon, zum Tab gewechselt`,
  startingAlready: title => `${title} startet schon`,
  nothingHere: 'nichts hier',
  waitCount: n => `● ${n} warten`,
  longCount: n => `(${n} lange)`,
  workingCount: n => `● ${n} arbeiten`,
  tabsWaiting: n => `● ${n} Tabs warten`,
  counts: (now, give, work, later) => `${now} jetzt · ${give} weggeben · ${work} Aufgaben · ${later} später`,
  inboxRule: 'Posteingang',
  backup: 'Sicherung',
  backupAt: time => `zuletzt ${time}`,
  backupEvery: min => (min === 60 ? 'stündlich' : min > 0 ? `alle ${min} Min.` : 'nur von Hand'),
  picked: n => `${n} markiert`,
  hiddenUntil: date => `bis ${date}`,
  hiddenCount: n => ` · ${n} ausgeblendet`,
  agenda: 'Termine: ',
  alarmUnder: (n, title) => `✗ ${n} Befunde unter ${title}`,
  restoreHint: 'Wiederherstellen: im Chat „stell die cmux-Workspaces aus der Sicherung wieder her“ (cmux-Skill, erst Probelauf)',
  olderCard: when => `Briefing von ${when}, das aktuelle steht weiter unten`,
  earlier: 'früher',
  closedCard: n => `Briefing zugeklappt · ${n} Tabs warten`,
  bandShort: n => `● ${n} warten`,
  bandLong: n => `Briefing: ${n} Tabs warten`,
  bandLongCount: n => ` · ${n} lange`,
  bandCountsShort: (now, give) => ` · ${now} jetzt · ${give} Ja `,
  bandCountsLong: (now, give) => ` · ${now} jetzt · ${give} zum Weggeben `,

  alreadyLoading: 'lädt schon, danach noch einmal ganz',
  loadTasks: 'Aufgaben',
  loadQuick: guess => `Posteingang und Aufgaben${guess}`,
  loadRest: guess => `alles, mit Trackern und Prüfungen${guess}`,
  seconds: n => ` (~${n} s)`,
  loadFailed: err => `Briefing laden fehlgeschlagen: ${err}`,
  viewUnreadable: err => `Briefing nicht lesbar: ${err}`,
  statusFailed: 'Tab-Abfrage gescheitert',
  tabsStale: (time, why) => `Tab-Stand seit ${time} nicht aktuell: ${why}`,
  tabToast: (name, state) => `Tab „${name}“ ${state}`,
  voiceWaiting: name => `${name} wartet auf dich`,
  saved: 'Workspaces gesichert (nur wenn sich etwas geändert hat)',
  saveFailed: err => `Sicherung ging nicht: ${err}`,
  listUnreadable: err => `nicht lesbar: ${err}`,
  approveFailed: err => `Mach du ging nicht: ${err}`,
  approvedNote: 'Ja gegeben, es läuft beim nächsten Durchlauf',
  approvedPending: title => `läuft beim nächsten Durchlauf: ${title}`,
  laterFailed: err => `Später fehlgeschlagen: ${err}`,
  laterBack: until => `Später, zurück am ${until}`,
  hiddenNote: (until, title) => `ausgeblendet bis ${until}: ${title}`,
  urgencySet: (word, title) => `Dringlichkeit ${word}: ${title}`,
  urgencyFailed: err => `Dringlichkeit ging nicht: ${err}`,
  prioFailed: err => `Priorität ging nicht: ${err}`,
  dropFailed: err => `Weg fehlgeschlagen: ${err}`,
  dropped: 'Verworfen',
  dropInboxNote: 'im Briefing-Dashboard verworfen',
  doneFailed: err => `Erledigt fehlgeschlagen: ${err}`,
  doneInboxNote: 'im Briefing-Dashboard als erledigt markiert',
  launchTeam: role => `Team, Rolle ${role}`,
  launchContext: 'Kontext sammeln',
  launchStart: (word, n, where) => `${word}: starte ${n} Tab(s) ${where} …`,
  ownWs: 'eigener Workspace',
  partlyStarted: n => `${n} gestartet, Rest fehlgeschlagen`,
  startFailed: 'Start fehlgeschlagen',
  adopted: (tab, title) => `Tab „${tab}“ gehört jetzt zu ${title}`,
  adoptFailed: err => `Zuordnen ging nicht: ${err}`,
  noteOnly: 'Notiz geht nur an Aufgaben und Posteingangs-Einträge',
  noteAdded: (title, line) => `Notiz an ${title}: ${line}`,
  noteFailed: err => `Notiz ging nicht: ${err}`,
  jumpFailed: err => `Hinspringen ging nicht: ${err}`,
  notAsking: name => `${name} fragt nicht mehr, nichts gedrückt`,
  keyFailed: err => `Taste ging nicht: ${err}`,
  saidYes: 'Ja gesendet',
  saidNo: 'Nein gesendet',
  tabClosed: name => `Tab „${name}“ geschlossen`,
  closeFailed: err => `Schließen ging nicht: ${err}`,
  sentTo: (name, text) => `an ${name}: ${text}`,
  sendFailed: err => `Senden fehlgeschlagen: ${err}`,
  goOnMessage: 'Mach weiter.',

  askAbout: (title, where) => `Briefing-Punkt: ${title}${where ? ` (${where})` : ''}. Schau es dir an und schlag den nächsten Schritt vor. Nichts nach außen ohne mein Ja.`,
  askInfo: (section, title, extra) => `${section}: ${title}${extra ? ` (${extra})` : ''}. Schau es dir an und schlag den nächsten Schritt vor. Nichts nach außen ohne mein Ja.`,
  followUp: (title, why) => `Entwirf eine kurze Nachfass-Nachricht für: ${title}${why ? ` (${why})` : ''}. Nur als Entwurf, nichts senden.`,
  overviewHead: (at, headline) => `Mein Briefing-Stand aus dem Dashboard (${at}): ${headline}`,
  overviewTail: 'Ordne kurz ein: was zuerst, was kann weg, was gebe ich an einen Tab ab. Keine Aktion ohne mein Ja.',
  evening: 'Feierabend-Ritual: Lies den heutigen Tagesblock in work/log.md ganz und python3 scripts/inbox.py list. ' +
    'Zeig mir kurz: was heute erledigt ist, was verschoben ist, was offen bleibt, und schlag vor, was morgen ' +
    'zuerst kommt. Dann schreib eine Logzeile mit gemessener Uhrzeit. Nichts nach außen.',
  eveningTabs: 'Offene Agenten-Tabs, sag zu jedem: abschließen, morgen weiter, oder was ihm fehlt:',
  eveningSince: d => ` seit ${d}`,
  eveningLast: last => ` (zuletzt: ${last})`,

  cmdDesc: 'Briefing als Dashboard: wer wartet, was gebe ich weg, woran arbeite ich; per Klick Tabs starten',
  cmdOffDesc: 'Briefing-Band für diese Sitzung ausblenden (Dashboard bleibt über /briefing-ui)',
  cmdDisabled: 'briefing-ui ist aus: briefing.claude_code_ui.enabled in bridge-config.yaml auf true setzen.',
  readFailed: err => `bridge-config.yaml ließ sich nicht lesen: ${err}`,
  cmdOutput: id => `Briefing-Dashboard (briefing-ui ${id}). Ohne den Mod steht hier nur dieser Satz.`,
  bandOff: 'Briefing-Band ausgeblendet. /briefing-ui öffnet das Dashboard weiterhin.',
  morning: 'Guten Morgen. /briefing-ui zeigt, wer wartet und was du weggeben kannst.',
  scMissing: n => `${n}: gibt es nicht`,
  scHasTab: (n, title) => `${n} (${title}) hat schon einen Tab, dorthin gewechselt`,
  scApproved: 'Ja ist schon gegeben',
  scWaiting: 'wartet auf jemand anderen, Nachfassen über die Karte',
  scOnlyYou: 'nur du, v für Berate mich',
  scResult: said => `Briefing ohne Claude: ${said}`,
}

const en: Strings = {
  state: { 'needs-you': 'needs you', waiting: 'waiting', working: 'working', shell: 'terminal' },
  urgency: { now: 'now', today: 'today', later: 'later' },
  section: { now: 'Waiting for you', give: 'To hand off', work: 'Your tasks', later: 'Later' },
  where: { area: 'in its area', tab: 'as a tab here', workspace: 'in its own workspace', auto: 'where it fits' },
  shortLabel: { advise: 'Advise', nudge: 'Follow up', ask: 'Ask' },
  side: { all: 'All', now: 'Now', give: 'Yes', work: 'Tasks', later: 'Later', tabs: 'Tabs' },
  help: [
    ['Tabs on top', 'Briefing: what waits and what you hand off · beside it the tabs of your briefing profile (view.pages in workflow/briefings/<id>.yaml, else by kind: Status, Dates, Trackers, Today, More) · number: what counts, ✗ red findings, ✓ all green · no tokens; GitHub and the health checks arrive with the full run (⟳, on open when the last is older than full_minutes) · "as of 08:46": how old cached rows are, ⟳ asks fresh'],
    ['Tested', 'only with Claude Code and cmux; other agents and terminals come later'],
    ['Header', '⟳ reload · all: open every section · Sort it: Claude prioritises (tokens) · Plan my day: Claude fits the order into your free slots (tokens) · End of day · Sidebar: open the sidebar · ? help · ✕ collapse the card, "Expand" brings it back'],
    ['Colours', '● red needs you, yellow waits, green works · P0 red, P1 yellow, P2 cyan · ! urgent now'],
    ['Sidebar', 'also the card below 90 columns · tabs at the top: All (every section stacked, › opens one), Now, Yes, Tasks, Later, Tabs · click a line: full text and buttons, "more …" for later, priority, team, context · ◂ ▸ pages · ⟳ reload · ✕ closes'],
    ['Sections', 'Waiting for you: tabs that wait, "now" and "today" · To hand off: needs only your yes, or may run alone · Your tasks: P0 to P2, area in front · Later: the rest, blocked, hidden'],
    ['Mark', 'coloured word in front of a row (a customer, say): view.marks in the briefing profile, never in code'],
    ['approve all', 'under To hand off: gives every approval with an action your yes at once, after one question'],
    ['Do it', 'an item with an action counts as your yes, it runs on the next inbox pass · otherwise a new tab in the area workspace does it'],
    ['Assign tab (▾)', 'a tab already running in the task\'s area is linked to it, then "Go to tab" shows'],
    ['Advise me', 'a new tab reads the context, reports briefly, then waits for you'],
    ['Done · Drop', 'close an item only you could do · discard the item'],
    ['Go to tab · go on · ✉', 'jump to the tab · send "Keep going." · your own message to the tab · needs you (asks for permission): answer Yes or No right here · Result filed: the tab put its result in the inbox, no longer counts as waiting, "Close tab" closes it'],
    ['Control session', 'only the session in the control workspace (workplace.control in bridge-config.yaml) polls the tabs, notifies and saves the layout; the others read its state and stay quiet · a stale tab state says why in red'],
    ['▾ (sidebar: title)', 'details, later or hide until a date, urgency, priority, own workspace, ask in chat, link'],
    ['[ ]', 'select; "N selected: Do it · Advise me" appears at the top'],
    ['+N more', 'open one section · "all" opens every section'],
    ['Team (▾)', 'several role tabs on one task, one after the other: Build (implement, review), TDD, Research (evidence, counter, summary), Reply (context, draft), Ops (diagnose, fix) · ▶ starts the next role once the previous one waits · handoff in team.md'],
    ['Long · Backup', '"long": a tab has waited or run for over an hour, reported once · inside cmux, workspaces and tabs are saved regularly (snapshot_minutes, hourly by default), only on change; "List" shows the latest'],
    ['Context (▾)', 'Note: add it yourself, it goes into STATUS.md or onto the item · let it collect: a tab searches log, inbox, commits, issues, mails, minutes and notes the facts with sources'],
    ['Shortcuts', 'type them into the prompt, no Claude turn: 3a do it · 3b later · 3c drop · 3v advise me · 3w own workspace · several: 1a 4v'],
    ['Tokens', 'only "Sort it", "Plan my day", "End of day", "ask in chat", "Follow up" and every launched tab · everything else is local'],
    ['Settings', 'briefing.claude_code_ui in bridge-config.yaml (band, shortcuts, voice, launch target, how often to poll, how old the full run may be, language)'],
  ],
  briefing: 'Briefing',
  bucketTasks: 'Tasks',
  bucketResting: 'Resting or blocked',
  empty: 'nothing',
  blocked: by => `blocked: ${by}`,
  quietFor: days => `quiet for ${days} days`,
  waitingFor: d => `waiting for ${d}`,
  runningFor: d => `running for ${d}`,

  resDo: 'Do it',
  resLater: 'Later',
  resDrop: 'Dropped',
  resDone: 'Done',
  resStarted: 'started',
  resPartly: 'partly started',
  resFailed: 'failed',
  resHidden: 'hidden',
  resAsked: 'asked',
  noInbox: 'not an inbox item',
  nothingToStart: 'nothing to start',
  nothingToDo: 'nothing to do',
  noTask: 'not a task',
  allRolesStarted: 'all roles started',
  waitsForRole: name => `waiting for ${name}`,
  prevRole: 'the previous role',

  btnDo: 'Do it',
  btnAdvise: 'Advise me',
  btnDrop: 'Drop',
  btnDone: 'Done',
  btnNudge: 'Follow up',
  btnAskClaude: 'Ask Claude',
  btnApproved: 'Yes given',
  btnToTab: 'Go to tab',
  btnYes: 'Yes',
  btnNo: 'No',
  btnCloseTab: 'Close tab',
  btnGoOn: 'go on',
  btnOpenTab: 'Open tab',
  btnAsk: 'ask',
  btnOpen: 'open',
  btnTomorrow: 'tomorrow',
  btnMonday: 'Monday',
  btnWeek: '1 week',
  btnUntil: 'until',
  btnCollect: 'let it collect',
  btnNote: 'add note',
  btnOwnWs: 'own workspace',
  btnDoOwnWs: 'Do it in its own workspace',
  btnEachOwnWs: 'each in its own workspace',
  btnAskChat: 'ask in chat',
  btnPickAll: 'select all',
  btnLess: 'less',
  btnMore: 'more …',
  btnCompact: 'compact',
  btnAll: 'all',
  btnReload: '⟳ reload',
  btnSort: 'Sort it',
  btnPlan: 'Plan my day',
  emptyHint: 'Nothing waits for you. What shows here is up to your briefing profile (workflow/briefings/<id>.yaml); how to build it: docs/briefing-dashboard.md',
  approveAll: n => `approve all ${n}`,
  approveAsk: n => `Approve all ${n}? Each runs its action on the next pass.`,
  approveYes: 'Yes, all',
  approveNo: 'Cancel',
  sourceAsOf: time => `as of ${time}`,
  planHead: (at, headline) => `Plan for today from the dashboard (${at}): ${headline}`,
  planAgenda: 'Appointments:',
  planRows: 'Open (block, priority, mark):',
  planTabs: 'Agent tabs waiting for me:',
  planTail: 'Make me a plan for today: an order with times in the free slots between appointments, ' +
    'what you can do in parallel in tabs, what I have to do myself, and what can wait until tomorrow. ' +
    'Short, as a table. Run nothing and send nothing out without my yes.',
  btnEvening: 'End of day',
  btnSidebar: 'Sidebar',
  btnSave: 'save now',
  btnList: 'List',
  btnClose: 'close',
  btnShow: 'show',
  btnShowAgain: 'show again',
  btnClear: 'clear',
  btnSend: 'send',
  btnReopen: 'Expand',
  btnDashboard: 'Dashboard',
  btnView: 'view ›',
  tabsClose: 'hide tabs',
  tabsAll: n => `all ${n} tabs`,

  asOf: 'As of',
  loading: 'loading …',
  loadingWhat: what => `loading ${what}`,
  noTracker: '(without trackers)',
  resultFiled: 'Result filed',
  resultFiledLong: 'The result is in the inbox, the tab can be closed',
  toTabLabel: 'to the tab',
  toTabPlaceholder: 'e.g. go on',
  msgPlaceholder: 'Message to the tab',
  tabInfo: (ws, name, state) => `Tab: ${ws} / ${name}, ${state}`,
  laterPrefix: 'Later: ',
  hidePrefix: 'Hide until: ',
  datePlaceholder: '2026-10-14',
  noDate: text => `not a date: ${text} (e.g. 2026-10-14 or 14.10.)`,
  urgencyPrefix: 'Urgency: ',
  prioPrefix: 'Priority: ',
  teamPrefix: 'Team: ',
  teamProgress: (label, started, all) => `Team ${label} ${started}/${all}: `,
  teamStillWorking: name => `${name} is still working `,
  teamNew: 'new: ',
  contextPrefix: 'Context: ',
  notePlaceholder: 'Note: what is missing, who, by when',
  adoptPrefix: 'Already running? Assign tab: ',
  moreRows: n => `+ ${n} more`,
  moreWork: ' (P3, no priority)',
  moreArrow: n => `+ ${n} more ›`,
  helpTitle: 'Help',
  skippedSection: 'arrives with the full briefing (⟳)',
  unreadable: why => `could not read: ${why}`,
  startingTab: 'starting …',
  btnRestart: 'Restart',
  startPrefix: 'Start: ',
  inboxOpen: n => `${n} in the inbox`,
  lineKind: { origin: 'Origin: ', next: 'Next: ', blocked: 'Blocked: ', step: 'Step: ', log: 'Log: ' },
  taskState: { backlog: 'backlog', doing: 'doing', review: 'in review', done: 'done' },
  whereArea: name => `in area ${name}`,
  alreadyOpen: label => `${label} is already running, switched to its tab`,
  startingAlready: title => `${title} is already starting`,
  nothingHere: 'nothing here',
  waitCount: n => `● ${n} waiting`,
  longCount: n => `(${n} long)`,
  workingCount: n => `● ${n} working`,
  tabsWaiting: n => `● ${n} tabs waiting`,
  counts: (now, give, work, later) => `${now} now · ${give} to hand off · ${work} tasks · ${later} later`,
  inboxRule: 'Inbox',
  backup: 'Backup',
  backupAt: time => `last at ${time}`,
  backupEvery: min => (min === 60 ? 'hourly' : min > 0 ? `every ${min} min` : 'only by hand'),
  picked: n => `${n} selected`,
  hiddenUntil: date => `until ${date}`,
  hiddenCount: n => ` · ${n} hidden`,
  agenda: 'Dates: ',
  alarmUnder: (n, title) => `✗ ${n} findings under ${title}`,
  restoreHint: 'To restore, ask in chat "restore the cmux workspaces from the backup" (cmux skill, dry run first)',
  olderCard: when => `Briefing from ${when}, the current one is further down`,
  earlier: 'earlier',
  closedCard: n => `Briefing collapsed · ${n} tabs waiting`,
  bandShort: n => `● ${n} waiting`,
  bandLong: n => `Briefing: ${n} tabs waiting`,
  bandLongCount: n => ` · ${n} long`,
  bandCountsShort: (now, give) => ` · ${now} now · ${give} yes `,
  bandCountsLong: (now, give) => ` · ${now} now · ${give} to hand off `,

  alreadyLoading: 'already loading, a full reload follows',
  loadTasks: 'tasks',
  loadQuick: guess => `inbox and tasks${guess}`,
  loadRest: guess => `everything, with trackers and checks${guess}`,
  seconds: n => ` (~${n} s)`,
  loadFailed: err => `Could not load the briefing: ${err}`,
  viewUnreadable: err => `Could not read the briefing: ${err}`,
  statusFailed: 'tab check failed',
  tabsStale: (time, why) => `Tab state not current since ${time}: ${why}`,
  tabToast: (name, state) => `Tab "${name}" ${state}`,
  voiceWaiting: name => `${name} is waiting for you`,
  saved: 'Workspaces saved (only if something changed)',
  saveFailed: err => `Backup failed: ${err}`,
  listUnreadable: err => `could not read: ${err}`,
  approveFailed: err => `Do it failed: ${err}`,
  approvedNote: 'Yes given, it runs on the next pass',
  approvedPending: title => `runs on the next pass: ${title}`,
  laterFailed: err => `Later failed: ${err}`,
  laterBack: until => `Later, back on ${until}`,
  hiddenNote: (until, title) => `hidden until ${until}: ${title}`,
  urgencySet: (word, title) => `Urgency ${word}: ${title}`,
  urgencyFailed: err => `Urgency failed: ${err}`,
  prioFailed: err => `Priority failed: ${err}`,
  dropFailed: err => `Drop failed: ${err}`,
  dropped: 'Dropped',
  dropInboxNote: 'dropped in the briefing dashboard',
  doneFailed: err => `Done failed: ${err}`,
  doneInboxNote: 'marked done in the briefing dashboard',
  launchTeam: role => `Team, role ${role}`,
  launchContext: 'Collect context',
  launchStart: (word, n, where) => `${word}: starting ${n} tab(s) ${where} …`,
  ownWs: 'own workspace',
  partlyStarted: n => `${n} started, the rest failed`,
  startFailed: 'Start failed',
  adopted: (tab, title) => `Tab "${tab}" now belongs to ${title}`,
  adoptFailed: err => `Assigning failed: ${err}`,
  noteOnly: 'Notes only go to tasks and inbox items',
  noteAdded: (title, line) => `Note on ${title}: ${line}`,
  noteFailed: err => `Note failed: ${err}`,
  jumpFailed: err => `Could not switch to the tab: ${err}`,
  notAsking: name => `${name} is no longer asking, nothing pressed`,
  keyFailed: err => `Key press failed: ${err}`,
  saidYes: 'Yes sent',
  saidNo: 'No sent',
  tabClosed: name => `Tab "${name}" closed`,
  closeFailed: err => `Closing failed: ${err}`,
  sentTo: (name, text) => `to ${name}: ${text}`,
  sendFailed: err => `Sending failed: ${err}`,
  goOnMessage: 'Keep going.',

  askAbout: (title, where) => `Briefing item: ${title}${where ? ` (${where})` : ''}. Take a look and suggest the next step. Nothing goes out without my yes.`,
  askInfo: (section, title, extra) => `${section}: ${title}${extra ? ` (${extra})` : ''}. Take a look and suggest the next step. Nothing goes out without my yes.`,
  followUp: (title, why) => `Draft a short follow-up message for: ${title}${why ? ` (${why})` : ''}. Draft only, do not send anything.`,
  overviewHead: (at, headline) => `My briefing state from the dashboard (${at}): ${headline}`,
  overviewTail: 'Sort it briefly: what comes first, what can go, what do I hand to a tab. No action without my yes.',
  evening: 'End of day: read today\'s day block in work/log.md in full and run python3 scripts/inbox.py list. ' +
    'Show me briefly what got done today, what was postponed and what stays open, and suggest what comes ' +
    'first tomorrow. Then write a log row with the measured time. Nothing goes out.',
  eveningTabs: 'Open agent tabs, say for each: wrap up, continue tomorrow, or what it is missing:',
  eveningSince: d => ` for ${d}`,
  eveningLast: last => ` (last: ${last})`,

  cmdDesc: 'Briefing as a dashboard: who waits, what I hand off, what I work on; start tabs with a click',
  cmdOffDesc: 'Hide the briefing band for this session (the dashboard stays available via /briefing-ui)',
  cmdDisabled: 'briefing-ui is off: set briefing.claude_code_ui.enabled to true in bridge-config.yaml.',
  readFailed: err => `Could not read bridge-config.yaml: ${err}`,
  cmdOutput: id => `Briefing dashboard (briefing-ui ${id}). Without the mod, this sentence is all you see here.`,
  bandOff: 'Briefing band hidden. /briefing-ui still opens the dashboard.',
  morning: 'Good morning. /briefing-ui shows who is waiting and what you can hand off.',
  scMissing: n => `${n}: does not exist`,
  scHasTab: (n, title) => `${n} (${title}) already has a tab, switched there`,
  scApproved: 'yes already given',
  scWaiting: 'waiting for someone else, follow up from the card',
  scOnlyYou: 'only you can do this, v for Advise me',
  scResult: said => `Briefing without Claude: ${said}`,
}

/** Both tables, for the help (own switcher) and the tests */
export const TABLES: Record<'de' | 'en', Strings> = { de, en }

let current: Strings = en

/** de... means German, everything else English */
export function setLanguage(lang: string): void {
  current = lang.toLowerCase().startsWith('de') ? de : en
}

export function T(): Strings {
  return current
}
