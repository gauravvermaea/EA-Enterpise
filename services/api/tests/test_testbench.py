"""The outside test bench (testbench/, D579 to D582): its arguments and guard, its reports, the load test's thresholds
and k6 script, the upgrade check with fakes, the reset-survival flow with fakes, its test data, and that it runs every
check the inside self-test runs (the same code, the same suites, the same filters)."""
import ast
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from testbench import SUITES, cli, lifecycle, reset, suites  # noqa: E402
from testbench import load as tb_load  # noqa: E402
from testbench.data import build as data_build  # noqa: E402
from testbench.report import write  # noqa: E402
from testbench.results import Run  # noqa: E402
from testbench.target import GuardError, check_owned, clean  # noqa: E402
from testbench.ui import clean_browsers  # noqa: E402

from eax.testing import SUITES as INSIDE_SUITES  # noqa: E402
from eax.testing import store  # noqa: E402


# ---------------------------------------------------------------- the guard and the target
def test_guard_needs_the_flag_or_the_ci_setting():
    with pytest.raises(GuardError):
        check_owned("https://ea.example.org", False, env={})
    assert check_owned("https://ea.example.org", True, env={}) == "ea.example.org"
    assert check_owned("https://ea.example.org", False, env={"EAX_TESTBENCH_I_OWN_THIS": "EA.example.org"})
    with pytest.raises(GuardError):
        check_owned("https://ea.example.org", False, env={"EAX_TESTBENCH_I_OWN_THIS": "other.example.org"})


def test_target_is_an_address_without_a_path():
    assert clean("ea.example.org/") == "https://ea.example.org"
    assert clean("http://localhost:8080") == "http://localhost:8080"
    for bad in ("", "ftp://x", "https://ea.example.org/app"):
        with pytest.raises(GuardError):
            clean(bad)


def test_cli_refuses_without_i_own_this(capsys):
    assert cli.main(["--target", "https://ea.example.org"]) == cli.EXIT_USAGE
    assert "--i-own-this" in capsys.readouterr().out
    assert cli.main([]) == cli.EXIT_USAGE


# ---------------------------------------------------------------- the same names and filters as eax test
def _args(*a):
    return cli.parser().parse_args(["run", *a])


def test_levels_and_suites_as_eax_test():
    assert cli.level_and_suites(_args(), store) == ("smoke", list(SUITES))
    assert cli.level_and_suites(_args("--detailed"), store)[0] == "detailed"
    assert cli.level_and_suites(_args("--suite", "api"), store) == ("detailed", ["api"])
    assert cli.level_and_suites(_args("--pages-only"), store) == ("detailed", ["ui"])
    assert cli.level_and_suites(_args("--journey", "help"), store) == ("detailed", ["ui"])
    assert set(cli.level_and_suites(_args("--suite", "all"), store)[1]) == set(SUITES)


def test_the_bench_takes_every_option_of_eax_test():
    help_txt = (REPO / "eaxcli" / "help.txt").read_text(encoding="utf-8")
    line = next(x for x in help_txt.splitlines() if x.startswith("### test "))
    # building the runner image is inside only; so is repeating a run's failed checks (R2.36: failed [run] --warnings)
    test_opts = set(__import__("re").findall(r"--[a-z-]+", line)) - {"--build", "--warnings", "--older-than", "--log"}   # delete: inside only (R2.43); watch --log (R3.2)
    bench_opts = {o for a in cli.parser()._subparsers._group_actions[0].choices["run"]._actions for o in a.option_strings}
    assert test_opts <= bench_opts, test_opts - bench_opts


def test_suites_are_the_self_tests():
    # but the backup checks (R2.45): they need the installation's own backup container, so they run inside only
    # and the restore test (R3.8): the command line only
    assert set(SUITES) == set(INSIDE_SUITES) - {"backup", "restore"}


def _calls(fn: ast.FunctionDef, modules: set[str]) -> set[str]:
    out = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            if node.func.value.id in modules:
                out.add(f"{node.func.value.id}.{node.func.attr}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "smoke":
            out.add("smoke")
    return out


def test_the_bench_runs_every_check_the_inside_run_runs():
    """Every test call in the inside run (eax/testing/run.py: cmd_run, smoke and collect) is one the bench makes or is
    bookkeeping the target does for it, so no check can be inside only."""
    tree = ast.parse((REPO / "services" / "api" / "eax" / "testing" / "run.py").read_text(encoding="utf-8"))
    mods = {"api_matrix", "api_writes", "db_checks", "security", "ui_journeys", "ui_flows", "ui_pages", "fixtures",
            "store", "report"}
    fns = {f.name: f for f in tree.body if isinstance(f, ast.FunctionDef)}
    inside = set()
    for name in ("cmd_run", "cmd_collect"):
        inside |= _calls(fns[name], mods)
    # smoke's own helpers (sign-in, areas, documentation, deploy page, command centre, banner, iterations) are covered
    # by calling run.smoke itself; its calls into the shared modules are listed here only to show nothing escapes
    smoke_calls = _calls(fns["smoke"], mods) - {"api_matrix.call", "api_matrix.endpoints", "api_matrix.in_area",
                                                "api_matrix.fill"}
    missing = (inside | smoke_calls) - suites.COVERED - suites.BOOKKEEPING
    assert not missing, f"inside only: {sorted(missing)} (add them to testbench/suites.py)"
    assert "smoke" in inside and "smoke" in suites.COVERED


# ---------------------------------------------------------------- browsers
def test_browsers():
    assert clean_browsers(None) == ["chromium"]
    assert clean_browsers("edge, safari,chrome") == ["msedge", "webkit", "chromium"]
    assert clean_browsers("all") == ["chromium", "firefox", "webkit", "msedge"]
    with pytest.raises(ValueError):
        clean_browsers("netscape")


# ---------------------------------------------------------------- reports
def _run(tmp_path) -> Run:
    r = Run("https://ea.example.org", tmp_path / "r", level="detailed", suites=["api", "ui"], quiet=True)
    rec = r.recorder("api")
    rec("GET /api/v1/models: without a token", "passed", "401")
    rec("GET /api/v1/models: as architect", "passed", "200")
    rec("write models: create an entity", "failed", "500", request="POST /x", response="500\nboom")
    r.recorder("ui", "Chromium 1")("page: #/models", "passed")
    r.recorder("ui", "Chromium 1")("journey: help", "skipped", "no project")
    r.recorder("security")("front door headers", "warning", "no HSTS")
    return r


def test_reports_html_json_junit(tmp_path):
    r = _run(tmp_path)
    out = write(r, {"notes": ["a note"]})
    data = json.loads(out["json"].read_text())
    assert data["result"] == "failed" and data["totals"]["failed"] == 1 and data["totals"]["total"] == 6
    cov = dict((c["what"], c["value"]) for c in data["coverage"])
    assert cov["Endpoints refused without a sign-in"] == "1 of 1" and "models 0/1" in cov["Writes tested, by area"]
    x = ET.parse(out["junit"]).getroot()
    assert x.tag == "testsuites" and sum(int(s.get("failures")) for s in x) == 1
    assert sum(int(s.get("skipped")) for s in x) == 1
    h = out["html"].read_text()
    assert "Coverage" in h and "a note" in h and "boom" in h and "prefers-color-scheme" in h


def test_exit_code_follows_the_result(tmp_path):
    assert cli.finish(_run(tmp_path)) == cli.EXIT_FAILED
    ok = Run("https://x.example", tmp_path / "ok", quiet=True)
    ok.recorder("smoke")("fine", "passed")
    assert cli.finish(ok) == cli.EXIT_OK


# ---------------------------------------------------------------- load: thresholds and k6
def _summary(med, p95, p99, fail, rps):
    return {"metrics": {"http_req_duration": {"med": med, "p(95)": p95, "p(99)": p99},
                        "http_req_failed": {"rate": fail}, "http_reqs": {"rate": rps, "count": 1000}}}


def test_thresholds_file_and_judge():
    marks = tb_load.thresholds()
    assert {"p50_ms", "p95_ms", "p99_ms", "error_rate", "min_rps"} <= set(marks)
    good = tb_load.judge(_summary(100, 500, 900, 0.001, marks["min_rps"] + 5), marks)
    assert not good["failed"] and "p95 500.0 ms" in good["summary"]
    bad = tb_load.judge({"metrics": {"http_req_duration": {"values": {"med": 9999, "p(95)": 9999, "p(99)": 9999}},
                                     "http_req_failed": {"values": {"rate": 0.5}}, "http_reqs": {"values": {"rate": 1}}}}, marks)
    assert bad["failed"] and len(bad["broken"]) == 5


def test_load_without_k6_says_how_to_get_it(tmp_path):
    r = Run("https://x.example", tmp_path / "l", quiet=True)
    out = tb_load.run(r, "https://x.example", ["t"], "", 10, 1, which=lambda _n: None)
    assert out["skipped"] and "k6" in r.results[0].detail and r.results[0].outcome == "skipped"


def test_load_reads_k6s_summary(tmp_path):
    r = Run("https://x.example", tmp_path / "l", quiet=True)

    def fake_k6(argv, env, **_kw):
        assert argv[:2] == ["k6", "run"] and env["USERS"] == "50" and json.loads(env["THRESHOLDS"])
        Path(argv[argv.index("--summary-export") + 1]).write_text(json.dumps(_summary(100, 300, 600, 0, 100)))
        return subprocess.CompletedProcess(argv, 0, "", "")
    out = tb_load.run(r, "https://x.example", ["t"], "m", 50, 5, which=lambda _n: "/usr/bin/k6", runner=fake_k6)
    assert not out["failed"] and r.results[0].outcome == "passed"


@pytest.mark.skipif(not shutil.which("node"), reason="node is not here")
def test_k6_script_parses(tmp_path):
    js = tmp_path / "s.mjs"
    js.write_text(tb_load.SCRIPT.read_text())
    subprocess.run(["node", "--check", str(js)], check=True)
    assert "summaryTrendStats" in js.read_text() and "p(99)" in js.read_text()


# ---------------------------------------------------------------- install and upgrade with fakes
class FakeClient:
    """An installation: answers /api/health, the API description and the state endpoint, as the version it is at."""
    world = {"version": "0.18.0", "migration": "0048_project_iterations", "up": True, "models": 5, "backed_up": True}

    def __init__(self, target, token=""):
        self.target, self.token = target, token

    def get(self, path, **_kw):
        w = self.world
        if not w["up"]:
            return 599, "no answer"
        if path == "/api/health":
            return 200, {}
        if path == "/api/v1/admin/testbench/state":
            return 200, {"version": w["version"], "migration": w["migration"],
                         "counts": {"models": w["models"], "entities": 10, "drawn views": None}}
        if path == "/api/v1/admin/backups":           # the updater's own backup (R3.11)
            rows = [{"name": "20261113T200000Z-before-upgrade", "kind": "before-upgrade", "pinned": True}] if w["backed_up"] else []
            return 200, {"infrastructure": {"infrastructure": rows}}
        return 404, {}


def test_upgrade_with_fakes(tmp_path):
    folder = tmp_path / "inst"
    calls = []

    def exporter(ref, dest, url):
        calls.append(("export", ref))
        dest.mkdir(parents=True)
        (dest / "eax.sh").write_text("")
        return "abc123"

    def sh(argv, cwd):
        calls.append(tuple(argv[2:4]))
        if "update" in argv:
            FakeClient.world.update(version=lifecycle.version_of(REPO), migration=lifecycle.migration_head(REPO))
        if "rollback" in argv:
            FakeClient.world.update(version="0.18.0", migration="0048_project_iterations")
        return 0
    FakeClient.world.update(version="0.18.0", migration="0048_project_iterations", up=True, models=5, backed_up=True)
    r = Run("https://localhost", tmp_path / "r", quiet=True)
    answers = tmp_path / "a.json"
    answers.write_text("{}")
    ok = lifecycle.upgrade(r, "v0.18.0", str(REPO), folder, answers, "https://localhost",
                           lambda: FakeClient("https://localhost", "t"), sh=sh, sleep=lambda _s: None,
                           client_of=FakeClient, exporter=exporter)
    assert ok, [(x.name, x.detail) for x in r.results if x.outcome == "failed"]
    assert ("export", "v0.18.0") in calls and ("deploy", "--console") in calls and ("update", "--to") in calls
    names = {x.name: x.outcome for x in r.results}
    assert names["data kept: models"] == "passed" and names["the version after the upgrade"] == "passed"
    assert "data kept: drawn views" not in names                      # a table the old version did not have
    # R3.11: the updater's own backup, then eax rollback, back to 0.18.0 with the data kept
    assert names["a full backup was taken before the upgrade"] == "passed" and ("rollback", "--yes") in calls
    assert names["the version after the roll back"] == "passed" and names["data kept after the roll back: models"] == "passed"


def test_a_roll_back_that_does_not_go_back_or_no_backup_fails(tmp_path):
    """R3.11: the upgrade test also checks the updater's backup and the roll back."""
    FakeClient.world.update(version="0.18.0", migration="x", up=True, models=5, backed_up=False)

    def sh(argv, cwd):
        if "update" in argv:
            FakeClient.world.update(version="0.19.0")
        return 0                                                        # rollback "succeeds" but changes nothing
    (tmp_path / "inst").mkdir()
    (tmp_path / "inst" / "eax.sh").write_text("")
    r = Run("https://localhost", tmp_path / "r", quiet=True)
    ok = lifecycle.upgrade(r, "v0.18.0", "v0.19.0", tmp_path / "inst", tmp_path / "a.json", "https://localhost",
                           lambda: FakeClient("https://localhost"), sh=sh, sleep=lambda _s: None, client_of=FakeClient)
    failed = {x.name for x in r.results if x.outcome == "failed"}
    assert not ok and {"a full backup was taken before the upgrade", "the version after the roll back"} <= failed
    FakeClient.world.update(version="0.18.0", backed_up=True)
    r2 = Run("https://localhost", tmp_path / "r2", quiet=True)
    lifecycle.upgrade(r2, "v0.18.0", "v0.19.0", tmp_path / "inst", tmp_path / "a.json", "https://localhost",
                      lambda: FakeClient("https://localhost"), sh=sh, sleep=lambda _s: None, client_of=FakeClient,
                      rollback=False)
    assert not any(x.name.startswith("eax rollback") for x in r2.results)   # --no-rollback leaves it upgraded


def test_upgrade_catches_lost_data_and_a_wrong_version(tmp_path):
    FakeClient.world.update(version="0.18.0", migration="x", up=True, models=5)

    def sh(argv, cwd):
        if "update" in argv:
            FakeClient.world.update(version="0.18.0", models=3)
        return 0
    (tmp_path / "inst").mkdir()
    (tmp_path / "inst" / "eax.sh").write_text("")
    r = Run("https://localhost", tmp_path / "r", quiet=True)
    ok = lifecycle.upgrade(r, "v0.18.0", "v0.19.0", tmp_path / "inst", tmp_path / "a.json", "https://localhost",
                           lambda: FakeClient("https://localhost"), sh=sh, sleep=lambda _s: None, client_of=FakeClient)
    assert not ok
    failed = {x.name for x in r.results if x.outcome == "failed"}
    assert {"the version after the upgrade", "data kept: models"} <= failed


def test_install_stops_when_deploy_fails(tmp_path):
    r = Run("https://localhost", tmp_path / "r", quiet=True)
    assert not lifecycle.install(r, tmp_path, tmp_path / "a.json", "https://localhost", sh=lambda a, c: 3,
                                 sleep=lambda _s: None, client_of=FakeClient)
    assert r.results[0].outcome == "failed" and "exit code 3" in r.results[0].detail


def test_migration_head_is_the_newest():
    assert lifecycle.migration_head(REPO).startswith("00")
    assert lifecycle.version_of(REPO)


# ---------------------------------------------------------------- reset-survival with fakes
def test_reset_survival_needs_the_name_and_reads_the_platforms_result(tmp_path):
    r = Run("https://localhost", tmp_path / "r", quiet=True)
    reset.run(r, FakeClient("https://localhost"), "demo-laptop", "wrong")
    assert r.results[0].outcome == "failed" and "nothing was reset" in r.results[0].detail

    seq = iter([200, 599, 599, 200])

    class C(FakeClient):
        def post(self, path, body=None, **_kw):
            assert body["argv"] == ["test", "--reset-survival", "--confirm", "demo-laptop"]
            assert body["confirm"] == {"typed": "demo-laptop", "understood": True}
            return 202, {"id": "run1"}

        def get(self, path, **_kw):
            if path == "/api/openapi.json":
                return next(seq, 200), {}
            return 200, {"runs": [{"id": "r1", "state": "passed", "checks": [{"name": "files survived", "result": "passed"}]}]}
    r2 = Run("https://localhost", tmp_path / "r2", quiet=True)
    reset.run(r2, C("https://localhost", "t"), "demo-laptop", "demo-laptop", sleep=lambda _s: None, client_of=C)
    names = {x.name: x.outcome for x in r2.results}
    assert names["EA Explorer went down for the reset"] == "passed"
    assert names["EA Explorer answers again after the reset"] == "passed"
    assert names["the platform's reset-survival test"] == "passed" and names["files survived"] == "passed"


# ---------------------------------------------------------------- publishing the results
def test_publish_sends_the_summary_and_every_result_in_batches(tmp_path):
    r = _run(tmp_path)
    for i in range(150):
        r.recorder("api")(f"GET /x{i}: as architect", "passed")
    sent = []

    class C:
        target, token = "https://ea.example.org", "t"

        def post(self, path, body=None, **_kw):
            sent.append((path, body))
            return 200, {"run_id": 9, "state": "failed"}
    suites.publish(C(), suites.Session(7, {}, "tk", {}), r, everything=True)
    assert all(p == "/api/v1/admin/testbench/runs/7/results" for p, _ in sent)
    assert sent[0][1]["results"][0]["name"] == "external testbench: summary"
    assert [b["done"] for _, b in sent].count(True) == 1 and sent[-1][1]["done"]
    assert all(len(b["results"]) <= 100 for _, b in sent) and all(b["suite"] in ("smoke", *SUITES) for _, b in sent)
    sent.clear()

    class Other(C):
        target = "https://history.example.org"
    suites.publish(C(), suites.Session(), r, everything=True, to=Other())
    assert sent[0][0] == "/api/v1/admin/testbench/runs" and sent[-1][0] == "/api/v1/admin/testbench/runs/9/finish"


# ---------------------------------------------------------------- the test data
def test_every_data_file_is_as_built_and_loads():
    assert data_build.check() == [], "run python -m testbench.data build"
    m = json.loads((REPO / "testbench" / "data" / "manifest.json").read_text())
    from openpyxl import load_workbook
    for name, f in m["files"].items():
        p = REPO / "testbench" / "data" / name
        assert p.exists() and p.stat().st_size < 50 * 1024 * 1024 and f["used_by"], name
        assert __import__("hashlib").sha256(data_build.canonical(name, p.read_bytes())).hexdigest() == f["sha256"], name
        if name.endswith(".xlsx"):
            assert load_workbook(p).sheetnames, name
        elif name.endswith((".zip", ".docx")):
            assert zipfile.ZipFile(p).testzip() is None, name
        elif name.endswith(".json"):
            json.loads(p.read_text())
        elif name.endswith(".xml"):
            assert ET.parse(p).getroot().tag == "mxfile"
        elif name.endswith(".pdf"):
            assert p.read_bytes().startswith(b"%PDF-") and p.read_bytes().rstrip().endswith(b"%%EOF")
        elif name.endswith(".png"):
            assert p.read_bytes().startswith(b"\x89PNG")
    good = load_workbook(REPO / "testbench" / "data" / "deliveries" / "good.xlsx")
    assert [c.value for c in good["ApplicationComponent"][2]][:2] == ["name", "description"]
    assert json.loads((REPO / "testbench" / "data" / "credentials.template.json").read_text())["token"] == ""


def test_every_journey_names_data_that_exists():
    """A journey or write that uses a data file names it by its manifest key ("data": "deliveries/good.xlsx"); each must
    exist. The expected results name only files that exist."""
    from eax.testing import ui_flows
    names = set(json.loads((REPO / "testbench" / "data" / "manifest.json").read_text())["files"])
    used = set()

    def walk(o):
        if isinstance(o, dict):
            if isinstance(o.get("data"), str):
                used.add(o["data"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(ui_flows.JOURNEYS)
    assert used <= names, used - names
    expected = json.loads((REPO / "testbench" / "data" / "expected" / "expected.json").read_text())
    assert set(expected) <= names
    surveys = __import__("eax.surveys", fromlist=["x"])
    survey = json.loads((REPO / "testbench" / "data" / "surveys" / "survey.json").read_text())
    assert all(q["kind"] in surveys.KINDS for s in survey["sections"] for q in s["questions"])


def test_the_state_answers_within_its_budget():
    """Full self-test, 13 Nov 2026: "GET /api/v1/admin/testbench/state: no answer" (71 s; the self-test waits a minute):
    eight exact counts of up to 20 s each. The counts now share a 30-second budget, each at most 10 s (statement and lock
    timeout), and the ones left when it is spent are None with the reason."""
    from eax import testbench_state as ts
    t = {"now": 0.0}
    said = []

    class Conn:
        def execute(self, sql, params=None):
            q = str(sql)
            said.append(q)
            if q.startswith("SELECT count(*)"):
                t["now"] += 8                                   # each count takes 8 seconds
            return type("R", (), {"scalar": lambda s: 7 if q.startswith("SELECT count") else "x"})()

    class Eng:
        def begin(self):
            import contextlib
            return contextlib.nullcontext(Conn())
    counts, problems = ts.count_rows(Eng(), clock=lambda: t["now"])
    assert t["now"] <= ts.STATE_BUDGET + 8                       # never much past the budget
    done = [k for k, v in counts.items() if v == 7]
    assert done == list(ts.COUNTS)[:4] and all(counts[k] is None for k in list(ts.COUNTS)[4:])
    assert len(problems) == 4 and "not counted" in problems[0]
    assert "SET LOCAL statement_timeout = 10000" in said and "SET LOCAL lock_timeout = 10000" in said
    assert "SET LOCAL statement_timeout = 6000" in said           # the fourth gets what is left
    api = (REPO / "services/api/eax/api/testbench_api.py").read_text()
    assert "counts, problems = count_rows(get_engine())" in api and "statement_timeout = '20s'" not in api
