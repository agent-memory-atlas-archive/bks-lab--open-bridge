"""Owner policy for peer requests: the owner's rules, and the ledger of every request.

A peer may ask for something to be DONE rather than answered (see ``executor.py``,
``bridge_request`` metadata). Whether that needs the owner is decided here:

- ``rules.yaml`` holds the owner's standing decisions, one per peer and subject:
  ``allow`` (no need to ask again) or ``deny`` (never). The runtime adds a rule only
  when the owner said so while deciding; the owner may also edit the file by hand or
  use the CLI below. It is read fresh on every request, so an edit applies at once. A
  revoked rule stays in the file with ``revoked_at``, so what was allowed when stays
  readable.
- ``ledger.jsonl`` is append-only: who asked what, when, who decided (the owner or
  which rule), and what came of it. Rule changes are recorded there too.

Declared in ``agent.yaml``::

    requests:
      enabled: true
      rules: "policy/rules.yaml"          # default, relative to the instance dir
      ledger: "policy/ledger.jsonl"       # default
      execute:                            # optional: what runs after a yes
        command: ["python3", "${tools_dir}/execute.py"]
        timeout_sec: 900

A subject is a short key the PEER sends with its request, for example
``cloudflare/example.org/member``. It is a label, not a guarantee: a rule matches on it,
and the request text travels with it. What a yes actually permits is up to the
execute command, which gets the full request and the rule that let it through.

Owner CLI (run from ``agents/``)::

    python3 -m _runtime.policy <instance> list
    python3 -m _runtime.policy <instance> history [--peer ID]
    python3 -m _runtime.policy <instance> add --peer ID --subject S --effect allow|deny [--note N] [--expires ISO]
    python3 -m _runtime.policy <instance> revoke <rule-id>
"""
from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import re
import secrets
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

try:  # POSIX; on Windows rule writes are not serialised across processes
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

logger = logging.getLogger(__name__)

EFFECTS = frozenset({"allow", "deny"})

# What a PEER may send as subject: no wildcard, no whitespace, no line breaks, so it
# can neither widen a rule the owner makes from it nor fake lines in what the owner
# reads. The OWNER may end a rule subject with ``*`` (prefix), or set ``*`` alone.
SUBJECT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,199}$")


class PolicyError(Exception):
    """The rules file cannot be read safely; nothing is written over it."""


def valid_peer_subject(subject: str) -> bool:
    return bool(SUBJECT_RE.match(subject))


def valid_rule_subject(subject: str) -> bool:
    return subject == "*" or valid_peer_subject(subject.removesuffix("*"))
_RULE_FIELDS = ("id", "peer", "subject", "effect", "note", "created_at", "created_by",
                "source_task", "expires", "revoked_at", "revoked_by")


@dataclass(frozen=True)
class RequestsConfig:
    enabled: bool = False
    rules_path: Path = Path("policy/rules.yaml")
    ledger_path: Path = Path("policy/ledger.jsonl")
    execute_command: tuple[str, ...] = ()
    execute_timeout_sec: float = 900.0


def parse_requests(instance: str, spec: dict | None, *, inst_dir: Path, tools_dir: str,
                   has_approval: bool, has_auth: bool) -> RequestsConfig:
    """Resolve the ``requests:`` block; raise on anything that would not run safely."""
    if not spec or not spec.get("enabled"):
        return RequestsConfig()
    if not has_approval:
        raise ValueError(
            f"agent '{instance}': requests need an approval: block, "
            "the owner must be askable before anything is done for a peer"
        )
    if not has_auth:
        raise ValueError(
            f"agent '{instance}': requests need an auth: block, "
            "a rule names a peer and an anonymous caller is none"
        )
    execute = spec.get("execute") or {}
    command = execute.get("command") or []
    if execute and (not isinstance(command, list) or not command
                    or not all(isinstance(a, str) and a for a in command)):
        raise ValueError(
            f"agent '{instance}': requests.execute.command must be a non-empty argv list"
        )
    timeout = float(execute.get("timeout_sec", 900))
    if timeout <= 0:
        raise ValueError(f"agent '{instance}': requests.execute.timeout_sec must be positive")
    return RequestsConfig(
        enabled=True,
        rules_path=inst_dir / spec.get("rules", "policy/rules.yaml"),
        ledger_path=inst_dir / spec.get("ledger", "policy/ledger.jsonl"),
        execute_command=tuple(a.replace("${tools_dir}", tools_dir) for a in command),
        execute_timeout_sec=timeout,
    )


@dataclass(frozen=True)
class Rule:
    id: str
    peer: str
    subject: str
    effect: str
    note: str = ""
    created_at: str = ""
    created_by: str = ""
    source_task: str | None = None
    expires: str | None = None
    revoked_at: str | None = None
    revoked_by: str | None = None

    def active(self, now: datetime) -> bool:
        if self.revoked_at:
            return False
        if self.expires:
            try:
                until = datetime.fromisoformat(self.expires)
            except ValueError:
                return False        # an unreadable expiry never widens a rule
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            if until <= now:
                return False
        return True

    def covers(self, peer: str, subject: str) -> bool:
        if not subject:
            return False
        if self.peer not in ("*", peer):
            return False
        if self.subject.endswith("*"):
            return subject.startswith(self.subject[:-1])
        return self.subject == subject


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rule_from(raw) -> Rule | None:
    if not isinstance(raw, dict):
        return None
    if raw.get("effect") not in EFFECTS or not raw.get("id") or not raw.get("peer") \
            or not raw.get("subject"):
        return None
    kwargs: dict = {k: str(raw[k]) for k in _RULE_FIELDS if raw.get(k) is not None}
    return Rule(**kwargs)


@dataclass
class Policy:
    rules_path: Path
    ledger_path: Path

    # --- rules ----------------------------------------------------------------------

    def _raw_rules(self, *, strict: bool = False) -> list:
        """The rule entries as stored. Missing file: none. Unreadable file: none for
        matching (so every request goes to the owner), PolicyError for a write, which
        must never replace a file it could not read."""
        if not self.rules_path.exists():
            return []
        try:
            data = yaml.safe_load(self.rules_path.read_text("utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            return self._unreadable(f"cannot read {self.rules_path}: {exc}", strict)
        if data is None:
            return []
        rules = data.get("rules") if isinstance(data, dict) else None
        if rules is None and isinstance(data, dict) and "rules" not in data:
            return []
        if not isinstance(rules, list):
            return self._unreadable(f"{self.rules_path}: 'rules' is not a list", strict)
        return rules

    @staticmethod
    def _unreadable(reason: str, strict: bool) -> list:
        if strict:
            raise PolicyError(reason)
        logger.error("policy: %s; treating as no rules, every request goes to the owner", reason)
        return []

    @contextlib.contextmanager
    def _locked(self):
        """Serialise read-modify-write of the rules file across processes (runtime, CLI)."""
        self.rules_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.rules_path.with_name(self.rules_path.name + ".lock")
        with open(lock_path, "a+") as fh:
            if fcntl is None:
                yield
                return
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def rules(self) -> list[Rule]:
        out = []
        for raw in self._raw_rules():
            rule = _rule_from(raw)
            if rule is None:
                logger.warning("policy: skipping unusable rule entry %r", raw)
                continue
            out.append(rule)
        return out

    def match(self, peer: str, subject: str, *, now: datetime | None = None) -> Rule | None:
        """The rule that decides ``peer``'s request on ``subject``; deny wins over allow."""
        now = now or _now()
        hits = [r for r in self.rules() if r.active(now) and r.covers(peer, subject)]
        for effect in ("deny", "allow"):
            for rule in hits:
                if rule.effect == effect:
                    return rule
        return None

    def _write_rules(self, raws: list) -> None:
        self.rules_path.parent.mkdir(parents=True, exist_ok=True)
        text = (
            "# Owner rules for peer requests. Edited by the owner, or by the runtime when the\n"
            "# owner decided with a rule. Revoked rules stay, so what was allowed when stays\n"
            "# readable. Format: agents/_runtime/policy.py\n"
            + yaml.safe_dump({"rules": raws}, allow_unicode=True, sort_keys=False)
        )
        fd, tmp = tempfile.mkstemp(dir=self.rules_path.parent, prefix=".rules-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, self.rules_path)

    def add_rule(self, *, peer: str, subject: str, effect: str, note: str = "", by: str,
                 source_task: str | None = None, expires: str | None = None,
                 now: datetime | None = None) -> Rule:
        if effect not in EFFECTS:
            raise ValueError(f"effect must be allow or deny, not {effect!r}")
        if not peer or not subject:
            raise ValueError("a rule needs a peer and a subject")
        if not valid_rule_subject(subject):
            raise ValueError(f"not a valid rule subject: {subject!r}")
        now = now or _now()
        rule = Rule(id=f"r-{now:%Y%m%d}-{secrets.token_hex(3)}", peer=peer, subject=subject,
                    effect=effect, note=note or "", created_at=now.isoformat(), created_by=by,
                    source_task=source_task, expires=expires)
        with self._locked():
            raws = self._raw_rules(strict=True)
            raws.append({k: v for k, v in asdict(rule).items() if v is not None})
            self._write_rules(raws)
        self.record("rule_added", peer=peer, by=by, task_id=source_task, subject=subject,
                    rule=asdict(rule), now=now)
        return rule

    def revoke(self, rule_id: str, *, by: str, now: datetime | None = None) -> None:
        now = now or _now()
        with self._locked():
            raws = self._raw_rules(strict=True)
            for raw in raws:
                if isinstance(raw, dict) and raw.get("id") == rule_id:
                    raw["revoked_at"] = now.isoformat()
                    raw["revoked_by"] = by
                    self._write_rules(raws)
                    break
            else:
                raise KeyError(rule_id)
        self.record("rule_revoked", peer=raw.get("peer"), by=by, rule_id=rule_id, now=now)

    # --- ledger ---------------------------------------------------------------------

    def record(self, event: str, *, now: datetime | None = None, **fields) -> None:
        entry = {"ts": (now or _now()).isoformat(), "event": event, **fields}
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with self.ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def history(self, peer: str | None = None) -> list[dict]:
        if not self.ledger_path.exists():
            return []
        out = []
        for line in self.ledger_path.read_text("utf-8").splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if peer is None or entry.get("peer") in (peer, "*"):
                out.append(entry)
        return out

    def view_for(self, peer: str, *, limit: int = 30, now: datetime | None = None) -> str:
        """What ``peer`` may know: the rules naming it (or every peer) and its own history."""
        now = now or _now()
        lines = ["Rules for you:"]
        mine = [r for r in self.rules() if r.peer in (peer, "*")]
        if not mine:
            lines.append("- none yet; every request goes to the owner")
        for r in mine:
            state = "active" if r.active(now) else ("revoked " + r.revoked_at if r.revoked_at
                                                     else "expired")
            lines.append(f"- {r.id}: {r.effect} {r.subject} ({state}, set {r.created_at[:10]} "
                         f"by {r.created_by}){': ' + r.note if r.note else ''}")
        lines.append("")
        lines.append(f"Your last requests and rule changes (up to {limit}, times in UTC):")
        events = [e for e in self.history(peer) if e.get("peer") == peer][-limit:]
        if not events:
            lines.append("- none")
        for e in events:
            detail = e.get("request") or e.get("verdict") or e.get("status") or e.get("rule_id") \
                or (e.get("rule") or {}).get("id") or ""
            by = f" by {e['by']}" if e.get("by") else ""
            lines.append(f"- {e['ts'][:16].replace('T', ' ')} UTC {e['event']}{by} [{e.get('task_id', '-')}] "
                         f"{e.get('subject', '')} {detail}".rstrip())
        return "\n".join(lines)


def policy_for(cfg: RequestsConfig) -> Policy:
    return Policy(cfg.rules_path, cfg.ledger_path)


def _main(argv: list[str] | None = None) -> int:
    from .config import load_agent_config  # late: config imports this module

    p = argparse.ArgumentParser(prog="python3 -m _runtime.policy", description="Owner rules and ledger for peer requests.")
    p.add_argument("instance")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    h = sub.add_parser("history"); h.add_argument("--peer")
    a = sub.add_parser("add")
    a.add_argument("--peer", required=True); a.add_argument("--subject", required=True)
    a.add_argument("--effect", required=True, choices=sorted(EFFECTS))
    a.add_argument("--note", default=""); a.add_argument("--expires")
    r = sub.add_parser("revoke"); r.add_argument("rule_id")
    args = p.parse_args(argv)

    cfg = load_agent_config(args.instance, environment="cli")
    if not cfg.requests.enabled:
        print(f"agent '{args.instance}' has no requests: block enabled", file=sys.stderr)
        return 2
    pol = policy_for(cfg.requests)
    if args.cmd == "list":
        now = _now()
        for rule in pol.rules():
            state = "active" if rule.active(now) else "inactive"
            print(f"{rule.id}\t{state}\t{rule.effect}\t{rule.peer}\t{rule.subject}\t{rule.note}")
    elif args.cmd == "history":
        for entry in pol.history(args.peer):
            print(json.dumps(entry, ensure_ascii=False))
    elif args.cmd == "add":
        rule = pol.add_rule(peer=args.peer, subject=args.subject, effect=args.effect,
                            note=args.note, by="owner-cli", expires=args.expires)
        print(rule.id)
    elif args.cmd == "revoke":
        try:
            pol.revoke(args.rule_id, by="owner-cli")
        except KeyError:
            print(f"no rule {args.rule_id}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
