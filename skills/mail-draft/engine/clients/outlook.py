"""Microsoft Outlook for Mac: a draft with HTML, recipients, priority, attachments.

What this client cannot do, measured, and therefore reported on every draft:
the sender. `every account` and `default account` both fail through
AppleScript, so the message lands on Outlook's default account and the person
has to switch "From" in the window.

`save` may raise -1701 and save anyway, or not raise and save nothing; without
an open window it stored nothing at all and the message was gone (measured
2026-10-06). So the draft is always opened as a window, the Drafts folder is
counted from a fresh process afterwards. The new Outlook shows scripts only
its local folders, not the account's Drafts, so a zero there is no evidence:
the run then reports the open window as unverified instead of as missing.
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
        repeat with f in (every mail folder)
            set fname to name of f
            if names contains fname then
                set hits to (every message of f whose subject is s)
                set total to total + (count of hits)
            end if
        end repeat
        -- After `open` the message is no longer an outgoing message, it is a
        -- window named "<subject> • <account>" (measured 2026-10-07).
        set windows_open to count of (every window whose name starts with s)
    end tell
    return (total as string) & "|" & (windows_open as string)
end run
'''


def handoff(d, workdir: Path, show: bool = True) -> Handoff:
    if not show:
        # Measured 2026-10-06: without `open`, `save` stored nothing and the
        # message object was gone; no draft, no window, no error.
        return Handoff(False, "outlook", "Outlook keeps a draft only as an open window; "
                       "--hide is not possible here, run without it or use --client eml")
    before = state(d.subject) or (0, 0)
    write_inputs(d, workdir)
    done = osascript(SCRIPT, [str(workdir), "show" if show else "hide", d.priority or "normal"])
    out = (done.stdout or "").strip()
    if done.returncode != 0 or not out.startswith("OK"):
        return Handoff(False, "outlook", (done.stderr or out or "no answer").strip())
    fields = answer_fields(out)
    notes = [f"{len(d.to)} recipient(s)", f"{fields.get('attachments')} attachment(s)",
             "sender: Outlook's default account, switch 'From' in the window"
             + (f" to {d.sender}" if d.sender else "")]
    after = state(d.subject)
    if after is None:
        notes.append("Outlook did not answer the check, not verified")
        return Handoff(True, "outlook", ", ".join(notes), verified=None)
    drafts, windows = after
    if drafts > before[0]:
        return Handoff(True, "outlook", ", ".join(notes), verified=True)
    if windows > before[1]:
        # Measured 2026-10-07 with the new Outlook: scripts see only the 10
        # local folders ("On My Computer"), never the account's own Drafts,
        # where Outlook DID store both test drafts (Apple Mail listed them).
        # A zero there proves nothing; the open window is what can be seen.
        notes.append("the window is open; this Outlook does not show its account folders to "
                     "scripts, so whether it is already in Drafts cannot be checked here")
        return Handoff(True, "outlook", ", ".join(notes), verified=None)
    notes.append("no window and no draft with this subject: nothing was created")
    return Handoff(False, "outlook", ", ".join(notes), verified=False)


def state(subject: str) -> tuple[int, int] | None:
    """(drafts with this subject in folders scripts can see, open windows with it)."""
    done = osascript(VERIFY, [subject], timeout=60)
    raw = (done.stdout or "").strip()
    drafts, _, windows = raw.partition("|")
    if drafts.isdigit() and windows.isdigit():
        return int(drafts), int(windows)
    return None


def verify(subject: str) -> int | None:
    found = state(subject)
    return None if found is None else found[0]
