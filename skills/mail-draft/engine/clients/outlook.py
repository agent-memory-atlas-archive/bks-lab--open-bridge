"""Microsoft Outlook for Mac: a draft with HTML, recipients, priority, attachments.

What this client cannot do, measured, and therefore reported on every draft:
the sender. `every account` and `default account` both fail through
AppleScript, so the message lands on Outlook's default account and the person
has to switch "From" in the window.

`save` may raise -1701 and save anyway, or not raise and save nothing; without
an open window it stored nothing at all and the message was gone (measured
2026-10-06). So the draft is always opened as a window, the Drafts folder is
counted from a fresh process afterwards, and when it is not there yet the
report says to press Cmd+S rather than calling it a draft.
"""

from __future__ import annotations

from pathlib import Path

from . import Handoff, answer_fields, osascript, write_inputs

SCRIPT = r'''
on readFile(p)
    try
        return read (POSIX file p) as «class utf8»
    on error
        return ""
    end try
end readFile

on nonEmptyLines(t)
    set out to {}
    if t is "" then return out
    repeat with x in paragraphs of t
        set s to x as text
        if s is not "" then set end of out to s
    end repeat
    return out
end nonEmptyLines

on run argv
    set d to item 1 of argv
    set showIt to ((item 2 of argv) is "show")
    set prio to item 3 of argv
    set theSubject to my readFile(d & "/subject.txt")
    set theHtml to my readFile(d & "/body.html")
    set toList to my nonEmptyLines(my readFile(d & "/to.txt"))
    set ccList to my nonEmptyLines(my readFile(d & "/cc.txt"))
    set bccList to my nonEmptyLines(my readFile(d & "/bcc.txt"))
    set attList to my nonEmptyLines(my readFile(d & "/attachments.txt"))
    tell application "Microsoft Outlook"
        set m to make new outgoing message with properties {subject:theSubject, content:theHtml}
        repeat with a in toList
            make new recipient at m with properties {email address:{address:(a as text)}}
        end repeat
        repeat with a in ccList
            make new cc recipient at m with properties {email address:{address:(a as text)}}
        end repeat
        repeat with a in bccList
            make new bcc recipient at m with properties {email address:{address:(a as text)}}
        end repeat
        try
            if prio is "high" then set priority of m to priority high
            if prio is "low" then set priority of m to priority low
        end try
        repeat with p in attList
            make new attachment at m with properties {file:(POSIX file (p as text))}
        end repeat
        set attachedList to every attachment of m
        set nAtt to (count of attachedList) as string
        try
            save m
        end try
        if showIt then open m
    end tell
    return "OK|attachments=" & nAtt
end run
'''

VERIFY = r'''
on run argv
    set s to item 1 of argv
    set names to {"Drafts", "Entwürfe", "Brouillons", "Borradores", "Bozze", "Concepten", "Rascunhos", "Utkast"}
    tell application "Microsoft Outlook"
        set total to 0
        set found to false
        repeat with f in (every mail folder)
            set fname to name of f
            if names contains fname then
                set found to true
                set hits to (every message of f whose subject is s)
                set total to total + (count of hits)
            end if
        end repeat
    end tell
    if not found then return "nofolder"
    return total as string
end run
'''


def handoff(d, workdir: Path, show: bool = True) -> Handoff:
    if not show:
        # Measured 2026-10-06: without `open`, `save` stored nothing and the
        # message object was gone; no draft, no window, no error.
        return Handoff(False, "outlook", "Outlook keeps a draft only as an open window; "
                       "--hide is not possible here, run without it or use --client eml")
    before = verify(d.subject) or 0
    write_inputs(d, workdir)
    done = osascript(SCRIPT, [str(workdir), "show" if show else "hide", d.priority or "normal"])
    out = (done.stdout or "").strip()
    if done.returncode != 0 or not out.startswith("OK"):
        return Handoff(False, "outlook", (done.stderr or out or "no answer").strip())
    fields = answer_fields(out)
    notes = [f"{len(d.to)} recipient(s)", f"{fields.get('attachments')} attachment(s)",
             "sender: Outlook's default account, switch 'From' in the window"
             + (f" to {d.sender}" if d.sender else "")]
    count = verify(d.subject)
    if count is None:
        notes.append("Drafts folder not found by name, not verified")
        return Handoff(True, "outlook", ", ".join(notes), verified=None)
    if count <= before:
        # The window is open, but Outlook has not stored it: a restart loses it.
        # An older draft with the same subject does not count.
        notes.append("open as a window but NOT yet in Drafts: press Cmd+S in it, "
                     "or it is lost when Outlook restarts")
    return Handoff(True, "outlook", ", ".join(notes), verified=count > before)


def verify(subject: str) -> int | None:
    done = osascript(VERIFY, [subject], timeout=60)
    raw = (done.stdout or "").strip()
    if raw.isdigit():
        return int(raw)
    return None
