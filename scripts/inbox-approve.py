#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Owner approval through the inbox: an agent's held answer waits where everything else waits.

agents/_runtime/approval.py keeps a finished answer until its owner released it
and leaves HOW the owner is asked to a command. This is that command, for a
Bridge with an inbox. Declare it in an agent's agent.yaml:

    approval:
      command: ["python3", "/path/to/bridge/scripts/inbox-approve.py", "--sync"]
      timeout_sec: 3600

It reads the request from stdin, files it as an inbox item (kind draft, gate
only-you, urgency now: an answer leaving to someone else is the owner's call),
and waits until a person decided on that item:

    python3 scripts/inbox.py approve <id>                 -> {"decision": "approve"}
    python3 scripts/inbox.py approve <id> --text "..."    -> {"decision": "edit", "text": "..."}
    python3 scripts/inbox.py reject <id>   (or drop)      -> {"decision": "reject"}
    nobody decided before timeout_sec                     -> {"decision": "timeout"}, item dropped

--sync pushes the new item and pulls while waiting, for an owner who decides on
another machine (`scripts/inbox.py sync`). The runtime fails closed on anything
else, so a crash here means the answer is not sent. Model: docs/inbox.md.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_inbox():
    spec = importlib.util.spec_from_file_location("inbox", Path(__file__).with_name("inbox.py"))
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError("cannot load scripts/inbox.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("inbox", module)
    previous, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=60)


def decision_of(item) -> dict | None:
    for event in reversed(item.events):
        if event.verb == "approve":
            text = event.data.get("text")
            return {"decision": "edit", "text": text} if text else {"decision": "approve"}
        if event.verb in ("reject", "drop", "close"):
            return {"decision": "reject"}
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="inbox-approve.py", description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--poll", type=float, default=5.0, help="seconds between looks at the inbox")
    ap.add_argument("--sync", action="store_true", help="push the item, pull while waiting")
    ap.add_argument("--by", default="agent-approval")
    args = ap.parse_args(argv)

    try:
        request = json.loads(sys.stdin.read())
        answer = str(request["answer"])
    except (ValueError, KeyError, TypeError) as exc:
        print(f"inbox-approve: unreadable request ({exc})", file=sys.stderr)
        return 2
    timeout = float(request.get("timeout_sec") or 3600)
    peer = str(request.get("peer") or "a peer")

    inbox = _load_inbox()
    box = inbox.Inbox(args.root / "work" / "inbox", actor=args.by)
    item_id = box.add(
        source=f"agent-approval/{peer}", kind="draft", gate="only-you", urgency="now",
        summary=f"Answer to {peer} waits for your release: {str(request.get('question') or '')[:80]}",
        detail=f"Question:\n{request.get('question') or ''}\n\nDrafted answer:\n{answer}",
        key=f"agent-approval:{request.get('task_id') or answer[:40]}",
    )
    if args.sync:
        subprocess.run([sys.executable, str(Path(__file__).with_name("inbox.py")), "--root", str(args.root),
                        "--by", args.by, "sync"], capture_output=True, timeout=120)

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if args.sync:
            _git(args.root, "pull", "--rebase", "--autostash")
        decided = decision_of(box.get(item_id))
        if decided:
            print(json.dumps(decided, ensure_ascii=False))
            return 0
        time.sleep(min(args.poll, max(0.0, deadline - time.monotonic())))
    box.event(item_id, "drop", text="nobody released the answer in time")
    print(json.dumps({"decision": "timeout"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
