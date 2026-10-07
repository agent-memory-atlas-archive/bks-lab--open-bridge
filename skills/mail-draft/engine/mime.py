"""The draft as an .eml file: text and HTML parts, attachments, marked unsent.

`X-Unsent: 1` makes Outlook (Windows and Mac) and Thunderbird open the file as
a draft with a Send button. Apple Mail ignores the header and opens a read-only
view, which is why the Apple Mail client does not go through this file.
The .eml is the one output that works on every platform, so it is always
written into the bundle, whatever client the draft is handed to.
"""

from __future__ import annotations

import mimetypes
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid


def _addr(r) -> str:
    return formataddr((r.name, r.address)) if getattr(r, "name", "") else r.address


def build(d) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = d.subject
    if d.sender:
        msg["From"] = d.sender
    msg["To"] = ", ".join(_addr(r) for r in d.to)
    if d.cc:
        msg["Cc"] = ", ".join(_addr(r) for r in d.cc)
    if d.bcc:
        msg["Bcc"] = ", ".join(_addr(r) for r in d.bcc)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    msg["X-Unsent"] = "1"
    if d.priority == "high":
        msg["X-Priority"] = "1"
        msg["Importance"] = "High"
    elif d.priority == "low":
        msg["X-Priority"] = "5"
        msg["Importance"] = "Low"
    msg.set_content(d.text, charset="utf-8")
    msg.add_alternative(d.html, subtype="html", charset="utf-8")
    for path in d.attachments:
        if not path.is_file():
            continue
        ctype, _ = mimetypes.guess_type(path.name)
        maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
        msg.add_attachment(path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name)
    return msg
