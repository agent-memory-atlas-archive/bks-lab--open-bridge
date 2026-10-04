# SPDX-License-Identifier: MIT
"""Tracker adapters of scripts/briefing.py (gitlab, ado, jira, linear) against recorded answers.

No live service is touched: CLI output and HTTP answers come from
scripts/tests/fixtures/briefing/<provider>/.
"""
from __future__ import annotations

import base64
import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "scripts" / "tests" / "fixtures" / "briefing"
sys.dont_write_bytecode = True


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


bf = _load("briefing", ROOT / "scripts" / "briefing.py")

NOW = dt.datetime(2026, 10, 4, 8, 0)
TOKEN = "tok-123"
JIRA_REF = "keychain://example/jira-token"
LINEAR_REF = "keychain://example/linear-key"


class FakeRun:
    def __init__(self, answers: dict | None = None):
        self.answers = answers or {}
        self.calls: list = []

    def __call__(self, argv, timeout=30, cwd=None):
        self.calls.append(list(argv))
        for prefix, answer in self.answers.items():
            if tuple(argv[: len(prefix)]) == prefix:
                if isinstance(answer, Exception):
                    raise answer
                return answer(argv) if callable(answer) else answer
        raise bf.SourceError(f"no recorded answer for {argv[:4]}")


class FakeHttp:
    """Records (method, url, headers, body) and answers with a fixture or an exception."""

    def __init__(self, answer):
        self.answer = answer
        self.calls: list = []

    def __call__(self, method, url, headers=None, body=None, **_):
        self.calls.append((method, url, headers, body))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def fake_secret(ref_ok: str):
    def secret(ref):
        if ref == ref_ok:
            return TOKEN
        raise bf.SourceError(f"secret {ref} not found")
    return secret


def fixture(*parts: str):
    return json.loads((FIX.joinpath(*parts)).read_text(encoding="utf-8"))


def fixture_text(*parts: str) -> str:
    return FIX.joinpath(*parts).read_text(encoding="utf-8")


def make_root(tmp_path: Path, accounts: dict | None = None) -> Path:
    root = tmp_path / "bridge"
    (root / "work" / "inbox").mkdir(parents=True, exist_ok=True)
    (root / "bridge-config.yaml").write_text("{}\n", encoding="utf-8")
    for name, data in (accounts or {}).items():
        path = root / "identity" / "accounts" / f"{name}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return root


def run_section(root: Path, section: dict, **kw) -> dict:
    ctx = bf.Context(root, now=NOW, **kw)
    result = bf.collect(root, {"id": "p", "sections": [section]}, ctx)
    return result["sections"][0]


def by_id(sec: dict) -> dict:
    return {i["id"]: i for i in sec["items"]}


JIRA_ACCOUNT = {"base_url": "https://example.atlassian.net", "email": "alice@example.com", "token_ref": JIRA_REF}
LINEAR_ACCOUNT = {"token_ref": LINEAR_REF}


# ---------------------------------------------------------------- gitlab

GL_SECTION = {"kind": "tracker", "id": "gl", "provider": "gitlab",
              "query": {"repos": ["example-org/acme-app"], "labels": ["bug"], "limit": 20}}


def test_gitlab_normalizes_states_types_and_urls(tmp_path):
    run = FakeRun({("glab", "issue", "list"): fixture_text("gitlab", "issues.json")})
    sec = run_section(make_root(tmp_path), GL_SECTION, run=run)
    assert sec["status"] == "ok" and sec["total"] == 5
    items = by_id(sec)
    assert items["example-org/acme-app#42"]["state"] == "in_progress"
    assert items["example-org/acme-app#42"]["type"] == "bug"
    assert items["example-org/acme-app#42"]["priority"] == "P1"
    assert items["example-org/acme-app#43"]["state"] == "blocked"
    assert items["example-org/acme-app#44"]["state"] == "review"
    assert items["example-org/acme-app#44"]["category"] == "qa"
    assert items["example-org/acme-app#45"]["state"] == "ready"
    assert items["example-org/acme-app#45"]["type"] == "issue"
    done = items["example-org/acme-app#46"]
    assert done["state"] == "done" and done["category"] == "done" and done["raw_state"] == "closed"
    first = items["example-org/acme-app#42"]
    assert first["url"].endswith("/-/issues/42") and first["assignee"] == "alice"
    assert first["assigned_to_me"] is True and first["tracker"] == "gitlab"


def test_gitlab_argv_shape(tmp_path):
    run = FakeRun({("glab", "issue", "list"): "[]"})
    run_section(make_root(tmp_path), GL_SECTION, run=run)
    argv = [c for c in run.calls if c[:3] == ["glab", "issue", "list"]][0]
    assert argv[:3] == ["glab", "issue", "list"]
    assert argv[argv.index("--repo") + 1] == "example-org/acme-app"
    assert argv[argv.index("--assignee") + 1] == "@me"
    assert argv[argv.index("--output") + 1] == "json"
    assert argv[argv.index("--per-page") + 1] == "20"
    assert argv[argv.index("--label") + 1] == "bug"


def test_gitlab_loops_over_repos(tmp_path):
    run = FakeRun({("glab", "issue", "list"): "[]"})
    section = {**GL_SECTION, "query": {"repos": ["example-org/a", "example-org/b"]}}
    run_section(make_root(tmp_path), section, run=run)
    lists = [c for c in run.calls if c[:3] == ["glab", "issue", "list"]]
    assert [c[c.index("--repo") + 1] for c in lists] == ["example-org/a", "example-org/b"]


def test_gitlab_missing_repos_is_error_section(tmp_path):
    section = {"kind": "tracker", "id": "gl", "provider": "gitlab", "query": {}}
    sec = run_section(make_root(tmp_path), section, run=FakeRun())
    assert sec["status"] == "error" and "repos" in sec["reason"]


def test_gitlab_cli_failure_and_bad_json_become_error(tmp_path):
    sec = run_section(make_root(tmp_path), GL_SECTION,
                      run=FakeRun({("glab",): bf.SourceError("glab: not logged in")}))
    assert sec["status"] == "error" and "not logged in" in sec["reason"]
    sec = run_section(make_root(tmp_path), GL_SECTION, run=FakeRun({("glab",): "not json"}))
    assert sec["status"] == "error" and "not JSON" in sec["reason"]


# ---------------------------------------------------------------- ado

ADO_SECTION = {"kind": "tracker", "id": "ado", "provider": "ado",
               "query": {"organization": "https://dev.azure.com/example-org", "project": "Acme"}}


def test_ado_normalizes_states_assignee_and_urls(tmp_path):
    run = FakeRun({("az", "boards", "query"): fixture_text("ado", "query.json")})
    sec = run_section(make_root(tmp_path), ADO_SECTION, run=run)
    assert sec["status"] == "ok" and sec["total"] == 4
    items = by_id(sec)
    bug = items["#1201"]
    assert bug["state"] == "in_progress" and bug["type"] == "bug" and bug["priority"] == "P1"
    assert bug["assignee"] == "Alice Example" and bug["labels"] == ["billing", "urgent"]
    assert bug["url"] == "https://dev.azure.com/example-org/Acme/_workitems/edit/1201"
    assert bug["assigned_to_me"] is True and bug["tracker"] == "ado"
    story = items["#1202"]
    assert story["state"] == "review" and story["category"] == "qa" and story["type"] == "story"
    assert story["assignee"] == "Alice Example" and story["labels"] == []
    assert items["#1203"]["state"] == "new" and items["#1203"]["assignee"] is None
    assert items["#1203"]["priority"] is None
    assert items["#1204"]["state"] == "blocked" and items["#1204"]["type"] == "feature"


def test_ado_argv_default_wiql_and_flags(tmp_path):
    run = FakeRun({("az", "boards", "query"): "[]"})
    run_section(make_root(tmp_path), ADO_SECTION, run=run)
    argv = run.calls[0]
    assert argv[:3] == ["az", "boards", "query"]
    wiql = argv[argv.index("--wiql") + 1]
    assert "@Me" in wiql and "'Closed'" in wiql and "'Removed'" in wiql and "'Done'" in wiql
    assert argv[argv.index("--org") + 1] == "https://dev.azure.com/example-org"
    assert argv[argv.index("--project") + 1] == "Acme"
    assert argv[argv.index("--output") + 1] == "json"


def test_ado_custom_wiql_is_used_and_not_assumed_mine(tmp_path):
    run = FakeRun({("az", "boards", "query"): fixture_text("ado", "query.json")})
    custom = "SELECT [System.Id] FROM WorkItems WHERE [System.State] = 'Ready for Testing'"
    section = {**ADO_SECTION, "query": {**ADO_SECTION["query"], "wiql": custom, "limit": 2}}
    sec = run_section(make_root(tmp_path), section, run=run)
    assert run.calls[0][run.calls[0].index("--wiql") + 1] == custom
    assert sec["total"] == 2
    assert all(i["assigned_to_me"] is False for i in sec["items"])


def test_ado_without_organization_has_no_url_and_failure_is_error(tmp_path):
    run = FakeRun({("az", "boards", "query"): fixture_text("ado", "query.json")})
    section = {"kind": "tracker", "id": "ado", "provider": "ado", "query": {}}
    sec = run_section(make_root(tmp_path), section, run=run)
    assert all(i["url"] is None for i in sec["items"])
    assert "--org" not in run.calls[0]
    sec = run_section(make_root(tmp_path), ADO_SECTION,
                      run=FakeRun({("az",): bf.SourceError("az: please run az login")}))
    assert sec["status"] == "error" and "az login" in sec["reason"]


# ---------------------------------------------------------------- jira

JIRA_SECTION = {"kind": "tracker", "id": "jira", "provider": "jira", "account_ref": "identity/accounts/jira-example.yaml"}


def test_jira_normalizes_and_posts_default_jql(tmp_path):
    root = make_root(tmp_path, {"jira-example": JIRA_ACCOUNT})
    http = FakeHttp(fixture("jira", "search.json"))
    sec = run_section(root, JIRA_SECTION, http=http, secret=fake_secret(JIRA_REF))
    assert sec["status"] == "ok" and sec["total"] == 5
    method, url, headers, body = http.calls[0]
    assert method == "POST" and url == "https://example.atlassian.net/rest/api/3/search/jql"
    assert body["jql"].startswith("assignee = currentUser()") and body["maxResults"] == 50
    assert "status" in body["fields"] and "summary" in body["fields"]
    expected = base64.b64encode(f"alice@example.com:{TOKEN}".encode()).decode()
    assert headers["Authorization"] == f"Basic {expected}"
    items = by_id(sec)
    a = items["ACME-101"]
    assert a["state"] == "in_progress" and a["type"] == "bug" and a["priority"] == "High"
    assert a["url"] == "https://example.atlassian.net/browse/ACME-101"
    assert a["assigned_to_me"] is True and a["tracker"] == "jira" and a["project"] == "ACME"
    assert items["ACME-102"]["state"] == "new" and items["ACME-102"]["type"] == "story"
    assert items["ACME-103"]["state"] == "review" and items["ACME-103"]["category"] == "qa"
    assert items["ACME-104"]["state"] == "review" and items["ACME-104"]["category"] == "qa"
    assert items["ACME-104"]["priority"] is None
    assert items["ACME-105"]["state"] == "blocked" and items["ACME-105"]["assignee"] is None
    assert items["ACME-105"]["type"] == "epic"


def test_jira_custom_jql_and_account_id(tmp_path):
    account = {**JIRA_ACCOUNT, "account_id": "acc-alice"}
    root = make_root(tmp_path, {"jira-example": account})
    http = FakeHttp(fixture("jira", "search.json"))
    section = {**JIRA_SECTION, "query": {"jql": "project = ACME", "limit": 5}}
    sec = run_section(root, section, http=http, secret=fake_secret(JIRA_REF))
    assert http.calls[0][3]["jql"] == "project = ACME" and http.calls[0][3]["maxResults"] == 5
    items = by_id(sec)
    assert items["ACME-101"]["assigned_to_me"] is True
    assert items["ACME-104"]["assigned_to_me"] is False
    assert items["ACME-105"]["assigned_to_me"] is False


def test_jira_bearer_and_api_v2(tmp_path):
    account = {"base_url": "https://jira.example.com", "token_ref": JIRA_REF, "auth": "bearer", "api_version": 2}
    root = make_root(tmp_path, {"jira-example": account})
    http = FakeHttp(fixture("jira", "search.json"))
    sec = run_section(root, JIRA_SECTION, http=http, secret=fake_secret(JIRA_REF))
    assert sec["status"] == "ok"
    method, url, headers, body = http.calls[0]
    assert method == "GET" and url.startswith("https://jira.example.com/rest/api/2/search?jql=")
    assert "currentUser" in url and body is None
    assert headers["Authorization"] == f"Bearer {TOKEN}"


def test_jira_errors_never_leak_the_token(tmp_path):
    root = make_root(tmp_path, {"jira-example": JIRA_ACCOUNT})
    http = FakeHttp(bf.SourceError("HTTP 401 from https://example.atlassian.net/rest/api/3/search/jql"))
    sec = run_section(root, JIRA_SECTION, http=http, secret=fake_secret(JIRA_REF))
    assert sec["status"] == "error" and "401" in sec["reason"]
    assert TOKEN not in sec["reason"]
    assert TOKEN not in json.dumps(sec) and base64.b64encode(f"alice@example.com:{TOKEN}".encode()).decode() not in json.dumps(sec)


def test_jira_success_result_does_not_contain_the_token(tmp_path):
    root = make_root(tmp_path, {"jira-example": JIRA_ACCOUNT})
    ctx = bf.Context(root, now=NOW, http=FakeHttp(fixture("jira", "search.json")), secret=fake_secret(JIRA_REF))
    result = bf.collect(root, {"id": "p", "sections": [JIRA_SECTION]}, ctx)
    assert TOKEN not in json.dumps(result)


def test_jira_missing_account_ref_and_keys(tmp_path):
    root = make_root(tmp_path, {"jira-example": JIRA_ACCOUNT})
    section = {"kind": "tracker", "id": "jira", "provider": "jira"}
    sec = run_section(root, section, http=FakeHttp({}), secret=fake_secret(JIRA_REF))
    assert sec["status"] == "error" and "account_ref" in sec["reason"]
    for key in ("base_url", "token_ref"):
        account = {k: v for k, v in JIRA_ACCOUNT.items() if k != key}
        root = make_root(tmp_path / key, {"jira-example": account})
        sec = run_section(root, JIRA_SECTION, http=FakeHttp({}), secret=fake_secret(JIRA_REF))
        assert sec["status"] == "error" and key in sec["reason"]
    account = {k: v for k, v in JIRA_ACCOUNT.items() if k != "email"}
    root = make_root(tmp_path / "email", {"jira-example": account})
    sec = run_section(root, JIRA_SECTION, http=FakeHttp({}), secret=fake_secret(JIRA_REF))
    assert sec["status"] == "error" and "email" in sec["reason"]


def test_jira_unresolvable_secret_is_error_section(tmp_path):
    root = make_root(tmp_path, {"jira-example": JIRA_ACCOUNT})
    sec = run_section(root, JIRA_SECTION, http=FakeHttp(fixture("jira", "search.json")),
                      secret=fake_secret("keychain://other/ref"))
    assert sec["status"] == "error"


# ---------------------------------------------------------------- linear

LIN_SECTION = {"kind": "tracker", "id": "lin", "provider": "linear", "account_ref": "identity/accounts/linear-example.yaml"}


def test_linear_normalizes_states_and_sends_raw_token(tmp_path):
    root = make_root(tmp_path, {"linear-example": LINEAR_ACCOUNT})
    http = FakeHttp(fixture("linear", "assigned.json"))
    sec = run_section(root, LIN_SECTION, http=http, secret=fake_secret(LINEAR_REF))
    assert sec["status"] == "ok" and sec["total"] == 5
    method, url, headers, body = http.calls[0]
    assert method == "POST" and url == "https://api.linear.app/graphql"
    assert headers["Authorization"] == TOKEN and "Bearer" not in headers["Authorization"]
    assert "assignedIssues(first: 50" in body["query"]
    assert body["variables"]["filter"] == {"state": {"type": {"nin": ["completed", "canceled"]}}}
    items = by_id(sec)
    assert items["ENG-12"]["state"] == "in_progress" and items["ENG-12"]["priority"] == "High"
    assert items["ENG-12"]["labels"] == ["backend"] and items["ENG-12"]["project"] == "Platform"
    assert items["ENG-12"]["assigned_to_me"] is True and items["ENG-12"]["tracker"] == "linear"
    assert items["ENG-13"]["state"] == "ready" and items["ENG-13"]["priority"] is None
    assert items["ENG-13"]["project"] == "ENG"
    assert items["ENG-14"]["state"] == "new"
    assert items["ENG-15"]["state"] == "review" and items["ENG-15"]["category"] == "qa"
    assert items["ENG-16"]["state"] == "new"
    assert items["ENG-12"]["url"] == "https://linear.app/example-org/issue/ENG-12"


def test_linear_done_and_canceled_states():
    mod = bf._providers().get("linear")
    base = {"identifier": "ENG-1", "title": "t", "state": {"name": "Done", "type": "completed"}}
    assert mod.normalize(base, mine=True)["state"] == "done"
    assert mod.normalize(base, mine=True)["category"] == "done"
    canceled = {**base, "state": {"name": "Canceled", "type": "canceled"}}
    assert mod.normalize(canceled, mine=True)["state"] == "removed"


def test_linear_filter_team_and_base_url(tmp_path):
    account = {**LINEAR_ACCOUNT, "base_url": "https://linear.example.com/graphql"}
    root = make_root(tmp_path, {"linear-example": account})
    http = FakeHttp({"data": {"issues": {"nodes": []}}})
    section = {**LIN_SECTION, "query": {"filter": {"priority": {"lte": 2}}, "team": "ENG", "limit": 7}}
    sec = run_section(root, section, http=http, secret=fake_secret(LINEAR_REF))
    assert sec["status"] == "ok" and sec["total"] == 0
    _, url, _, body = http.calls[0]
    assert url == "https://linear.example.com/graphql"
    assert body["variables"]["filter"] == {"priority": {"lte": 2}, "team": {"key": {"eq": "ENG"}}}
    assert "issues(first: 7" in body["query"]


def test_linear_graphql_errors_become_error_without_token(tmp_path):
    root = make_root(tmp_path, {"linear-example": LINEAR_ACCOUNT})
    http = FakeHttp(fixture("linear", "error.json"))
    sec = run_section(root, LIN_SECTION, http=http, secret=fake_secret(LINEAR_REF))
    assert sec["status"] == "error" and "Authentication required" in sec["reason"]
    assert TOKEN not in json.dumps(sec)


def test_linear_transport_error_never_leaks_token(tmp_path):
    root = make_root(tmp_path, {"linear-example": LINEAR_ACCOUNT})
    http = FakeHttp(bf.SourceError("HTTP 500 from https://api.linear.app/graphql"))
    sec = run_section(root, LIN_SECTION, http=http, secret=fake_secret(LINEAR_REF))
    assert sec["status"] == "error" and TOKEN not in json.dumps(sec)


def test_linear_success_result_does_not_contain_the_token(tmp_path):
    root = make_root(tmp_path, {"linear-example": LINEAR_ACCOUNT})
    ctx = bf.Context(root, now=NOW, http=FakeHttp(fixture("linear", "assigned.json")), secret=fake_secret(LINEAR_REF))
    result = bf.collect(root, {"id": "p", "sections": [LIN_SECTION]}, ctx)
    assert TOKEN not in json.dumps(result)


def test_linear_missing_account_ref_and_token_ref(tmp_path):
    root = make_root(tmp_path, {"linear-example": {}})
    section = {"kind": "tracker", "id": "lin", "provider": "linear"}
    sec = run_section(root, section, http=FakeHttp({}), secret=fake_secret(LINEAR_REF))
    assert sec["status"] == "error" and "account_ref" in sec["reason"]
    sec = run_section(root, LIN_SECTION, http=FakeHttp({}), secret=fake_secret(LINEAR_REF))
    assert sec["status"] == "error" and "token_ref" in sec["reason"]


def test_gitlab_marks_mine_by_my_login_not_by_the_query(tmp_path):
    issues = [{"iid": 1, "title": "Bob's", "state": "opened", "assignees": [{"username": "bob"}],
               "labels": [], "web_url": "https://gitlab.example.com/x/1", "updated_at": "2026-10-04T08:00:00Z"},
              {"iid": 2, "title": "Mine", "state": "opened", "assignees": [{"username": "octo"}],
               "labels": [], "web_url": "https://gitlab.example.com/x/2", "updated_at": "2026-10-04T08:00:00Z"}]
    run = FakeRun({("glab", "api", "user"): '{"username": "octo"}',
                   ("glab", "issue", "list"): json.dumps(issues)})
    section = {**GL_SECTION, "query": {"repos": ["example-org/x"], "assignee": "bob"}}
    items = {i["title"]: i["assigned_to_me"] for i in run_section(make_root(tmp_path), section, run=run)["items"]}
    assert items == {"Bob's": False, "Mine": True}
