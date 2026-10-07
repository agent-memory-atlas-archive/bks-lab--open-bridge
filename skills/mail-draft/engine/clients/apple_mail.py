"""Apple Mail: a real draft with HTML, sender, recipients and attachments.

`html content` is broken only for READING (it returns an empty string). Setting
it on a new outgoing message works and keeps tables and inline styles as
written, and it is the only route on which the sender can be chosen. The
NSSharingService route that older scripts used turns HTML into rich text
(tables and borders fall apart) and always sends from the default account.

The message is created as a normal compose window and never activated, so Mail
does not take focus from whatever the person is typing in. With `--hide` the
window is closed after saving. An INVISIBLE outgoing message is not an option:
it outlives `save`, cannot be closed or deleted by script, and Mail keeps
re-saving it into Drafts until it quits.
"""

from __future__ import annotations

import time
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
    set theSubject to my readFile(d & "/subject.txt")
    set theHtml to my readFile(d & "/body.html")
    set theSender to my readFile(d & "/sender.txt")
    set toList to my nonEmptyLines(my readFile(d & "/to.txt"))
    set ccList to my nonEmptyLines(my readFile(d & "/cc.txt"))
    set bccList to my nonEmptyLines(my readFile(d & "/bcc.txt"))
    set attList to my nonEmptyLines(my readFile(d & "/attachments.txt"))
    set senderSet to "no"
    tell application "Mail"
        -- Windows that already carry this subject belong to the person; with
        -- one of those open, --hide leaves our window open instead of guessing.
        set preWindows to count of (every window whose name is theSubject)
        -- Always a real window. An invisible outgoing message survives `save`
        -- as an object nobody can close or delete, and Mail keeps re-saving it
        -- into Drafts until it quits (measured: a deleted test draft came back).
        set m to make new outgoing message with properties {subject:theSubject, visible:true}
        if theSender is not "" then
            try
                set sender of m to theSender
                set senderSet to "yes"
            end try
        end if
        tell m
            repeat with a in toList
                make new to recipient at end of to recipients with properties {address:(a as text)}
            end repeat
            repeat with a in ccList
                make new cc recipient at end of cc recipients with properties {address:(a as text)}
            end repeat
            repeat with a in bccList
                make new bcc recipient at end of bcc recipients with properties {address:(a as text)}
            end repeat
        end tell
        set html content of m to theHtml
        -- The HTML is applied asynchronously and replaces the content, and the
        -- attachments live IN the content. Added too early they vanish without
        -- an error, so wait for the HTML before attaching.
        delay 1.5
        set attached to 0
        repeat with p in attList
            try
                tell content of m to make new attachment with properties {file name:((POSIX file (p as text)) as alias)} at after the last paragraph
                set attached to attached + 1
            end try
        end repeat
        -- An attachment is still loading for a moment after it is added; a
        -- save before that stores the draft without it.
        delay 2
        save m
        delay 1
        set actualSender to ""
        try
            set actualSender to (sender of m) as text
        end try
        set closedIt to "no"
        if not showIt and preWindows is 0 then
            -- `--hide`: saved above, then the window closed WITHOUT saving
            -- again, which ends the object. A second save from the closing
            -- window stored the draft without its attachment (measured).
            try
                close (every window whose name is theSubject) saving no
                set closedIt to "yes"
            end try
        end if
    end tell
    set nTo to (count of toList) as string
    set nAtt to attached as string
    return "OK|sender=" & senderSet & "|to=" & nTo & "|attachments=" & nAtt & "|closed=" & closedIt & "|from=" & actualSender
end run
'''

VERIFY = r'''
on run argv
    set s to item 1 of argv
    tell application "Mail"
        set ms to (messages of drafts mailbox whose subject is s)
        set n to count of ms
        if n is 0 then return "0"
        -- The NEWEST with this subject: an older draft of the same name must
        -- not confirm a new one that failed.
        set best to item 1 of ms
        repeat with m in ms
            if (date received of m) > (date received of best) then set best to m
        end repeat
        set src to source of best
    end tell
    return (n as string) & linefeed & src
end run
'''


DEDUPE = r'''
on run argv
    set s to item 1 of argv
    set windowSeconds to (item 2 of argv) as integer
    set cutoff to (current date) - windowSeconds
    tell application "Mail"
        set ms to (messages of drafts mailbox whose subject is s)
        if (count of ms) < 2 then return "0"
        set best to item 1 of ms
        repeat with m in ms
            set dm to date received of m
            set db to date received of best
            if dm > db then set best to m
        end repeat
        set bestId to id of best
        set removed to 0
        repeat with m in ms
            set dm to date received of m
            set mid to id of m
            if mid is not bestId and dm ≥ cutoff then
                delete m
                set removed to removed + 1
            end if
        end repeat
    end tell
    return removed as string
end run
'''


def handoff(d, workdir: Path, show: bool = True) -> Handoff:
    started = time.monotonic()
    before = inspect(d.subject)
    before_count = before[0] if before else 0
    # Apple Mail converts the HTML under the current system appearance and keeps
    # the computed colours, so it gets the version without dark-mode rules.
    write_inputs(d, workdir, html=d.html_static)
    done = osascript(SCRIPT, [str(workdir), "show" if show else "hide"])
    out = (done.stdout or "").strip()
    if done.returncode != 0 or not out.startswith("OK"):
        return Handoff(False, "apple-mail", (done.stderr or out or "no answer").strip())
    fields = answer_fields(out)
    notes = [f"{fields.get('to')} recipient(s)"]
    actual = fields.get("from", "")
    if d.sender:
        # Mail accepts any sender without an error and keeps its default when no
        # account has that address, so only the value read back counts.
        if d.sender.lower() in actual.lower():
            notes.append(f"sender {actual}")
        else:
            notes.append(f"sender NOT {d.sender}: Mail kept {actual or 'its default'} "
                         f"(no account with that address); switch 'From' before sending")
    elif actual:
        notes.append(f"sender {actual} (Mail's default)")
    found = inspect(d.subject)
    if found is None:
        return Handoff(False, "apple-mail", ", ".join(notes) + ", Drafts not readable", verified=None)
    count, saved = found
    if count <= before_count:
        notes.append(f"Drafts holds {count} with this subject, as before ({before_count}): the new one was not saved")
        return Handoff(False, "apple-mail", ", ".join(notes), verified=False)
    if count > before_count + 1:
        # Measured 2026-10-07 on an Exchange account: one run left two drafts
        # five seconds apart (Mail's own autosave of the new window, then the
        # explicit save), and Exchange kept both. Only copies with this subject
        # created during THIS run are removed, never an older draft.
        window = int(time.monotonic() - started) + 5
        done = osascript(DEDUPE, [d.subject, str(window)], timeout=60)
        removed = (done.stdout or "").strip()
        if removed.isdigit() and int(removed):
            notes.append(f"removed {removed} duplicate(s) Mail saved during this run")
            found = inspect(d.subject) or found
            count, saved = found
    expected = sorted(p.name for p in d.attachments if p.is_file())
    if sorted(saved["attachments"]) != expected:
        notes.append(f"attachments in the saved draft: {saved['attachments'] or 'none'}, "
                     f"expected {expected}; attach them by hand before sending")
        return Handoff(False, "apple-mail", ", ".join(notes), verified=True)
    if expected:
        notes.append(f"{len(expected)} attachment(s) in the saved draft")
    return Handoff(True, "apple-mail", ", ".join(notes), verified=True)


def inspect(subject: str) -> tuple[int, dict] | None:
    """Read the saved draft back from a fresh process: count, attachments, sender.

    The creating script's own counts are not evidence: it counted an attachment
    that the saved draft did not contain.
    """
    done = osascript(VERIFY, [subject], timeout=60)
    raw = done.stdout or ""
    head, _, source = raw.partition("\n")
    try:
        count = int(head.strip())
    except ValueError:
        return None
    saved = {"attachments": [], "from": ""}
    if source.strip():
        import email
        from email import policy
        msg = email.message_from_string(source, policy=policy.default)
        saved["from"] = str(msg.get("From", ""))
        saved["attachments"] = [p.get_filename() for p in msg.walk() if p.get_filename()]
    return count, saved


def verify(subject: str) -> int | None:
    found = inspect(subject)
    return None if found is None else found[0]
