"""Phase 36.1 (test automation, D367, D522 to D525) and phase 36.3 (scaling out, D520 to D528): the runner's logic, the
operations helper's scaling rules, the compose files and the wiring. No database or Docker needed."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
API = REPO / "services" / "api"


def _ops_module(name: str):
    spec = importlib.util.spec_from_file_location(f"ops_{name}", REPO / "services" / "ops" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- the migration
def test_migration_adds_rows_only():
    sql = (API / "migrations" / "sql" / "0045_tests_scaling.sql").read_text()
    assert "CREATE TABLE core.test_runs" in sql and "CREATE TABLE core.test_results" in sql and "CREATE TABLE core.test_fixtures" in sql
    assert "name ~ '^(self_test_|svc-self-test-)'" in sql
    assert "ON CONFLICT (version) DO NOTHING" in sql and "'0.19.0'" in sql
    assert "CREATE TRIGGER" not in sql.upper() and "CREATE FUNCTION" not in sql.upper()   # D248
    v = (API / "migrations" / "versions" / "0045_tests_scaling.py").read_text()
    assert 'revision = "0045_tests_scaling"' in v and 'down_revision = "0044_updates"' in v


# ---------------------------------------------------------------- suites
def test_suites_are_checked():
    from eax.testing import store
    assert store.clean_suites(None) == ["api", "ui", "db", "security"]
    assert store.clean_suites("db, api") == ["api", "db"]
    assert store.clean_suites(["all"]) == ["api", "ui", "db", "security"]
    with pytest.raises(ValueError):
        store.clean_suites(["api", "load"])
    assert store.clean_options("detailed", "user_architect", "models") == ("detailed", "architect", "models")
    for bad in (("fast", "", ""), ("smoke", "nobody", ""), ("smoke", "", "nowhere")):
        with pytest.raises(ValueError):
            store.clean_options(*bad)
    assert store.estimate_minutes("smoke", [])[1] <= 5 and store.short("c08f9f97-2965-4a0b-8c1d-000000000000") == "c08f9f972965"
    t = _ops_module("testruns")
    assert t.suites_of("security") == ["security"] and t.suites_of([]) == ["api", "ui", "db", "security"]
    with pytest.raises(ValueError):
        t.suites_of(["nope"])


# ---------------------------------------------------------------- the API matrix
SPEC = {"security": [{"bearerAuth": []}], "paths": {
    "/api/health": {"get": {"security": []}},
    "/api/v1/models": {"get": {}},
    "/api/v1/models/{model_id}/entities": {"get": {}},
    "/api/v1/models/{model_id}/kpis": {"get": {}},
    "/api/v1/admin/servers": {"put": {}},
    "/api/v1/things/{thing_key}": {"get": {}},
}}


def test_endpoints_and_parameters():
    from eax.testing import api_matrix as m
    eps = m.endpoints(SPEC)
    assert {(e["path"], e["method"], e["public"]) for e in eps} >= {("/api/health", "get", True), ("/api/v1/models", "get", False)}
    assert m.fill("/api/v1/models/{model_id}/entities/{entity_id}", {"model": "M", "entity": "E"}) == "/api/v1/models/M/entities/E"
    assert m.fill("/api/v1/things/{thing_key}", {"model": "M"}) is None


def test_judgements():
    from eax.testing import api_matrix as m
    assert m.judge_anonymous(401, False)[0] == "passed"
    assert m.judge_anonymous(200, False)[0] == "failed"          # open without a token
    assert m.judge_anonymous(200, True)[0] == "passed"           # public
    assert m.judge_anonymous(500, False)[0] == "failed"
    assert m.judge_role(403)[0] == "passed" and m.judge_role(200)[0] == "passed"
    assert m.judge_role(500)[0] == "failed" and m.judge_role(401)[0] == "failed"
    assert m.judge_role(503)[0] == "warning"


def test_the_matrix_finds_what_is_wrong(monkeypatch):
    from eax.testing import api_matrix as m

    def status(path, token):
        if path == "/api/health":
            return 200
        if token is None:
            return 200 if path.endswith("/kpis") else 401         # a hole: kpis without a token
        if path.endswith("/entities") and "OTHER" in path:
            return 200 if token == "t-none" else 403               # a hole: content readable without a role
        if path == "/api/v1/admin/servers":
            return 403
        if path.endswith("/kpis") and token == "t-report":
            return 500                                            # a server error for one role
        return 200

    monkeypatch.setattr(m, "call", lambda base, method, path, token=None, timeout=30: (status(path, token), '{"message": "x"}'))
    got = {}
    m.run("http://x", SPEC, {"no-role": "t-none", "report-viewer": "t-report"}, {"model": "M", "model_id": "M"}, "OTHER",
          lambda name, outcome, detail, ms, request="", response="": got.__setitem__(name, (outcome, request, response)), workers=2)
    assert got["GET /api/health: without a token"][0] == "passed"
    assert got["GET /api/v1/models/{model_id}/kpis: without a token"][0] == "failed"
    roles = got["GET /api/v1/models/{model_id}/kpis: every test role"]
    assert roles[0] == "failed" and "as report-viewer" in roles[1] and roles[2].startswith("500")   # asked and answered
    assert got["GET /api/v1/models/{model_id}/entities: cross-user (no role on the model)"][0] == "failed"
    assert got["GET /api/v1/models/{model_id}/kpis: cross-user (no role on the model)"][0] == "warning"   # not content: look
    assert got["PUT /api/v1/admin/servers: refused without a global role"][0] == "passed"
    assert got["GET /api/v1/things/{thing_key}: skipped"][0] == "skipped"
    only = {}
    m.run("http://x", SPEC, {"no-role": "t-none"}, {"model": "M", "model_id": "M"}, None,
          lambda name, *a, **k: only.__setitem__(name, 1), workers=1, area="administration")
    assert all("/admin/" in n for n in only)                       # one area only
    assert m.HEAVY.search("/api/v1/admin/backups") and not m.HEAVY.search("/api/v1/models")


# ---------------------------------------------------------------- security
def test_headers_and_cookies():
    from eax.testing import security as s
    got = []
    rec = lambda name, outcome, detail, ms: got.append((name, outcome))  # noqa: E731
    s.check_headers({"x-content-type-options": "nosniff", "referrer-policy": "strict-origin-when-cross-origin",
                     "server": "nginx/1.27.2"}, "front door", rec)
    d = dict(got)
    assert d["front door: header x-content-type-options"] == "passed"
    assert d["front door: header strict-transport-security"] == "warning"
    assert d["front door: server version hidden"] == "warning"
    got.clear()
    s.check_cookies(["AUTH_SESSION_ID=a; Path=/; Secure; HttpOnly; SameSite=None", "X=1; Path=/"], "sign-in", rec)
    d = dict(got)
    assert d["sign-in: cookie AUTH_SESSION_ID"] == "passed" and d["sign-in: cookie X"] == "failed"


def test_scan_reports(tmp_path):
    from eax.testing import security as s
    got = {}
    rec = lambda name, outcome, detail, ms: got.__setitem__(name, outcome)  # noqa: E731
    s.read_zap(tmp_path / "zap.json", rec)
    assert got["OWASP ZAP baseline scan"] == "skipped"
    (tmp_path / "zap.json").write_text(json.dumps({"site": [{"alerts": [{"alert": "CSP not set", "riskcode": "2"}]}]}))
    s.read_zap(tmp_path / "zap.json", rec)
    assert got["OWASP ZAP baseline scan"] == "warning"
    (tmp_path / "trivy-api.json").write_text(json.dumps({"Results": [{"Vulnerabilities": [
        {"Severity": "CRITICAL", "PkgName": "openssl", "InstalledVersion": "3.0.1", "VulnerabilityID": "CVE-1", "FixedVersion": "3.0.2"}]}]}))
    (tmp_path / "trivy-web.json").write_text(json.dumps({"Results": []}))
    s.read_trivy(tmp_path, rec)
    assert got["image api (Trivy)"] == "failed" and got["image web (Trivy)"] == "passed"


def test_db_checks_are_queries_that_find_problems():
    from eax.testing import db_checks
    names = [n for n, _sql, _bad in db_checks.CHECKS]
    assert len(names) == len(set(names)) >= 8
    for _n, sql, bad in db_checks.CHECKS:
        assert sql.strip().upper().startswith("SELECT") and bad in ("failed", "warning")


def test_fixtures_are_named_after_their_run_and_purged_by_record_only():
    from eax.testing import fixtures, ui_journeys
    src = (API / "eax/testing/fixtures.py").read_text()
    assert 'f"self_test_{sid}_1"' in src and 'f"self_test_{sid}_2"' in src and 'f"self_test_{sid}_3"' in src
    assert "DISABLE TRIGGER row_versions_no_change" in src and "ENABLE TRIGGER row_versions_no_change" in src
    assert "The history guard did not come back on" in src            # D445: checked before commit
    assert "not this run's" in src                                     # refuses anything not the run's, whatever its name
    assert callable(fixtures.purge)
    js = ui_journeys.journeys({"model": "M", "model_name": "self_test_x_1", "project": "P", "project_name": "self_test_x_3"})
    assert all(j["steps"] and j["role"] for j in js) and any("#/projects/P" in st["route"] for j in js for st in j["steps"])
    assert {j["role"] for j in ui_journeys.journeys({"model": "M"}, "architect")} == {"architect"}


def test_report_and_cli_exist():
    from eax.testing import cli, report
    assert callable(report.to_html) and callable(report.to_xlsx) and "clean" in cli.__doc__ and "fixtures" in cli.__doc__
    assert "selftest_session_blp" in (API / "eax/app.py").read_text()
    assert "fixedToken" in (REPO / "services/web/src/auth.js").read_text()      # the screens sign in with the run's token


def test_sample_screenshot_is_a_png():
    from eax.seed.sample_tests import _png
    png = _png(20, 10)
    assert png.startswith(b"\x89PNG\r\n\x1a\n") and b"IEND" in png


# ---------------------------------------------------------------- scaling rules
def test_scaling_decides_one_step_at_a_time():
    s = _ops_module("scaling")
    rules = {"EAX_SCALE_MODE": "auto", "EAX_SCALE_MIN": 1, "EAX_SCALE_MAX": 4, "EAX_SCALE_USERS_PER_SERVER": 25,
             "EAX_SCALE_CPU_UP": 75, "EAX_SCALE_CPU_DOWN": 25, "EAX_SCALE_MINUTES": 5, "EAX_SCALE_COOLDOWN": 10}
    now = 10_000.0
    hot = [{"t": now - 60 * i, "cpu": 90.0} for i in range(6, -1, -1)]
    cold = [{"t": now - 60 * i, "cpu": 5.0} for i in range(6, -1, -1)]
    mid = [{"t": now - 60 * i, "cpu": 50.0} for i in range(6, -1, -1)]
    assert s.decide(rules, 2, 10, hot, now, 0)[0] == 3                     # busy: one more
    assert s.decide(rules, 4, 10, hot, now, 0)[0] == 4                     # never above the most
    assert s.decide(rules, 3, 10, cold, now, 0)[0] == 2                    # quiet: one fewer
    assert s.decide(rules, 1, 10, cold, now, 0)[0] == 1                    # never below the fewest
    assert s.decide(rules, 2, 100, cold, now, 0)[0] == 3                   # 100 people need 4: up one at a time
    assert s.decide(rules, 2, 10, mid, now, 0) == (2, "no change")
    assert s.decide(rules, 2, 10, hot, now, now - 120)[0] == 2             # within the cool-down
    short = [{"t": now - 60, "cpu": 95.0}, {"t": now, "cpu": 95.0}]
    assert s.decide(rules, 2, 10, short, now, 0)[0] == 2                   # not hot for long enough yet
    assert s.decide({**rules, "EAX_SCALE_MIN": 3}, 2, 0, mid, now, 0)[0] == 3


def test_scaling_settings_are_checked():
    s = _ops_module("scaling")
    s.bind({"_values": lambda lines: {}, "_read_config": lambda: []})
    assert s.settings({})["EAX_SCALE_MODE"] == "fixed"
    assert s.settings({"EAX_SCALE_MAX": "99", "EAX_SCALE_MIN": "0"})["EAX_SCALE_MAX"] == 16
    assert s.check({"EAX_SCALE_MODE": "auto", "EAX_SCALE_MAX": "6"}) == {"EAX_SCALE_MODE": "auto", "EAX_SCALE_MAX": "6"}
    for bad in ({"EAX_SCALE_MODE": "fast"}, {"EAX_SCALE_MAX": "40"}, {"EAX_SECRET": "1"},
                {"EAX_SCALE_MIN": "5", "EAX_SCALE_MAX": "2"}, {"EAX_SCALE_CPU_DOWN": "80", "EAX_SCALE_CPU_UP": "70"}):
        with pytest.raises(ValueError):
            s.check(bad)
    lines = s._set(["EAX_X=1"], "EAX_SCALE_MIN", "2")
    assert lines[-1] == "EAX_SCALE_MIN=2" and any("Scaling" in x for x in lines)
    assert s._set(lines, "EAX_SCALE_MIN", "3").count("EAX_SCALE_MIN=3") == 1


# ---------------------------------------------------------------- compose, scripts and wiring
def _yaml(path: Path):
    import yaml

    class Loader(yaml.SafeLoader):
        pass
    Loader.add_multi_constructor("!", lambda loader, suffix, node: None)   # compose tags such as !reset
    return yaml.load(path.read_text(), Loader=Loader)  # noqa: S506 - a SafeLoader subclass


def test_compose_has_the_runner_and_the_scale_out_files():
    compose = _yaml(REPO / "docker-compose.yml")
    tr = compose["services"]["testrunner"]
    assert tr["profiles"] == ["test"] and tr["build"]["dockerfile"] == "Dockerfile.test"
    assert (API / "Dockerfile.test").read_text().count("playwright install --with-deps chromium") == 1
    proxy = compose["services"]["proxy"]["environment"]
    assert proxy["EAX_API_UPSTREAM"] == "${EAX_API_UPSTREAM:-api:8000}"
    tpl = (REPO / "deploy/proxy/templates/default.conf.template").read_text()
    assert "http://api:8000;" not in tpl and tpl.count("http://${EAX_API_UPSTREAM};") == 3
    scale = REPO / "deploy" / "compose" / "scale"
    names = sorted(p.name.removeprefix("docker-compose.").removesuffix(".yml") for p in scale.glob("docker-compose.*.yml"))
    assert names == ["api-host", "library-elsewhere", "library-host", "primary", "shared-storage", "standby"]
    for p in scale.glob("*.yml"):
        assert isinstance(_yaml(p), dict), p
    standby = _yaml(scale / "docker-compose.standby.yml")["services"]
    assert "wal_level=replica" in standby["db"]["command"] and "db-standby" in standby
    sh = (REPO / "deploy/postgres/standby/standby-entrypoint.sh").read_text()
    assert "pg_basebackup" in sh and "-R" in sh and "eax_replicator" in (REPO / "deploy/postgres/standby/pg_hba.conf").read_text()
    for f in ("eax.ps1", "eax.sh", "eaxcli/core.py"):
        assert "EAX_COMPOSE_EXTRA" in (REPO / f).read_text() and "deploy/compose/scale/docker-compose." in (REPO / f).read_text(), f


def test_commands_and_screens_are_wired():
    for f in ("eax.ps1", "eax.sh", "eaxcli/main.py"):
        text = (REPO / f).read_text()
        assert '"test"' in text or "  test)" in text, f
        assert "standby" in text and "testrunner" in text, f
    ops = (REPO / "services/ops/ops.py").read_text()
    assert "testruns.cli(args)" in ops and "scaling.start()" in ops and 'self.path == "/tests"' in ops
    docker = (REPO / "services/ops/Dockerfile").read_text()
    assert "COPY scaling.py" in docker and "COPY testruns.py" in docker
    assert "mcp_tests" in (API / "eax/mcp_server.py").read_text()
    assert "platform_tests_blp" in (API / "eax/app.py").read_text()
    web = REPO / "services" / "web" / "src"
    assert '["scaling", "Scaling"' in (web / "Admin.jsx").read_text() and '["self-test", "Self-test"' in (web / "Admin.jsx").read_text()
    assert "<LastSelfTest />" in (web / "Heartbeat.jsx").read_text()
    assert "Watch it in this browser" in (web / "TestRuns.jsx").read_text() and "Type DELETE" in (web / "TestRuns.jsx").read_text()
    assert "sample_tests" in (API / "eax/seed/later.py").read_text()


def test_mcp_tool_reads_test_results():
    sys.modules.pop("eax.mcp_tests", None)
    src = (API / "eax/mcp_tests.py").read_text()
    assert "async def test_results(" in src and "_operator()" in src
    assert "may_write" not in src                              # read only: no change through MCP
