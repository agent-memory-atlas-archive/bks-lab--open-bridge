"""Owner policy: the rules an owner sets for peer requests, and the ledger of every request.

The rules file is the owner's: the runtime adds a rule only when the owner said so in a
decision, and reads the file fresh on every request, so a hand edit applies at once. A
revoked rule stays in the file with ``revoked_at``, so what was allowed when stays
readable. The ledger is append-only JSON lines: who asked what, when, who decided, and
what came of it.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
import yaml

from _runtime.policy import Policy, RequestsConfig, parse_requests

NOW = datetime(2026, 10, 10, 18, 0, tzinfo=timezone.utc)


@pytest.fixture
def policy(tmp_path):
    return Policy(tmp_path / "policy" / "rules.yaml", tmp_path / "policy" / "ledger.jsonl")


def _ledger(policy):
    return [json.loads(line) for line in policy.ledger_path.read_text("utf-8").splitlines()]


def test_without_rules_nothing_matches(policy):
    assert policy.match("alice", "cloudflare/example.org/dns", now=NOW) is None


def test_a_rule_the_owner_adds_matches_its_peer_and_subject(policy):
    rule = policy.add_rule(peer="alice", subject="cloudflare/example.org/dns", effect="allow",
                           note="DNS for example.org", by="owner", source_task="t-1", now=NOW)
    assert policy.match("alice", "cloudflare/example.org/dns", now=NOW).id == rule.id
    assert policy.match("bob", "cloudflare/example.org/dns", now=NOW) is None
    assert policy.match("alice", "cloudflare/other.org/dns", now=NOW) is None


def test_a_request_without_subject_never_matches(policy):
    policy.add_rule(peer="alice", subject="*", effect="allow", note="", by="owner", now=NOW)
    assert policy.match("alice", "", now=NOW) is None


def test_a_trailing_star_matches_the_prefix(policy):
    policy.add_rule(peer="alice", subject="cloudflare/example.org/*", effect="allow",
                    note="", by="owner", now=NOW)
    assert policy.match("alice", "cloudflare/example.org/dns", now=NOW) is not None
    assert policy.match("alice", "cloudflare/example.orgx/dns", now=NOW) is None


def test_a_star_peer_covers_every_peer(policy):
    policy.add_rule(peer="*", subject="docs/read", effect="allow", note="", by="owner", now=NOW)
    assert policy.match("bob", "docs/read", now=NOW) is not None


def test_deny_wins_over_allow(policy):
    policy.add_rule(peer="alice", subject="cloudflare/*", effect="allow", note="", by="owner", now=NOW)
    deny = policy.add_rule(peer="alice", subject="cloudflare/example.org/delete", effect="deny",
                           note="never", by="owner", now=NOW)
    assert policy.match("alice", "cloudflare/example.org/delete", now=NOW).id == deny.id


def test_an_expired_or_revoked_rule_no_longer_matches(policy):
    old = policy.add_rule(peer="alice", subject="a", effect="allow", note="", by="owner",
                          expires=(NOW - timedelta(days=1)).isoformat(), now=NOW)
    kept = policy.add_rule(peer="alice", subject="b", effect="allow", note="", by="owner", now=NOW)
    assert policy.match("alice", "a", now=NOW) is None
    policy.revoke(kept.id, by="owner", now=NOW)
    assert policy.match("alice", "b", now=NOW) is None
    # Both stay in the file, so what was allowed when stays readable.
    stored = yaml.safe_load(policy.rules_path.read_text("utf-8"))["rules"]
    assert {r["id"] for r in stored} == {old.id, kept.id}
    assert next(r for r in stored if r["id"] == kept.id)["revoked_at"]


def test_a_hand_edit_applies_on_the_next_request(policy):
    policy.rules_path.parent.mkdir(parents=True, exist_ok=True)
    policy.rules_path.write_text(yaml.safe_dump({"rules": [
        {"id": "r-hand", "peer": "alice", "subject": "x", "effect": "allow",
         "note": "by hand", "created_by": "owner", "created_at": NOW.isoformat()},
    ]}), "utf-8")
    assert policy.match("alice", "x", now=NOW).id == "r-hand"


def test_a_broken_rule_entry_is_skipped_not_trusted(policy):
    policy.rules_path.parent.mkdir(parents=True, exist_ok=True)
    policy.rules_path.write_text(yaml.safe_dump({"rules": [
        {"id": "r-bad", "peer": "alice", "subject": "x", "effect": "maybe"},
        "not a mapping",
    ]}), "utf-8")
    assert policy.match("alice", "x", now=NOW) is None


def test_every_event_lands_in_the_ledger_with_time_and_peer(policy):
    policy.record("requested", peer="alice", task_id="t-1", subject="s", request="bitte", now=NOW)
    rule = policy.add_rule(peer="alice", subject="s", effect="allow", note="ok", by="owner",
                           source_task="t-1", now=NOW)
    policy.revoke(rule.id, by="owner", now=NOW)
    events = _ledger(policy)
    assert [e["event"] for e in events] == ["requested", "rule_added", "rule_revoked"]
    assert all(e["ts"] == NOW.isoformat() for e in events)
    assert events[1]["rule"]["id"] == rule.id and events[1]["by"] == "owner"


def test_a_peer_sees_its_own_rules_and_history_only(policy):
    policy.add_rule(peer="alice", subject="s", effect="allow", note="für Alice", by="owner", now=NOW)
    policy.add_rule(peer="bob", subject="t", effect="allow", note="für Bob", by="owner", now=NOW)
    policy.record("requested", peer="alice", task_id="t-1", subject="s", request="meins", now=NOW)
    policy.record("requested", peer="bob", task_id="t-2", subject="t", request="seins", now=NOW)
    view = policy.view_for("alice")
    assert "für Alice" in view and "meins" in view
    assert "für Bob" not in view and "seins" not in view


def test_revoking_an_unknown_rule_says_so(policy):
    with pytest.raises(KeyError):
        policy.revoke("r-nope", by="owner", now=NOW)


# --- the agent.yaml block ---------------------------------------------------------

def test_no_block_means_off(tmp_path):
    assert not parse_requests("x", None, inst_dir=tmp_path, tools_dir="/t",
                              has_approval=True, has_auth=True).enabled


def test_requests_need_an_owner_to_ask_and_a_known_peer(tmp_path):
    with pytest.raises(ValueError, match="approval"):
        parse_requests("x", {"enabled": True}, inst_dir=tmp_path, tools_dir="/t",
                       has_approval=False, has_auth=True)
    with pytest.raises(ValueError, match="auth"):
        parse_requests("x", {"enabled": True}, inst_dir=tmp_path, tools_dir="/t",
                       has_approval=True, has_auth=False)


def test_paths_default_into_the_instance_and_the_execute_command_resolves(tmp_path):
    cfg = parse_requests("x", {"enabled": True, "execute": {"command": ["python3", "${tools_dir}/run.py"]}},
                         inst_dir=tmp_path, tools_dir="/abs/tools", has_approval=True, has_auth=True)
    assert isinstance(cfg, RequestsConfig) and cfg.enabled
    assert cfg.rules_path == tmp_path / "policy" / "rules.yaml"
    assert cfg.ledger_path == tmp_path / "policy" / "ledger.jsonl"
    assert cfg.execute_command == ("python3", "/abs/tools/run.py")


def test_a_broken_execute_command_stops_the_start(tmp_path):
    with pytest.raises(ValueError, match="execute.command"):
        parse_requests("x", {"enabled": True, "execute": {"command": "rm -rf /"}},
                       inst_dir=tmp_path, tools_dir="/t", has_approval=True, has_auth=True)


def test_an_unreadable_rules_file_refuses_writes(policy):
    policy.rules_path.parent.mkdir(parents=True, exist_ok=True)
    policy.rules_path.write_text("rules: [\n", "utf-8")
    from _runtime.policy import PolicyError
    with pytest.raises(PolicyError):
        policy.add_rule(peer="alice", subject="s", effect="allow", by="owner", now=NOW)
    assert policy.rules_path.read_text("utf-8") == "rules: [\n"


def test_rule_writes_are_serialised_by_a_lock(policy):
    # Two writers in a row on separate Policy objects keep both rules.
    other = Policy(policy.rules_path, policy.ledger_path)
    a = policy.add_rule(peer="p", subject="a", effect="allow", by="owner", now=NOW)
    b = other.add_rule(peer="p", subject="b", effect="allow", by="owner", now=NOW)
    assert {r.id for r in policy.rules()} == {a.id, b.id}
