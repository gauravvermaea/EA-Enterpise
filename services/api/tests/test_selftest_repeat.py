"""R2.36 (D605; owner, 12 Nov 2026: "run last failed tests only"): run the failed ones again. A repeat runs only the
checks that failed in an earlier run, records only those, shows each then and now, and marks the earlier run followed
up when all pass. From Self-test > History, the API and `eax test failed [run] [--warnings]`. No database or Docker."""

from __future__ import annotations

import contextlib
import importlib.util
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
API = REPO / "services" / "api"
OLD = {"model": "11111111-1111-1111-1111-111111111111", "project": "22222222-2222-2222-2222-222222222222",
       "sid": "aaaaaaaaaaaa"}
NEW = {"model": "33333333-3333-3333-3333-333333333333", "project": "44444444-4444-4444-4444-444444444444",
       "sid": "bbbbbbbbbbbb"}


def _ops():
    spec = importlib.util.spec_from_file_location("ops_testruns_r236", REPO / "services" / "ops" / "testruns.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_page_of_the_runs_own_model_is_the_same_check_in_the_repeat():
    from eax.testing import repeat
    old = f"page: #/metamodel/{OLD['model']}/graph"
    c = repeat.canon(old, OLD)
    assert c == "page: #/metamodel/{model}/graph"
    assert repeat.fill(c, NEW) == f"page: #/metamodel/{NEW['model']}/graph"
    assert repeat.canon(repeat.fill(c, NEW), NEW) == c
    assert repeat.fill("page: #/entity/{id}", NEW) is None           # an id the new run has not got: not repeated
    assert repeat.canon(f"journey: make self_test_{OLD['sid']}_1", OLD) == "journey: make self_test_{sid}_1"


def test_the_plan_runs_each_suite_only_as_far_as_its_failures_need():
    from eax.testing import repeat
    rows = [{"suite": "api", "name": "GET /api/v1/models: every test role", "outcome": "failed"},
            {"suite": "api", "name": "write imports: undo the load", "outcome": "failed"},
            {"suite": "ui", "name": f"page: #/project/{OLD['project']}", "outcome": "failed"},
            {"suite": "ui", "name": "journey: a project and its tasks as architect", "outcome": "failed"},
            {"suite": "db", "name": "every table has a primary key", "outcome": "failed"},
            {"suite": "security", "name": "front door: header Strict-Transport-Security", "outcome": "failed"},
            {"suite": "security", "name": "image eaexplorer/backup:1.0.0 (Trivy)", "outcome": "failed"}]
    p = repeat.plan(rows, OLD)
    assert p["suites"] == ["api", "db", "security", "ui"]
    assert p["api"] == {"GET /api/v1/models: every test role"} and p["writes"] == {"write imports: undo the load"}
    assert p["routes"] == ["#/project/{project}"] and p["journeys"] == {"journey: a project and its tasks as architect"}
    assert p["db"] and p["front_door"] and not p["zap"]
    assert repeat.scans(p) == {"zap": False, "images": ["eaexplorer/backup:1.0.0"]}       # Trivy on that image only
    assert ("ui", "page: #/project/{project}") in p["keys"]


def test_then_and_now_and_not_repeated():
    from eax.testing import repeat
    earlier = [{"suite": "ui", "name": f"page: #/metamodel/{OLD['model']}", "outcome": "failed"},
               {"suite": "api", "name": "GET /api/v1/x: every test role", "outcome": "failed"},
               {"suite": "db", "name": "gone", "outcome": "warning"}]
    now = [("ui", f"page: #/metamodel/{NEW['model']}", "passed"), ("api", "GET /api/v1/x: every test role", "failed"),
           ("api", "GET /api/v1/x: every test role", "passed")]
    got = repeat.then_and_now(earlier, OLD, now, NEW)
    assert [(c["then"], c["now"]) for c in got] == [("failed", "passed"), ("failed", "failed"), ("warning", "not repeated")]


def test_the_command_line_of_a_repeat():
    from eax.testing import store
    assert store.command_line({"repeat_of": 12, "level": "detailed", "suites": ["ui"]}) == ".\\eax test failed 12"
    assert store.command_line({"repeat_of": 3, "repeat_warnings": True, "pages_only": True}, "./eax.sh") == \
        "./eax.sh test failed 3 --warnings"
    assert store.command_line({"level": "smoke", "suites": []}) == ".\\eax test --smoke"


def test_the_matrix_runs_only_the_named_checks(monkeypatch):
    from eax.testing import api_matrix as m
    spec = {"paths": {"/api/v1/models": {"get": {}}, "/api/v1/projects": {"get": {}}, "/api/health": {"get": {"security": []}}}}
    asked = []
    monkeypatch.setattr(m, "call", lambda base, method, path, token=None, timeout=60, size=1500: (asked.append(path), (200, "{}"))[1])
    got = {}
    m.run("http://x", spec, {"architect": "t", "it-admin": "u"}, {}, None, lambda name, *a, **k: got.__setitem__(name, a[0]),
          workers=1, only={"GET /api/v1/models: every test role"})
    assert list(got) == ["GET /api/v1/models: every test role"] and asked == ["/api/v1/models"] * 2


def test_writes_run_up_to_the_last_failed_one(monkeypatch):
    from eax.testing import api_writes as w
    writes = [dict(area="a", what="one", method="post", path="/1", who="super-admin", ok={200}),
              dict(area="b", what="two", method="post", path="/2", who="super-admin", ok={200}),
              dict(area="c", what="three", method="post", path="/3", who="super-admin", ok={200})]
    monkeypatch.setattr(w, "plan", lambda ids, sid: writes)
    asked = []
    monkeypatch.setattr(w, "call", lambda base, method, path, token, body=None: (asked.append(path), (200, {}))[1])
    names = []
    w.run("http://x", {"super-admin": "t"}, {}, lambda name, *a, **k: names.append(name), only={"write b: two"})
    assert asked == ["/1", "/2"] and names == ["write a: one", "write b: two"]   # "three" not run; the runner records "two" only


class _Page:
    def __init__(self):
        self.opened = []

    def on(self, *a):
        pass

    def evaluate(self, js, arg=None):
        if arg is not None:
            self.opened.append(arg)
            return None
        return {"head": "A page", "links": ["#/somewhere-else"], "notFound": False} if "links" in js or "innerText" in js else "ok"

    def wait_for_selector(self, *a, **k):
        pass

    def wait_for_timeout(self, *a):
        pass

    def wait_for_load_state(self, *a, **k):
        pass

    keyboard = types.SimpleNamespace(press=lambda *a: None)


def test_the_failed_pages_open_again_without_a_crawl(monkeypatch):
    from eax.testing import ui_pages
    monkeypatch.setattr(ui_pages, "judge", lambda found, errors, help_state: ("passed", "ok"))
    page, loaded, got = _Page(), [], []
    ui_pages.sweep(page, loaded.append, NEW, lambda name, *a, **k: got.append(name), routes=["#/models", "#/projects"])
    assert got == ["page: #/models", "page: #/projects"]          # no skipped routes listed, no links followed


def test_only_the_failed_journeys_run_again(monkeypatch, tmp_path):
    from eax.testing import ui_flows, ui_journeys, ui_pages

    class Ctx:
        def new_page(self):
            return types.SimpleNamespace(on=lambda *a: None, video=None)

        def close(self):
            pass
    browser = types.SimpleNamespace(version="1", new_context=lambda **k: Ctx(), close=lambda: None)
    pw = types.SimpleNamespace(chromium=types.SimpleNamespace(launch=lambda **k: browser))
    fake = types.ModuleType("playwright.sync_api")
    fake.sync_playwright = lambda: contextlib.nullcontext(pw)
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake)
    monkeypatch.setattr(ui_flows, "journeys", lambda ids, role="", only=None, smoke=False: [{"name": "a"}, {"name": "b as x"}])
    ran, swept = [], []
    monkeypatch.setattr(ui_flows, "run", lambda factory, js, rec: (ran.extend(j["name"] for j in js), {"journeys": len(js)})[1])
    monkeypatch.setattr(ui_pages, "sweep", lambda *a, **k: (swept.append(k.get("routes")), {"pages": 0})[1])
    ui_journeys.run_all({}, "t", tmp_path, lambda *a, **k: None, names={"journey: b as x"}, routes=[])
    assert ran == ["b as x"] and swept == []                        # no pages failed: no page opened
    ran.clear()
    ui_journeys.run_all({}, "t", tmp_path, lambda *a, **k: None, names=set(), routes=["#/models"])
    assert ran == [] and swept == [["#/models"]]


def test_the_runner_records_only_the_repeated_checks(monkeypatch):
    from eax.testing import run, store
    saved = []
    monkeypatch.setattr(store, "add_result", lambda conn, rid, suite, name, *a: saved.append((suite, name)))
    r = run.Run.__new__(run.Run)
    r.engine = types.SimpleNamespace(begin=lambda: contextlib.nullcontext(None))
    r.id, r.left_out, r.ids = 1, 0, NEW
    r.only = {("ui", "page: #/metamodel/{model}")}
    rec = r.recorder("ui")
    rec(f"page: #/metamodel/{NEW['model']}", "passed")
    rec("page: #/models", "passed")
    assert saved == [("ui", f"page: #/metamodel/{NEW['model']}")] and r.left_out == 1


def test_eax_test_failed_starts_a_repeat(monkeypatch, capsys):
    ops = _ops()
    seen = {}
    monkeypatch.setattr(ops, "run_sequence", lambda *a, **k: (seen.update(k), {"run_id": 9, "folder": "f", "code": 0})[1])
    assert ops.cli(["failed", "12", "--warnings", "--version", "1.0.0"]) == 0
    assert seen["repeat"] == 12 and seen["warnings"] is True
    assert ops.cli(["failed", "--version", "1.0.0"]) == 0 and seen["repeat"] == 0 and seen["warnings"] is False   # the last run
    monkeypatch.setattr(ops, "run_sequence", lambda *a, **k: {"run_id": 0, "folder": "f", "code": 0})
    assert ops.cli(["failed"]) == 0                                  # nothing to repeat: said by the runner, no run
    assert ops.cli(["failed", "x"]) == 2 and "Usage: eax test failed" in capsys.readouterr().out


def test_the_helper_passes_the_repeat_and_scans_only_what_failed(monkeypatch, tmp_path):
    ops = _ops()
    monkeypatch.setattr(ops, "WORK", str(tmp_path))
    ops.H.update(project=lambda: "eax", docker=lambda *a, **k: "",
                 containers=lambda: [{"image": "eaexplorer/backup:1.0.0"}, {"image": "eaexplorer/api:1.0.0"}])
    monkeypatch.setattr(ops, "_api_container", lambda: {"Config": {"Image": "eaexplorer/api:1.0.0"}})
    monkeypatch.setattr(ops, "image_present", lambda image: True)
    monkeypatch.setattr(ops, "host_work", lambda: str(tmp_path))
    cmds, scanned, collected = [], [], []

    def start_runner(info, name, folder, cmd):
        cmds.append(cmd)
        (tmp_path / "tests" / folder / "scans.json").write_text('{"zap": false, "images": ["eaexplorer/backup:1.0.0"]}')
        return "cid"
    monkeypatch.setattr(ops, "_start_runner", start_runner)
    monkeypatch.setattr(ops, "_wait", lambda cid, follow=None: (0, "RUN_ID=5\nSCANS_NEXT\n"))
    monkeypatch.setattr(ops, "_zap", lambda *a: scanned.append("zap"))
    monkeypatch.setattr(ops, "_trivy", lambda hostdir, images, say: scanned.extend(images))
    monkeypatch.setattr(ops, "_collect", lambda *a, **k: (collected.append(a[3]), 0)[1])
    out = ops.run_sequence("detailed", ["security"], repeat=4, warnings=True)
    assert out["code"] == 0 and cmds[0][-3:] == ["--repeat", "4", "--warnings"]
    assert scanned == ["eaexplorer/backup:1.0.0"] and collected == [5]          # no ZAP; Trivy on the failed image only
    scanned.clear()
    monkeypatch.setattr(ops, "_wait", lambda cid, follow=None: (0, "RUN_ID=6\n"))   # nothing for the scanners: closed already
    ops.run_sequence("detailed", ["security"], repeat=4)
    assert scanned == []


def test_wired_everywhere():
    sql = (API / "migrations" / "sql" / "0051_selftest_repeat.sql").read_text()
    assert "repeat_of" in sql and "followed_up_by" in sql and "fixture_ids" in sql
    assert "CREATE TRIGGER" not in sql.upper() and "CREATE FUNCTION" not in sql.upper()          # D248
    v = (API / "migrations" / "versions" / "0051_selftest_repeat.py").read_text()
    assert 'down_revision = "0050_release_1_0_0"' in v
    assert '"/tests/<int:run_id>/repeat"' in (API / "eax" / "api" / "platform_tests.py").read_text()
    tr = (REPO / "services" / "web" / "src" / "TestRuns.jsx").read_text()
    assert "Run the failed ones again" in tr and "/repeat`" in tr and "RepeatPanel" in tr and "followed up by run" in tr
    sys.path.insert(0, str(REPO))
    from eaxcli import commands as C
    assert C.check_argv(["test", "failed", "12", "--warnings"]) == ["test", "failed", "12", "--warnings"]
    assert C.check_argv(["test", "full"]) == ["test", "full"]
    helptext = (REPO / "eaxcli" / "help.txt").read_text()
    assert "$ {eax} test failed" in helptext
    rep = (API / "eax" / "testing" / "report.py").read_text()
    assert "Then and now" in rep and "Repeat of self-test" in rep


def test_a_smoke_repeat_opens_the_failed_pages_of_the_new_model(monkeypatch, tmp_path):
    """Found running it (12 Nov 2026): smoke()'s own loop variable p hid the repeat's plan, so a smoke repeat broke with
    "string indices must be integers"."""
    from eax.testing import run
    monkeypatch.setattr(run.api_matrix, "call", lambda *a, **k: (200, "{}"))
    for f in ("documentation", "deploy_page", "command_centre", "banner_and_schedules", "iterations"):
        monkeypatch.setattr(run, f, lambda *a, **k: None)
    got = {}
    monkeypatch.setattr(run.ui_journeys, "run_all", lambda *a, **k: (got.update(k), {})[1])
    r = run.Run.__new__(run.Run)
    r.counts, r.only, r.ids, r.left_out = {}, None, NEW, 0
    r.recorder = lambda suite: (lambda *a, **k: None)
    r.log = lambda msg: None
    r.dir = tmp_path
    spec = {"paths": {"/api/v1/models": {"get": {}}}}
    rp = {"routes": ["#/metamodel/{model}/grid"], "journeys": {"journey: help and documentation"}}
    run.smoke(r, spec, {"super-admin": "t"}, {**NEW, "model_id": NEW["model"]}, "ticket", rp)
    assert got["routes"] == [f"#/metamodel/{NEW['model']}/grid"] and got["names"] == {"journey: help and documentation"}


def test_a_command_that_wrote_no_record_says_why(tmp_path):
    """R2.49 (owner, 12 Nov 2026, 19:12): Run the failed ones again ended "The test runner could not be built: No such
    run." because the build's container stopped before it wrote its record; now its own last lines are the reason."""
    spec = importlib.util.spec_from_file_location("ops_cc_r249", REPO / "services" / "ops" / "commandcentre.py")
    cc = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(REPO))
    spec.loader.exec_module(cc)
    cc.RUNS = str(tmp_path)

    def docker(*a, **k):
        if a[:2] == ("ps", "-q"):
            return ""                                    # not running
        if a[:2] == ("ps", "-aq"):
            return "abc\n"
        if a[0] == "logs":
            return "/usr/bin/python3: No module named eaxcli.cmdrun\n"
        return "exited (exit 1) "
    cc.hooks.update(docker=docker, me=lambda: {"project": "eaexplorer"})
    try:
        cc.detail("20261112T171200Z-test-ab12")
        raise AssertionError("no error")
    except FileNotFoundError as exc:
        assert "No module named eaxcli.cmdrun" in str(exc) and "exit 1" in str(exc)
