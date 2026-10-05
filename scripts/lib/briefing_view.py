# SPDX-License-Identifier: MIT
"""How a briefing is shown: the `view:` block of a briefing profile.

A profile's sections say where the data comes from; this module decides what the
reader sees. Four styles, chosen per profile (`view.style`) or once on the command
line (`briefing.py render --style <style>`):

  sources  one block per section, in profile order: the briefing as it always was
  triage   every row sorted by what to DO with it: do, plan, delegate, waiting,
           drop; a thing two sources carry is shown once; housekeeping goes last
  brevity  the bottom line, then the top three with why each matters
  plan     the day: your rows laid into the free gaps of today's calendar, what
           the Bridge does meanwhile, and when the day ends

Which bucket a row lands in follows fixed rules (docs/briefings.md § Views), so the
shape never depends on which agent renders it. A section can force its bucket
(`bucket:`), `mutes:` hide rows a person said they never want again, and every word
the reader sees can be relabelled (`view.labels`, bucket titles). Contract:
scripts/tests/test_briefing_view.py.
"""
from __future__ import annotations

import datetime as dt
import re
import string
import textwrap

STYLES = ("sources", "triage", "brevity", "plan")
BUCKETS = ("do", "plan", "delegate", "waiting", "drop")
VIEW_KEYS = {"style", "headline", "since_last", "lookahead_days", "max_items", "answer_keys", "hygiene", "color",
             "width", "labels", "buckets", "plan"}
BUCKET_KEYS = {"id", "title", "options", "nudge_after_days"}
DEFAULT_BUCKETS = {
    "do": {"title": "Do (you, today)", "options": ["yes", "later", "drop"]},
    "plan": {"title": "Plan", "options": ["schedule", "later"]},
    "delegate": {"title": "I'll do", "options": ["go", "not now"]},
    "waiting": {"title": "Waiting on others", "options": ["nudge", "wait"], "nudge_after_days": 7},
    "drop": {"title": "Park or drop", "options": ["park", "keep"]},
}
LABELS = {
    "yours_today": "{n} for you today",
    "free_until": "free until {time}",
    "free_rest": "free for the rest of the day",
    "busy_until": "in {title} until {time}",
    "next_date": "next: {when} {title}",
    "since": "since {time}: {new} new, {changed} changed",
    "today": "today",
    "tomorrow": "tomorrow",
    "due": "due {when}",
    "back_on": "back on {date}",
    "only_you": "only you",
    "collides": "collides with the calendar",
    "waiting_days": "waiting {n} days",
    "with": "with {who}",
    "task": "task {slug}",
    "nudge": "nudge?",
    "new": "new",
    "housekeeping": "Housekeeping",
    "no_next": "{n} task(s) without a next step: {slugs}",
    "muted": "{n} muted",
    "hidden": "{n} hidden (bucket not shown: {ids})",
    "error": "{title} failed: {reason}",
    "workplace": "Tabs: {n} proposed ({new} new, {resume} to resume). Open them?",
    "more": "+{n} more",
    "end": "That's all for today.",
    "why": "why",
    "meanwhile": "Meanwhile I do",
    "later": "Later",
    "shutdown": "Day ends {time}",
}
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
# An id that names its repository is the same thing wherever it comes from; any
# other id (a command's "1", an ADO "1234") is only unique inside its section.
GLOBAL_ID = re.compile(r"^[\w.-]+/[\w.-]+#\d+$")
WHO_BRIDGE = ("bridge", "agent", "ai")
WHO_YOU = ("me", "you", "self")
URGENCY = {b: n for n, b in enumerate(BUCKETS)}


# ---------------------------------------------------------------- choice and validation

def _cfg(profile: dict) -> dict:
    view = profile.get("view")
    return view if isinstance(view, dict) else {}


def style_of(profile: dict, override: str | None = None) -> str:
    if override:
        return override
    style = _cfg(profile).get("style", "sources")
    return style if style in STYLES else "sources"


def _pos_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _int(value, default: int, minimum: int = 0) -> int:
    """A number from a profile that may not have been validated: bad values fall back."""
    if isinstance(value, bool):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number >= minimum else default


def _fields(text: str) -> set:
    """Placeholder names in a label; raises ValueError on a broken brace."""
    return {name for _, name, _, _ in string.Formatter().parse(text) if name is not None}


def problems(view, mutes) -> list:
    """What is wrong with a profile's `view:` block and `mutes:` list (None = not given)."""
    out = []
    if view is not None:
        if not isinstance(view, dict):
            return ["view must be a mapping"]
        for key in sorted(set(view) - VIEW_KEYS):
            out.append(f"unknown view key {key}")
        if view.get("style", "sources") not in STYLES:
            out.append(f"view.style must be one of {', '.join(STYLES)}")
        for key in ("headline", "since_last", "answer_keys"):
            if key in view and not isinstance(view[key], bool):
                out.append(f"view.{key} must be true or false")
        if "max_items" in view and not _pos_int(view["max_items"]):
            out.append("view.max_items must be a positive integer")
        if "width" in view and not (_pos_int(view["width"]) and view["width"] >= 40):
            out.append("view.width must be a whole number of 40 or more")
        if "lookahead_days" in view and _int(view["lookahead_days"], -1) < 0 or \
                isinstance(view.get("lookahead_days"), (str, bool, float)):
            out.append("view.lookahead_days must be a whole number of days, 0 or more")
        if view.get("hygiene", "bottom") not in ("bottom", "hide"):
            out.append("view.hygiene must be bottom or hide")
        if view.get("color", "auto") not in ("auto", "meaning", "none"):
            out.append("view.color must be auto, meaning or none")
        labels = view.get("labels", {})
        if not isinstance(labels, dict) or not all(isinstance(v, str) for v in labels.values()):
            out.append("view.labels must map label names to text")
        else:
            for key, text in sorted(labels.items()):
                if key not in LABELS:
                    out.append(f"view.labels: unknown label {key} (known: {', '.join(sorted(LABELS))})")
                    continue
                try:
                    extra = _fields(text) - _fields(LABELS[key])
                except ValueError:
                    out.append(f"view.labels.{key}: a brace that is not a placeholder (write {{{{ or }}}})")
                    continue
                if extra:
                    allowed = ", ".join(f"{{{f}}}" for f in sorted(_fields(LABELS[key]))) or "none"
                    out.append(f"view.labels.{key}: unknown placeholder {', '.join(sorted(extra))} "
                               f"(allowed: {allowed})")
        buckets = view.get("buckets", [])
        if not isinstance(buckets, list):
            out.append("view.buckets must be a list")
            buckets = []
        seen = set()
        for n, b in enumerate(buckets, 1):
            if not isinstance(b, dict) or b.get("id") not in BUCKETS:
                bid = b.get("id") if isinstance(b, dict) else b
                out.append(f"view.buckets {n}: bucket id {bid!r} is not one of {', '.join(BUCKETS)}")
                continue
            if b["id"] in seen:
                out.append(f"view.buckets {n}: bucket {b['id']} listed twice")
            seen.add(b["id"])
            for key in sorted(set(b) - BUCKET_KEYS):
                out.append(f"view.buckets {n}: unknown key {key}")
            if "title" in b and not isinstance(b["title"], str):
                out.append(f"view.buckets {n}: title must be text")
            if "options" in b and not (isinstance(b["options"], list) and all(isinstance(o, str) for o in b["options"])):
                out.append(f"view.buckets {n}: options must be a list of text")
            if "nudge_after_days" in b and not _pos_int(b["nudge_after_days"]):
                out.append(f"view.buckets {n}: nudge_after_days must be a positive integer")
        plan = view.get("plan", {})
        if not isinstance(plan, dict):
            out.append("view.plan must be a mapping")
        else:
            for key in sorted(set(plan) - {"workday", "default_minutes"}):
                out.append(f"view.plan: unknown key {key}")
            workday = plan.get("workday", {})
            if not isinstance(workday, dict):
                out.append("view.plan.workday must be a mapping with start and end")
            else:
                good = True
                for key in ("start", "end"):
                    if key in workday and not (isinstance(workday[key], str) and HHMM.match(workday[key])):
                        out.append(f"view.plan.workday {key} must be HH:MM")
                        good = False
                if good and _hm(workday.get("start", "08:00")) >= _hm(workday.get("end", "18:00")):
                    out.append("view.plan.workday start must be before its end")
            if "default_minutes" in plan and not _pos_int(plan["default_minutes"]):
                out.append("view.plan.default_minutes must be a positive integer")
    if mutes is not None:
        if not isinstance(mutes, list):
            out.append("mutes must be a list")
        else:
            for n, m in enumerate(mutes, 1):
                if not isinstance(m, dict) or not isinstance(m.get("section"), str):
                    out.append(f"mutes rule {n} needs a `section:` (a section id)")
                elif not isinstance(m.get("when"), dict) or not m["when"]:
                    out.append(f"mutes rule {n} needs a non-empty `when:` mapping")
                elif set(m) - {"section", "when", "note"}:
                    out.append(f"mutes rule {n}: unknown key {sorted(set(m) - {'section', 'when', 'note'})[0]}")
                elif "note" in m and not isinstance(m["note"], str):
                    out.append(f"mutes rule {n}: note must be text")
    return out


def _labels(view: dict) -> dict:
    """The profile's words over the defaults; a label that would not format keeps the default."""
    out = dict(LABELS)
    given = view.get("labels") if isinstance(view.get("labels"), dict) else {}
    for key, text in given.items():
        if key not in LABELS or not isinstance(text, str):
            continue
        try:
            if _fields(text) <= _fields(LABELS[key]):
                out[key] = text
        except ValueError:
            pass
    return out


# ---------------------------------------------------------------- time

def _when(value):
    """ISO date or datetime as a naive local datetime; a bare date is midnight."""
    if not value:
        return None
    text = str(value).strip()
    try:
        when = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            when = dt.datetime.combine(dt.date.fromisoformat(text[:10]), dt.time())
        except ValueError:
            return None
    if when.tzinfo is not None:
        when = when.astimezone().replace(tzinfo=None)
    return when


def _has_time(value) -> bool:
    return bool(value) and len(str(value)) > 10


def _fmt_when(value, now: dt.datetime, labels: dict) -> str:
    when = _when(value)
    if when is None:
        return str(value)
    day = (labels["today"] if when.date() == now.date() else
           labels["tomorrow"] if when.date() == now.date() + dt.timedelta(days=1) else f"{when:%d.%m}")
    return f"{day} {when:%H:%M}" if _has_time(value) else day


def _hm(value: str) -> int:
    h, m = value.split(":")
    return int(h) * 60 + int(m)


def _clock(minutes: int) -> str:
    minutes = max(0, min(minutes, 24 * 60 - 1))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _events(raw: list, now: dt.datetime) -> list:
    """Timed events as (start, end, title), sorted by time; no end = 30 minutes."""
    out = []
    for e in raw:
        start = _when(e.get("start"))
        if start is None or not _has_time(e.get("start")):
            continue
        end = _when(e.get("end")) if _has_time(e.get("end")) else None
        if end is None or end <= start:
            end = start + dt.timedelta(minutes=30)
        out.append((start, end, str(e.get("title") or "")))
    return sorted(out, key=lambda e: e[0])


def _today(events: list, now: dt.datetime) -> list:
    """Events overlapping today, as minute ranges clipped to today."""
    day0 = dt.datetime.combine(now.date(), dt.time())
    day1 = day0 + dt.timedelta(days=1)
    out = []
    for start, end, title in events:
        if start < day1 and end > day0:
            s = max(start, day0)
            e = min(end, day1)
            out.append((int((s - day0).total_seconds() // 60), int((e - day0).total_seconds() // 60), title))
    return out


# ---------------------------------------------------------------- build

def _matches(when: dict, item: dict) -> bool:
    for field, want in when.items():
        have = item.get(field)
        wants = want if isinstance(want, list) else [want]
        if isinstance(have, list):
            if not any(w in have for w in wants):
                return False
        elif have not in wants:
            return False
    return True


def _bucket_cfg(view: dict) -> tuple:
    """(shown bucket configs in order, ids hidden). No list = all five in the default order."""
    listed = view.get("buckets")
    if not isinstance(listed, list) or not listed:
        listed = [{"id": b} for b in BUCKETS]
    shown = []
    for b in listed:
        if isinstance(b, dict) and b.get("id") in BUCKETS:
            shown.append({"id": b["id"], **DEFAULT_BUCKETS[b["id"]], **{k: v for k, v in b.items() if k != "id"}})
    ids = [b["id"] for b in shown]
    return shown, [b for b in BUCKETS if b not in ids]


def _short(text, limit: int) -> str:
    """At most `limit` characters, marked with an ellipsis; cut at a word when the text has one."""
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if " " in cut and not text[limit - 1].isspace():
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,.;:") + "…"


def _days_since(value, now: dt.datetime):
    when = _when(value)
    return (now.date() - when.date()).days if when else None


def _item_key(sid, iid) -> str:
    iid = str(iid)
    return f"item:{iid}" if GLOBAL_ID.match(iid) else f"item:{sid}:{iid}"


def _rows(result: dict, profile: dict, view: dict, labels: dict, now: dt.datetime) -> dict:
    sections_cfg = {}
    for s in profile.get("sections") or []:
        if isinstance(s, dict):
            sections_cfg[str(s.get("id") or s.get("kind"))] = s
    mutes = [m for m in (profile.get("mutes") or []) if isinstance(m, dict) and isinstance(m.get("when"), dict)]
    you = set(WHO_YOU) | ({str(profile["for"]).lower()} if profile.get("for") else set())
    horizon = now.date() + dt.timedelta(days=_int(view.get("lookahead_days"), 1))
    nudge_days = DEFAULT_BUCKETS["waiting"]["nudge_after_days"]
    for b in view.get("buckets") or []:
        if isinstance(b, dict) and b.get("id") == "waiting":
            nudge_days = _int(b.get("nudge_after_days"), nudge_days, 1)

    out = {"rows": {}, "order": [], "hygiene": [], "no_next": [], "muted": 0, "events": [], "workplace": None}

    def items_of(s):
        # The section's own `max:` still caps what it contributes.
        return s.get("items") or []

    def muted(sid, item):
        return any(m.get("section") == sid and _matches(m["when"], item) for m in mutes)

    def usable(s):
        return s.get("status") == "ok" and sections_cfg.get(s.get("id"), {}).get("bucket") != "none"

    # First pass: what the advice says about tasks (a quiet task is shown once, under drop).
    quiet, blocked = set(), set()
    for s in result.get("sections") or []:
        if s.get("kind") != "advise" or not usable(s):
            continue
        for item in items_of(s):
            if muted(s["id"], item):
                continue
            if item.get("check") == "quiet" and item.get("task"):
                quiet.add(item["task"])
            if item.get("check") == "blocked" and item.get("task"):
                blocked.add(item["task"])

    def add(key, row):
        if key in out["rows"]:
            have = out["rows"][key]
            for sid in row["sources"]:
                if sid not in have["sources"]:
                    have["sources"].append(sid)
            # A section's own `bucket:` is the person's word and wins; otherwise the
            # more urgent reading of the same thing wins over profile order.
            if (row["forced"], -URGENCY[row["bucket"]]) > (have["forced"], -URGENCY[have["bucket"]]):
                have["bucket"], have["forced"] = row["bucket"], row["forced"]
            have["rank"] = min(have["rank"], row["rank"])
            have["why"] += [w for w in row["why"] if w not in have["why"]]
            for k in ("due", "nudge", "estimate"):
                if row.get(k) and not have.get(k):
                    have[k] = row[k]
            have["new"] = have["new"] or row["new"]
            have["changed"] = have["changed"] or row["changed"]
            return
        out["rows"][key] = row
        out["order"].append(key)

    def row(sid, item, bucket, title, why=(), rank=5, **extra):
        r = {"title": str(title or ""), "bucket": bucket, "forced": sid in forced_ids,
             "why": [w for w in why if w], "sources": [sid],
             "rank": rank, "url": item.get("url"), "task": item.get("task"), "new": bool(item.get("new")),
             "changed": bool(item.get("changed"))}
        if _pos_int(item.get("estimate_min")):
            r["estimate"] = item["estimate_min"]
        return {**r, **extra}

    carried = []      # advice that only stands when no other row carries it
    forced_ids = {sid for sid, c in sections_cfg.items() if c.get("bucket") in BUCKETS}
    for s in result.get("sections") or []:
        sid, kind = s.get("id"), s.get("kind")
        cfg = sections_cfg.get(sid, {})
        if s.get("status") == "error":
            out["hygiene"].append(labels["error"].format(title=s.get("title") or sid, reason=s.get("reason", "")))
            continue
        if not usable(s):
            continue
        forced = cfg.get("bucket") if cfg.get("bucket") in BUCKETS else None
        if kind == "calendar":
            out["events"] += items_of(s)
            continue
        if kind == "activity":
            continue
        if kind == "workplace":
            tabs = [i for i in items_of(s) if i.get("state") != "warning"]
            for i in items_of(s):
                if i.get("state") == "warning":
                    out["hygiene"].append(str(i.get("title")))
            if tabs:
                out["workplace"] = labels["workplace"].format(
                    n=len(tabs), new=sum(1 for t in tabs if t.get("state") == "new"),
                    resume=sum(1 for t in tabs if t.get("state") == "resume"))
            continue
        for item in items_of(s):
            if muted(sid, item):
                out["muted"] += 1
                continue
            iid = str(item.get("id"))
            if kind == "inbox":
                due = _when(item.get("due"))
                why = []
                if item.get("state") == "deferred":
                    back = _when(item.get("until"))
                    if back:
                        why.append(labels["back_on"].format(date=f"{back:%d.%m}"))
                if item.get("due"):
                    why.append(labels["due"].format(when=_fmt_when(item["due"], now, labels)))
                if item.get("gate") == "only-you":
                    why.append(labels["only_you"])
                soon = due is not None and due.date() <= horizon
                if item.get("state") == "deferred":
                    bucket = "do" if soon or item.get("gate") == "only-you" else "plan"
                else:
                    bucket = "do" if item.get("urgency") in ("now", "today") or soon else "plan"
                rank = 0 if item.get("urgency") == "now" else 1 if soon else 2
                # An item the briefing filed from a tracker row is that row: one line, not two.
                key = f"inbox:{iid}"
                filed = str(item.get("key") or "").split(":", 3)
                if filed[0] == "briefing" and len(filed) == 4:
                    key = _item_key(filed[2], filed[3])
                add(key, row(sid, item, forced or bucket, item.get("title"), why, rank, due=item.get("due")))
            elif kind == "advise":
                check = item.get("check")
                if check == "wip":
                    out["hygiene"].append(str(item.get("title")))
                elif check == "quiet":
                    add(f"task:{item.get('task')}", row(sid, item, forced or "drop", item.get("title"), (), 5))
                elif check == "collision":
                    add(f"advise:{iid}", row(sid, item, forced or "do", item.get("title"), [labels["collides"]], 0))
                elif check in ("blocked", "waiting", "due"):
                    carried.append((sid, item, forced))
                else:
                    add(f"advise:{iid}", row(sid, item, forced or "plan", item.get("title")))
            elif kind == "tasks":
                if iid in quiet:
                    continue
                nxt = item.get("next")
                if isinstance(nxt, str):
                    nxt = {"what": nxt}
                age = _days_since(item.get("changed_at"), now)
                if item.get("blocked_by"):
                    age = _days_since(item.get("blocked_since"), now) if item.get("blocked_since") else age
                    why = [labels["waiting_days"].format(n=age) if age is not None else "",
                           _short(item["blocked_by"], 60)]
                    nudge = iid in blocked or (age is not None and age >= nudge_days)
                    add(f"task:{iid}", row(sid, item, forced or "waiting", item.get("title"), why, 3, nudge=nudge,
                                           task=iid))
                elif isinstance(nxt, dict) and nxt.get("what"):
                    who = str(nxt.get("who") or "me").lower()
                    due = _when(nxt.get("due"))
                    why = [labels["task"].format(slug=iid)]
                    if nxt.get("due"):
                        why.append(labels["due"].format(when=_fmt_when(nxt["due"], now, labels)))
                    extra = {"task": iid, "due": nxt.get("due")}
                    if _pos_int(nxt.get("estimate_min")):
                        extra["estimate"] = nxt["estimate_min"]
                    if who in WHO_BRIDGE:
                        bucket = "delegate"
                    elif who in you:
                        bucket = "do" if due is not None and due.date() <= horizon else "plan"
                    else:
                        bucket = "waiting"
                        why = [labels["with"].format(who=nxt.get("who")),
                               labels["waiting_days"].format(n=age) if age is not None else ""] + why
                        extra["nudge"] = age is not None and age >= nudge_days
                    add(f"task:{iid}", row(sid, item, forced or bucket, nxt["what"], why,
                                           1 if bucket == "do" else 4, **extra))
                else:
                    out["no_next"].append(iid)
            else:   # tracker, command
                state = item.get("state")
                if state in ("done", "removed"):
                    continue
                if item.get("category") == "qa" or state == "review":
                    bucket = "do"
                elif state == "blocked":
                    bucket = "waiting"
                else:
                    bucket = "plan"
                label = item.get("raw_state") or state
                add(_item_key(sid, iid), row(sid, item, forced or bucket, item.get("title"),
                                             [iid, str(label) if label else ""], 2 if bucket == "do" else 4))

    # blocked / waiting / due advice repeats what a task or inbox row already says;
    # it stands on its own only when no such row is in the view.
    for sid, item, forced in carried:
        check = item.get("check")
        subject = str(item.get("id") or "").split(":", 2)[-1]
        carrier = f"task:{item.get('task')}" if check == "blocked" else f"inbox:{subject}"
        if carrier in out["rows"]:
            continue
        bucket = {"blocked": "waiting", "due": "do", "waiting": "plan"}[check]
        add(f"advise:{item.get('id')}", row(sid, item, forced or bucket, item.get("title"), (), 2))
    return out


def build(result: dict, profile: dict, style: str | None = None) -> dict:
    """The view of one collected briefing: plain data, drawn by `draw`, read by an agent."""
    style = style_of(profile, style)
    view = _cfg(profile)
    labels = _labels(view)
    now = _when(result.get("collected_at")) or dt.datetime.now()
    data = _rows(result, profile, view, labels, now)
    shown, hidden_ids = _bucket_cfg(view)
    titles = {b: DEFAULT_BUCKETS[b]["title"] for b in BUCKETS} | {b["id"]: b["title"] for b in shown}

    rows = [data["rows"][k] for k in data["order"]]
    rows.sort(key=lambda r: (URGENCY[r["bucket"]], r["rank"], str(_when(r.get("due")) or "9999")))

    hygiene = list(data["hygiene"])
    if data["no_next"]:
        hygiene.append(labels["no_next"].format(n=len(data["no_next"]), slugs=", ".join(data["no_next"])))
    if data["muted"]:
        hygiene.append(labels["muted"].format(n=data["muted"]))
    hidden = [r for r in rows if r["bucket"] in hidden_ids]
    if hidden:
        ids = sorted({r["bucket"] for r in hidden}, key=lambda b: URGENCY[b])
        hygiene.append(labels["hidden"].format(n=len(hidden), ids=", ".join(ids)))
    visible = [r for r in rows if r["bucket"] not in hidden_ids]

    events = _events(data["events"], now)
    plan_cfg: dict = view["plan"] if isinstance(view.get("plan"), dict) else {}
    workday: dict = plan_cfg["workday"] if isinstance(plan_cfg.get("workday"), dict) else {}
    day_start, day_end = workday.get("start", "08:00"), workday.get("end", "18:00")
    if not (isinstance(day_start, str) and HHMM.match(day_start) and isinstance(day_end, str)
            and HHMM.match(day_end) and _hm(day_start) < _hm(day_end)):
        day_start, day_end = "08:00", "18:00"

    width = view.get("width")
    out = {"style": style, "collected_at": result.get("collected_at"), "headline": None, "since": None,
           "buckets": [], "hygiene": hygiene, "workplace": data["workplace"], "more": 0, "titles": titles,
           "answer_keys": view.get("answer_keys", True) is not False,
           "show_hygiene": view.get("hygiene", "bottom") != "hide",
           "color": view.get("color", "auto"), "width": width if _pos_int(width) and width >= 40 else 100,
           "labels": labels}

    if view.get("headline", True) is not False:
        out["headline"] = _headline(visible, events, now, labels, day_end)
    if view.get("since_last", True) is not False and result.get("previous_at"):
        prev = _when(result["previous_at"])
        if prev:
            stamp = f"{prev:%H:%M}" if prev.date() == now.date() else f"{prev:%d.%m %H:%M}"
            out["since"] = labels["since"].format(time=stamp, new=sum(1 for r in visible if r["new"]),
                                                   changed=sum(1 for r in visible if r["changed"] and not r["new"]))

    cap = _int(view.get("max_items"), 3 if style == "brevity" else 12, 1)
    if style == "brevity":
        cap = min(cap, 3)
        pick = ([r for r in visible if r["bucket"] == "do"] +
                [r for r in visible if r["bucket"] == "waiting" and r.get("nudge")] +
                [r for r in visible if r["bucket"] in ("plan", "delegate")] +
                [r for r in visible if r["bucket"] == "waiting" and not r.get("nudge")] +
                [r for r in visible if r["bucket"] == "drop"])
        out["top"] = [{**r, "why": r["why"] or [titles[r["bucket"]]]} for r in pick[:cap]]
        out["more"] = max(0, len(visible) - len(out["top"]))
        return out

    if style == "plan":
        # The plan shows every row (laid out, meanwhile, waiting, drop, later): nothing is "more".
        out["plan"] = _plan(visible, events, now, plan_cfg, day_start, day_end)
        return out

    left = cap
    for b in shown:
        mine = [r for r in visible if r["bucket"] == b["id"]]
        take = mine[:max(0, left)]
        left -= len(take)
        out["more"] += len(mine) - len(take)
        if take:
            out["buckets"].append({"id": b["id"], "title": b["title"], "options": list(b.get("options") or []),
                                   "items": take})
    return out


def _headline(rows: list, events: list, now: dt.datetime, labels: dict, day_end: str) -> str:
    parts = [labels["yours_today"].format(n=sum(1 for r in rows if r["bucket"] == "do"))]
    current = next((e for e in events if e[0] <= now < e[1]), None)
    upcoming = next((e for e in events if e[0] > now and e[0].date() == now.date()), None)
    if current:
        parts.append(labels["busy_until"].format(title=_short(current[2], 40),
                                                 time=_fmt_when(current[1].isoformat(timespec="minutes"),
                                                                now, labels).replace(f"{labels['today']} ", "")))
    elif upcoming:
        parts.append(labels["free_until"].format(time=f"{upcoming[0]:%H:%M}"))
    elif now.hour * 60 + now.minute < _hm(day_end):
        parts.append(labels["free_rest"])
    dated = [(_when(r["due"]), r["title"], r["due"]) for r in rows if r.get("due") and _when(r["due"])]
    dated += [(e[0], e[2], e[0].isoformat(timespec="minutes")) for e in events if e[0].date() > now.date()]
    dated = sorted((d for d in dated if d[0] > now), key=lambda d: d[0])
    if dated:
        _, title, raw = dated[0]
        parts.append(labels["next_date"].format(when=_fmt_when(raw, now, labels), title=_short(title, 48)))
    return " · ".join(parts)


def _plan(rows, events, now, cfg, day_start, day_end) -> dict:
    """Lay your rows (do, then plan) into today's free gaps between start and end of day.

    Each row takes the earliest free gap long enough for it, so a long row that does not
    fit early never pushes a short one past a gap it would have fitted."""
    minutes = _int(cfg.get("default_minutes"), 30, 1)
    busy = sorted(_today(events, now))
    now_min = now.hour * 60 + now.minute
    first = max(_hm(day_start), -(-now_min // 15) * 15)
    stop = _hm(day_end)
    free, cursor = [], first
    for s, e, _ in busy:
        if s > cursor:
            free.append([cursor, min(s, stop)])
        cursor = max(cursor, e)
    if cursor < stop:
        free.append([cursor, stop])
    free = [f for f in free if f[1] > f[0]]
    slots = [{"start": _clock(s), "end": _clock(e), "title": t, "kind": "event"} for s, e, t in busy]
    later = []
    for r in [r for r in rows if r["bucket"] == "do"] + [r for r in rows if r["bucket"] == "plan"]:
        length = r.get("estimate") or minutes
        gap = next((f for f in free if f[1] - f[0] >= length), None)
        if gap is None:
            later.append(r["title"])
            continue
        slots.append({"start": _clock(gap[0]), "end": _clock(gap[0] + length), "title": r["title"],
                      "kind": "work", "why": r["why"]})
        gap[0] += length
    slots.sort(key=lambda s: (s["start"], s["kind"] != "event"))
    return {"slots": slots, "parallel": [r["title"] for r in rows if r["bucket"] == "delegate"],
            "waiting": [r["title"] for r in rows if r["bucket"] == "waiting"],
            "drop": [r["title"] for r in rows if r["bucket"] == "drop"], "later": later, "shutdown": day_end}


# ---------------------------------------------------------------- draw

def draw(view: dict, color: bool = False, width: int | None = None) -> str:
    """Terminal text. Colour carries meaning only (due now, waiting, scaffolding dimmed)."""
    use = color and view.get("color", "auto") != "none"
    width = width or _int(view.get("width"), 100, 40)
    labels = view["labels"]
    titles = view.get("titles") or {b: DEFAULT_BUCKETS[b]["title"] for b in BUCKETS}

    def c(code, text):
        return f"\x1b[{code}m{text}\x1b[0m" if use else text

    def wrap(text, indent="", hang=None, style=None):
        lines = textwrap.wrap(text, width=width, initial_indent=indent, subsequent_indent=hang or indent,
                              break_long_words=False, break_on_hyphens=False) or [indent]
        return [c(style, line) if style else line for line in lines]

    out = []
    if view.get("headline"):
        out += wrap(view["headline"], style="1")
    if view.get("since"):
        out += wrap(view["since"], style="2")

    if view["style"] == "brevity":
        for r in view.get("top", []):
            out.append("")
            out += wrap(r["title"], style="1")
            out += wrap(f"{labels['why']}: " + " · ".join(r["why"]), indent="  ", hang="  ", style="2")
    elif view["style"] == "plan" and view.get("plan"):
        plan = view["plan"]
        out.append("")
        for s in plan["slots"]:
            line = f"  {s['start']}-{s['end']}  {s['title']}"
            out += wrap(line, hang=" " * 15, style="2" if s["kind"] == "event" else None)
        for key, title, style in (("parallel", labels["meanwhile"], None), ("waiting", titles["waiting"], "2"),
                                  ("drop", titles["drop"], "2"), ("later", labels["later"], "2")):
            if plan.get(key):
                out += wrap(f"{title}: " + " · ".join(plan[key]), indent="  ", hang="    ", style=style)
        out += wrap(labels["shutdown"].format(time=plan["shutdown"]), indent="  ", style="1")
    else:
        n = 0
        for b in view["buckets"]:
            out.append("")
            head = f"── {b['title']} ──"
            if view.get("answer_keys") and b.get("options"):
                letters = "abcdefghij"
                head += " " + " · ".join(f"{letters[i]} {o}" for i, o in enumerate(b["options"][:10]))
            out += wrap(head, style="1;31" if b["id"] == "do" else "2" if b["id"] in ("waiting", "drop") else "1")
            for r in b["items"]:
                n += 1
                num = f"{n:>3}  " if view.get("answer_keys") else "  -  "
                extras = list(r["why"])
                if len(r["sources"]) > 1:
                    extras.append("+".join(r["sources"]))
                if r.get("nudge"):
                    extras.append(labels["nudge"])
                if r["new"]:
                    extras.append(labels["new"])
                text = r["title"] + (f"  ({' · '.join(extras)})" if extras else "")
                lines = textwrap.wrap(text, width=width, initial_indent=num, subsequent_indent=" " * len(num),
                                      break_long_words=False, break_on_hyphens=False)
                urgent = b["id"] == "do" and r["rank"] <= 1
                dim = b["id"] in ("waiting", "drop") and not r.get("nudge")
                out += [c("31", line) if urgent else c("2", line) if dim else line for line in lines]

    if view.get("workplace") and view["style"] != "brevity":
        out.append("")
        out += wrap(view["workplace"])
    # Housekeeping in every style: a failed source or a muted row is never silent.
    if view.get("show_hygiene", True) and view.get("hygiene"):
        out.append("")
        out += wrap(f"── {labels['housekeeping']} ──", style="2")
        for h in view["hygiene"]:
            out += wrap(h, indent="  · ", hang="    ", style="2")
    out.append("")
    if view.get("more"):
        out += wrap(labels["more"].format(n=view["more"]), style="2")
    out += wrap(labels["end"], style="2")
    return "\n".join(out)
