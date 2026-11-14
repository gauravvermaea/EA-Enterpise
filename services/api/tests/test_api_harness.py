"""R3.16 (D662): the API test harness: every endpoint listed with its form, one call as yourself or a test role, reads
anywhere and writes only into test data (owner, 13 Nov 2026, 21:37), saved cases checked and run (also by the
self-test), and `eax test api` in every form of eax."""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path

import pytest

from eax import api_harness as ah
from eax.metamodel_edit import EditError

REPO = Path(__file__).resolve().parents[3]
M = "11111111-2222-3333-4444-555555555555"
REAL = "99999999-2222-3333-4444-555555555555"

SPEC = {"paths": {
    "/api/v1/models/{model_id}/entities": {
        "get": {"summary": "The model's entities", "parameters": [{"name": "type", "in": "query"}]},
        "post": {"summary": "Add one", "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/E"}}}}}},
    "/api/v1/models": {"get": {"summary": "Models"}}},
    "components": {"schemas": {"E": {"type": "object", "properties": {"name": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}}}}}}


def test_every_endpoint_is_listed_with_its_form():
    eps = {(e["method"], e["path"]): e for e in ah.endpoints(SPEC)}
    post = eps[("post", "/api/v1/models/{model_id}/entities")]
    assert post["writes"] and post["example"] == {"name": "", "tags": [""]}
    get = eps[("get", "/api/v1/models/{model_id}/entities")]
    assert not get["writes"] and {"name": "type", "in": "query", "required": False} in get["params"]
    assert {"name": "model_id", "in": "path", "required": True} in get["params"]


def test_reads_go_anywhere_and_writes_only_into_test_data():
    test_ids = {M}
    assert ah.may_call("get", f"/api/v1/models/{REAL}/entities", test_ids) == ""
    assert ah.may_call("post", f"/api/v1/models/{M}/entities", test_ids) == ""
    assert "is not test data" in ah.may_call("post", f"/api/v1/models/{REAL}/entities", test_ids)
    assert "names no test model or project" in ah.may_call("post", "/api/v1/models", test_ids)
    assert "is not test data" in ah.may_call("delete", f"/api/v1/projects/{M}/links/{REAL}", test_ids)


class _Resp(io.BytesIO):
    def __init__(self, status, body, headers=None):
        super().__init__(body.encode())
        self.status, self.headers = status, headers or {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_a_call_goes_through_the_api_with_the_roles_own_token():
    seen = []

    def http(req, timeout=120):
        seen.append((req.get_method(), req.full_url, req.headers.get("Authorization")))
        return _Resp(200, json.dumps({"items": [{"name": "A"}]}))
    out = ah.call("get", f"/api/v1/models/{M}/entities", "TOKEN-A", query={"type": "Capability"}, test_ids=set(),
                  as_who="architect", base="http://api:8000", http=http)
    assert out["status"] == 200 and out["json"]["items"][0]["name"] == "A"
    assert seen[0][0] == "GET" and seen[0][1].endswith(f"/api/v1/models/{M}/entities?type=Capability") and seen[0][2] == "Bearer TOKEN-A"
    assert out["curl"].startswith("curl -sk -X GET") and "token of architect" in out["curl"]

    def refused(req, timeout=120):
        raise urllib.error.HTTPError(req.full_url, 403, "no", {}, io.BytesIO(b'{"message": "no role"}'))
    assert ah.call("get", "/api/v1/models", "T", test_ids=set(), base="http://x", http=refused)["status"] == 403
    with pytest.raises(EditError) as e:                                       # refused before it is sent
        ah.call("post", f"/api/v1/models/{REAL}/entities", "T", body={}, test_ids={M}, base="http://x",
                http=lambda *a, **k: pytest.fail("sent"))
    assert e.value.status == 403
    with pytest.raises(EditError):
        ah.call("get", "/api/v1/models/{model_id}", "T", test_ids=set(), base="http://x", http=http)   # not filled in


def test_a_case_checks_the_status_and_fields():
    answer = {"status": 200, "ms": 12, "json": {"model": {"name": "self_test_x_1"}, "items": [{"id": 3}]}}
    assert ah.check({"expect_status": 200, "expect_fields": {"model.name": "self_test_x_1", "items.0.id": 3}}, answer)[0]
    ok, why = ah.check({"expect_status": 201, "expect_fields": {"model.name": "other"}}, answer)
    assert not ok and "status 200, expected 201" in why and 'model.name is "self_test_x_1", expected "other"' in why


def test_cases_run_in_the_test_data_as_their_role():
    calls = []

    def http(req, timeout=120):
        calls.append((req.full_url, req.headers.get("Authorization")))
        return _Resp(200, "{}")
    rows = [{"id": 1, "name": "list", "method": "get", "path": "/api/v1/models/{model}/entities", "as_role": "architect",
             "expect_status": 200},
            {"id": 2, "name": "write elsewhere", "method": "post", "path": f"/api/v1/models/{REAL}/entities", "as_role": "architect"}]
    out = ah.run_cases(rows, {"architect": "TA", "super-admin": "TS"}, {"model": M}, {M}, base="http://api", http=http)
    assert out[0]["passed"] and out[0]["path"] == f"/api/v1/models/{M}/entities" and calls[0][1] == "Bearer TA"
    assert not out[1]["passed"] and "is not test data" in out[1]["detail"] and len(calls) == 1


def test_wired_in_the_api_the_page_the_self_test_and_every_form_of_eax():
    app = (REPO / "services/api/eax/app.py").read_text()
    assert "from .api.harness import blp as harness_blp" in app
    api = (REPO / "services/api/eax/api/harness.py").read_text()
    for route in ("/endpoints", "/sessions", "/sessions/<int:session_id>/end", "/call", "/cases", "/cases/<int:case_id>", "/cases/run"):
        assert f'@blp.route("{route}")' in api, route
    assert api.count('@require_auth("system.operate")') == 8
    sql = (REPO / "services/api/migrations/sql/0069_api_cases.sql").read_text()
    assert "CREATE TABLE IF NOT EXISTS tests.api_cases" in sql and "FUNCTION" not in sql.upper()
    run = (REPO / "services/api/eax/testing/run.py").read_text()
    assert "saved_cases(r, tokens, ids)" in run
    web = (REPO / "services/web/src/TestRuns.jsx").read_text()
    assert '["harness", "API harness"]' in web and "<ApiHarness />" in web
    for f, needle in (("eax.ps1", '"eax.testing.cli", "api"'), ("eax.sh", "eax.testing.cli api"),
                      ("eaxcli/main.py", '"eax.testing.cli", "api"'), ("eaxcli/help.txt", "  api     one call through the API test harness")):
        assert needle in (REPO / f).read_text(), f


def test_eax_test_api_says_how_to_use_it(capsys):
    from eax.testing import cli
    assert cli.api_call(["GET"]) == 2 and "Usage: eax test api" in capsys.readouterr().out
    assert cli.api_call(["FETCH", "/api/v1/models"]) == 2
    assert cli.api_call(["POST", "/api/v1/x", "--body", "{not json"]) == 2 and "not JSON" in capsys.readouterr().out
