"""Preflight: what a human would catch on a second read, caught before the draft exists.

Errors stop the draft. Warnings are printed and the draft is still built,
because the person who presses Send reads them there.

Every check here is one that cost somebody a mail:

- an attachment named in the text and missing from the mail
- a file path that does not exist, which some clients drop without a word
- a `{placeholder}` that reached the recipient as written
- a link whose visible text is one address and whose target is another
- tracking parameters in a link the recipient can see
- a `file://` link or a stylesheet variable copied out of a browser
- a remote image, which most clients block until the reader allows it
- an expired or not yet valid footer notice (reported, it is already hidden)
"""

from __future__ import annotations

import re

from . import footer as footer_mod

TRACKING = re.compile(r"[?&](utm_[a-z]+|fbclid|gclid|mc_eid|mkt_tok)=", re.I)
LEFTOVER = re.compile(r"(?<!\{)\{([a-z_]+)\}(?!\})")
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def _host(url: str) -> str:
    m = re.match(r"^[a-z]+://([^/?#]+)", url.strip(), re.I)
    return (m.group(1) if m else "").lower().removeprefix("www.")


def run(d, profile: dict, cfg) -> None:
    body = d.markdown

    for path in d.attachments:
        if not path.is_file():
            d.errors.append(f"attachment not found: {path}")
            continue
        size = path.stat().st_size / (1024 * 1024)
        if size > float(cfg.get("max_attachment_mb") or 20):
            d.warnings.append(f"attachment {path.name} is {size:.1f} MB, many servers refuse mail over 20-25 MB")
    total = sum(p.stat().st_size for p in d.attachments if p.is_file()) / (1024 * 1024)
    if total > 25:
        d.errors.append(f"attachments total {total:.1f} MB, above what most servers accept (25 MB)")

    words = [str(w).lower() for w in (profile.get("attachment_words") or cfg.get("attachment_words") or [])]
    lower = body.lower()
    promised = [w for w in words if re.search(rf"(?<!\w){re.escape(w)}(?!\w)", lower)]
    if promised and not d.attachments:
        d.warnings.append(f"the text says '{promised[0]}' but nothing is attached")
    require = profile.get("require") or {}
    if require.get("attachments") and not d.attachments:
        d.errors.append(f"profile {d.profile_id} requires an attachment and none is given")
    if require.get("subject_pattern"):
        try:
            if not re.search(str(require["subject_pattern"]), d.subject):
                d.errors.append(f"subject '{d.subject}' does not match the profile's pattern "
                                f"{require['subject_pattern']}")
        except re.error as err:
            d.errors.append(f"profile {d.profile_id}: subject_pattern is not a valid regex ({err})")

    # Code is example text: `{name}` in a code span or block is meant literally.
    prose = re.sub(r"```.*?```", "", body, flags=re.S)
    prose = re.sub(r"`[^`]*`", "", prose)
    for name in sorted(set(LEFTOVER.findall(prose + "\n" + d.subject))):
        if name != "visitor_query":
            d.errors.append(f"placeholder {{{name}}} is still in the text")
    if not d.subject.strip():
        d.errors.append("the subject is empty")

    for text, url in LINK.findall(body):
        if text.startswith("["):
            continue
        shown = _host(text if "://" in text else f"https://{text}") if re.match(r"^(https?://)?[\w-]+(\.[\w-]+)+(/\S*)?$", text) else ""
        if shown and _host(url) and shown != _host(url):
            d.warnings.append(f"link text '{text}' points to a different host ({_host(url)})")
    for url in re.findall(r"https?://\S+", body) + footer_mod.urls(d.footer_cfg):
        if TRACKING.search(url):
            d.warnings.append(f"tracking parameters in a visible link: {url}")
    if re.search(r"\]\(file:|\bfile://", body):
        d.errors.append("a file:// link cannot be opened by the recipient")
    if "var(--" in body or "calc(" in body:
        d.errors.append("the body carries CSS variables or calc(), copied from a browser; no mail client resolves them")
    if re.search(r"!\[[^\]]*\]\(https?://", body):
        d.warnings.append("remote images are blocked by most clients until the reader allows them")

    notice = d.footer_cfg.get("notice") if d.footer_cfg else None
    if isinstance(notice, dict) and notice.get("text"):
        if not footer_mod.notice_active(notice, d.today):
            d.warnings.append(f"footer notice is outside its window and left out: {notice['text']}")

    if d.client == "outlook" and d.sender:
        d.warnings.append(f"Outlook cannot set the sender by script; check 'From' is {d.sender} before sending")
    if d.style_skill:
        d.warnings.append(f"tone: load the {d.style_skill} skill and check the text against it")
