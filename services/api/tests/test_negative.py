"""Negative tests for every endpoint (R3.9): what is sent, where, and how the answers are judged."""

from __future__ import annotations

import json
from types import SimpleNamespace

from eax.testing import negative, run
from eax.testing.api_matrix import NOTHING

JSON_BODY = {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/NameIn"}}}}
LIST_BODY = {"content": {"application/json": {"schema": {"type": "array", "items": {"type": "string"}}}}}
SPEC = {
    "components": {"schemas": {"NameIn": {"type": "object", "properties": {"name": {"type": "string"}}}}},
    "paths": {
        "/api/v1/models": {"get": {}, "post": {"requestBody": JSON_BODY}},
        "/api/v1/models/{model_id}": {"get": {}, "patch": {"requestBody": JSON_BODY}, "delete": {}},
        "/api/v1/models/{model_id}/order": {"put": {"requestBody": LIST_BODY}},
        "/api/v1/admin/backups/run": {"post": {}},                       # no body: acts without reading one
        "/api/v1/uploads": {"post": {"requestBody": {"content": {"multipart/form-data": {}}}}},
        "/api/v1/things/{thing_id}": {"get": {}, "post": {"requestBody": JSON_BODY}},
    },
}
IDS = {"model": "test-model-guid"}


def _jobs():
    return negative.checks(SPEC, IDS)


def test_judge_refusals_pass():
    for status in (400, 401, 403, 404, 405, 409, 413, 415, 422):
        assert negative.judge(status, "bad JSON")[0] == "passed"


def test_judge_server_error_fails():
    out, detail = negative.judge(500, "bad JSON")
    assert out == "failed" and "500" in detail


def test_judge_success_on_bad_input_fails():
    assert negative.judge(200, "not an object")[0] == "failed"
    assert negative.judge(201, "unknown id")[0] == "failed"


def test_judge_long_name_accepted_is_a_warning():
    assert negative.judge(200, "too long")[0] == "warning"


def test_sql_text_is_kept_as_text_or_refused_never_a_server_error():
    assert negative.judge(200, "SQL text") == ("passed", "kept as text (200)")
    assert negative.judge(422, "SQL text")[0] == "passed" and negative.judge(500, "SQL text")[0] == "failed"
    jobs = [(k, p, b) for k, _m, p, b, _d in _jobs() if k == "SQL text"]
    assert jobs and all("test-model-guid" in p for _k, p, _b in jobs)          # only inside the run's own test data
    assert all(json.loads(b)["name"] == negative.SQL_TEXT for _k, _p, b in jobs)


def test_judge_no_answer_is_a_warning():
    assert negative.judge(599, "bad JSON")[0] == "warning"


def test_unknown_path_replaces_the_last_parameter():
    p = negative.unknown_path("/api/v1/models/{model_id}/elements/{element_id}", IDS)
    assert p == f"/api/v1/models/test-model-guid/elements/{negative.UNKNOWN_GUID}"


def test_unknown_path_int_and_none():
    assert negative.unknown_path("/api/v1/runs/{int:run_id}", {}) == "/api/v1/runs/999999999"
    assert negative.unknown_path("/api/v1/models", IDS) is None


def test_unknown_path_none_when_other_ids_are_missing():
    assert negative.unknown_path("/api/v1/x/{a_id}/y/{b_id}", {}) is None


def test_no_write_to_an_endpoint_without_a_json_body():
    paths = {(m, d) for _, m, _, _, d in _jobs()}
    assert ("post", "/api/v1/admin/backups/run") not in paths
    assert ("post", "/api/v1/uploads") not in paths


def test_deletes_are_never_sent():
    assert all(m != "delete" for _, m, _, _, _ in _jobs())


def test_writes_only_into_test_data_or_nothing():
    for _kind, m, path, _, _ in _jobs():
        if m in negative.WRITES and "/models/" in path:
            assert "test-model-guid" in path or NOTHING in path, path
    things = [p for _, m, p, _, d in _jobs() if d == "/api/v1/things/{thing_id}" and m == "post"]
    assert things and all(NOTHING in p for p in things)


def test_a_list_endpoint_is_not_sent_a_list():
    kinds = {k for k, m, _, _, d in _jobs() if d == "/api/v1/models/{model_id}/order"}
    assert "bad JSON" in kinds and "not an object" not in kinds


def test_long_name_only_inside_test_data():
    long = [(p, d) for k, _, p, _, d in _jobs() if k == "too long"]
    assert ("/api/v1/models/test-model-guid", "/api/v1/models/{model_id}") in long
    assert all(d != "/api/v1/models" for _, d in long)            # a create could keep it: never sent
    assert all(d != "/api/v1/things/{thing_id}" for _, d in long)  # no test data for it


def test_bodies_are_really_bad():
    for kind, _, _, body, _ in _jobs():
        if kind == "bad JSON":
            try:
                json.loads(body)
                raise AssertionError("bad JSON parsed")
            except ValueError:
                pass
        if kind == "not an object":
            assert isinstance(json.loads(body), list)
        if kind == "too long":
            assert len(json.loads(body)["name"]) == 100_000


def test_reads_with_unknown_ids():
    reads = [(p, d) for k, m, p, _, d in _jobs() if k == "unknown id"]
    assert (f"/api/v1/models/{negative.UNKNOWN_GUID}", "/api/v1/models/{model_id}") in reads
    assert all(m == "get" for k, m, *_ in _jobs() if k == "unknown id")


def test_run_counts_and_records_by_described_path():
    seen, recorded = [], []

    def sender(base, method, path, token, body):
        seen.append((method, path, token))
        return (500, "boom") if path.endswith("/order") else (422, "")

    def record(name, outcome, detail, ms, **kw):
        recorded.append((name, outcome, kw))

    counts = negative.run("http://api", SPEC, "tok", IDS, record, workers=2, sender=sender)
    assert all(t == "tok" for *_, t in seen)
    assert counts["bad JSON"]["failed"] == 1
    assert sum(sum(v.values()) for v in counts.values()) == len(recorded) == len(_jobs())
    bad = [x for x in recorded if x[1] == "failed"]
    assert bad[0][0] == "negative: bad JSON: PUT /api/v1/models/{model_id}/order"
    assert "500" in bad[0][2]["response"] and bad[0][2]["request"]
    ok = [x for x in recorded if x[1] == "passed"]
    assert ok and ok[0][2]["request"] == ""


def test_send_reports_no_answer_as_599(monkeypatch):
    import urllib.request

    def boom(*a, **k):
        raise OSError("refused")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    status, text = negative.send("http://127.0.0.1:1", "post", "/api/v1/models", "t", b"{")
    assert status == 599 and "refused" in text


class _R:
    def __init__(self, tmp):
        self.dir, self.counts, self.logs, self.rec = tmp, {}, [], []

    def log(self, m):
        self.logs.append(m)

    def recorder(self, suite):
        return lambda *a, **k: self.rec.append(a)


def test_run_wiring_counts_and_file(tmp_path):
    r = _R(tmp_path)
    got = {}

    def runner(api, spec, token, ids, record):
        got.update(spec=spec, token=token)
        return {"bad JSON": {"passed": 3, "failed": 1, "warning": 0}}
    out = run.negative_tests(r, SPEC, {"architect": "a", "super-admin": "s"}, IDS, area=None, runner=runner)
    assert got["token"] == "s" and out["bad JSON"]["failed"] == 1
    assert r.counts["negative bad JSON"] == 4
    assert json.loads((tmp_path / "negative.json").read_text())["bad JSON"]["passed"] == 3


def test_run_wiring_area_filters_paths(tmp_path, monkeypatch):
    r = _R(tmp_path)
    got = {}
    monkeypatch.setattr(run.api_matrix, "in_area", lambda p, a: "/admin/" in p)
    run.negative_tests(r, SPEC, {"super-admin": "s"}, IDS, area="admin",
                       runner=lambda api, spec, *a: got.update(spec=spec) or {})
    assert list(got["spec"]["paths"]) == ["/api/v1/admin/backups/run"]


def test_run_wiring_no_token_skips(tmp_path):
    r = _R(tmp_path)
    assert run.negative_tests(r, SPEC, {}, IDS, runner=lambda *a: SimpleNamespace()) == {}
    assert r.rec[0][1] == "skipped"
