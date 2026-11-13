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
    assert store.clean_suites(None) == ["api", "ui", "db", "security", "backup"]
    assert store.clean_suites("db, api") == ["api", "db"]
    assert store.clean_suites(["all"]) == ["api", "ui", "db", "security", "backup"]
    with pytest.raises(ValueError):
        store.clean_suites(["api", "load"])
    assert store.clean_options("detailed", "user_architect", "models") == ("detailed", "architect", "models")
    for bad in (("fast", "", ""), ("smoke", "nobody", ""), ("smoke", "", "nowhere")):
        with pytest.raises(ValueError):
            store.clean_options(*bad)
    assert store.estimate_minutes("smoke", [])[1] <= 5 and store.short("c08f9f97-2965-4a0b-8c1d-000000000000") == "c08f9f972965"
    t = _ops_module("testruns")
    assert t.suites_of("security") == ["security"] and t.suites_of([]) == ["api", "ui", "db", "security", "backup"]
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
def test_headers_and_cookies(monkeypatch):
    from eax.testing import security as s
    monkeypatch.setenv("EAX_DEPLOYMENT", "server")
    got = []
    rec = lambda name, outcome, detail, ms: got.append((name, outcome))  # noqa: E731
    s.check_headers({"x-content-type-options": "nosniff", "referrer-policy": "strict-origin-when-cross-origin",
                     "server": "nginx/1.27.2"}, "front door", rec)
    d = dict(got)
    assert d["front door: header x-content-type-options"] == "passed"
    assert d["front door: header strict-transport-security"] == "warning"
    assert d["front door: server version hidden"] == "warning"
    got.clear()
    monkeypatch.setenv("EAX_DEPLOYMENT", "laptop")      # HSTS is off on a laptop by design (D107)
    s.check_headers({"x-content-type-options": "nosniff"}, "front door", rec)
    assert dict(got)["front door: header strict-transport-security"] == "passed"
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
    assert "http://api:8000;" not in tpl and tpl.count("http://${EAX_API_UPSTREAM};") == 6   # and the exact /api/v1/me in each block (D644)
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
    tr = (web / "TestRuns.jsx").read_text()      # two choices only (R2.0.1, D592), and the test data deleted (D593)
    assert '["smoke", "Smoke test"' in tr and '["full", "Full test"' in tr and "Type DELETE" in tr and "Delete all test data" in tr
    assert "sample_tests" in (API / "eax/seed/later.py").read_text()


def test_mcp_tool_reads_test_results():
    sys.modules.pop("eax.mcp_tests", None)
    src = (API / "eax/mcp_tests.py").read_text()
    assert "async def test_results(" in src and "_operator()" in src
    assert "may_write" not in src                              # read only: no change through MCP


# ---------------------------------------------------------------- building the test runner from the page (D570)
def test_build_command_in_every_form():
    main = (REPO / "eaxcli/main.py").read_text()
    assert 'command == "test" and "--build" in rest' in main
    i = main.index('command == "test" and "--build" in rest')
    assert '"--profile", "test", "build", "testrunner"' in main[i:i + 600]
    sh = (REPO / "eax.sh").read_text()
    assert '*" --build "*)' in sh and "compose --profile test build testrunner &&" in sh
    ps = (REPO / "eax.ps1").read_text()
    assert '$RestArgs -contains "--build"' in ps
    helptext = (REPO / "eaxcli/help.txt").read_text()
    # --build still works for scripts but is no longer shown (R2.0.1, D592): the help shows smoke, full and clean
    assert "### test [smoke|full|backup|ui-review|failed [run] [--warnings]|delete <run|all> [--older-than DAYS]|clean]" in helptext and "$ {eax} test full" in helptext and "$ {eax} test clean" in helptext
    sys.path.insert(0, str(REPO))
    from eaxcli import commands as C
    assert C.check_argv(["test", "--build"]) == ["test", "--build"]
    assert C.kind_of_argv(["test", "--build"]) == "run"
    docker = (API / "Dockerfile.test").read_text()
    for step in ("EAX-STEP python", "EAX-STEP chromium", "EAX-STEP scanners", "EAX-STEP code"):
        assert step in docker


def test_build_steps_follow_the_log():
    t = _ops_module("testruns")
    assert [s["state"] for s in t.build_steps("")] == ["waiting"] * 5
    log = "#1 [internal] load metadata for docker.io/library/python:3.12-slim\n#5 [3/6] RUN echo \"EAX-STEP python: x\"\n"
    st = {s["key"]: s["state"] for s in t.build_steps(log)}
    assert st == {"base": "done", "python": "running", "chromium": "waiting", "scanners": "waiting", "code": "waiting"}
    log += "#6 EAX-STEP chromium: y\nERROR: failed to solve: no space left on device\n"
    st = {s["key"]: s["state"] for s in t.build_steps(log, finished=True, ok=False)}
    assert st["python"] == "done" and st["chromium"] == "failed" and st["scanners"] == "waiting"
    assert "no space left" in t._reason(log)
    assert all(s["state"] == "done" for s in t.build_steps(log, finished=True, ok=True))


def test_auto_build_setting_is_kept_in_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("EAX_PERSIST_DIR", str(tmp_path))
    sys.path.insert(0, str(REPO))
    t = _ops_module("testruns")
    assert t.auto_build("laptop") is True and t.auto_build("server") is True and t.auto_build("aws") is True   # on everywhere (D584)
    t.set_auto_build(True, "it")
    data = json.loads((tmp_path / "settings.json").read_text())
    assert data["testrunner_auto_build"] is True and data["testrunner_auto_build_by"] == "it"
    assert t.auto_build("laptop") is True
    t.set_auto_build(False, "it")
    assert t.auto_build("server") is False
    assert (tmp_path / "settings.json.bak").exists()        # written atomically, the last good copy kept


def test_build_is_wired_through_the_helper_and_the_api():
    ops = (REPO / "services/ops/ops.py").read_text()
    assert '"/tests/build"' in ops and '"/tests/settings"' in ops and 'startswith("/tests/build/")' in ops
    assert "testruns.auto_build_loop" in ops
    t = (REPO / "services/ops/testruns.py").read_text()
    assert 'cc._launch(["test", "--build"]' in t and "start(then)" in t
    api = (API / "eax/api/platform_tests.py").read_text()
    for route in ('@blp.route("/tests/build")', '@blp.route("/tests/build/<string:build_id>")', '@blp.route("/tests/settings")'):
        assert route in api
    assert "build_first" in api and '"/tests/build", {"by": g.user.username, "then": body}' in api
    web = (REPO / "services/web/src/TestRuns.jsx").read_text()
    for s in ("Rebuild the test runner", "Retry", "Build it automatically after each start or update", "Advanced: the test runner",
              "/api/v1/admin/tests/build", "/api/v1/admin/tests/settings"):
        assert s in web, s
    # nothing to build by hand (D584): a run from the page always prepares the runner first; no "Build, then run" choice
    assert 'data.get("build_first", True) is not False' in api and "build_first: notBuilt" not in web and "Build, then run" not in web



def test_the_runner_gets_the_test_data_when_the_helper_starts_it():
    """R2.0.1: a run started by the operations helper (the page and eax test) had no test data folder, and the journeys'
    file lookup broke the whole run ("ERROR: 4"); the helper now mounts testbench/data at /testdata, and a missing folder
    only makes the upload steps say so."""
    ops = (REPO / "services/ops/testruns.py").read_text()
    assert '"EAX_TEST_DATA=/testdata"' in ops and '{test_data_folder(work)}:/testdata:ro' in ops
    # beside work/, in the host's own spelling (the laptop's full run: a Windows source C:\\...\\work had become
    # "...\\work/testbench/data", an empty folder)
    src = (REPO / "services/ops/testruns.py").read_text()
    ns: dict = {"re": __import__("re")}
    start = src.index("def test_data_folder(")
    exec(src[start:src.index("\ndef ", start + 10)], ns)   # noqa: S102 - the one function, from the repository
    f = ns["test_data_folder"]
    assert f(r"C:\Users\me\EA\work") == r"C:\Users\me\EA\testbench\data"
    assert f("/srv/eax/work/") == "/srv/eax/testbench/data"
    assert f("/run/desktop/mnt/host/c/Users/me/EA/work") == "/run/desktop/mnt/host/c/Users/me/EA/testbench/data"
    from eax.testing import ui_flows
    assert ui_flows._with_data({"upload": "input", "data": "no/such/file.xlsx"}) == {"upload": "input", "data": "no/such/file.xlsx"}


def test_a_run_does_not_depend_on_the_sample_data():
    """Owner, 12 Nov 2026: "Smoke test should not depend upon sample data ... Neither is critical for function of the
    app": a run makes its own models, project and accounts, and neither waits for nor checks the sample data or the
    industry packs (the work after the start, operations.startup_parts)."""
    here = Path(__file__).resolve().parents[1] / "eax" / "testing"
    for f in here.glob("*.py"):
        src = f.read_text(encoding="utf-8")
        assert "startup_parts" not in src and "wait_for_startup" not in src, f.name
