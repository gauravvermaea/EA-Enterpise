"""The self-test's coverage (0.19.0, D575 to D578): the page sweep's enumeration, the journeys' definitions, the API
writes' plan, the coverage maths of the report, the command line a run equals, and the Self-test page's "From the
command line" section kept in step with eaxcli/help.txt."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from eax.testing import api_writes, db_checks, report, store, ui_flows, ui_pages

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "services" / "web" / "src"
IDS = {"model": "11111111-1111-1111-1111-111111111111", "other_model": "22222222-2222-2222-2222-222222222222",
       "project": "33333333-3333-3333-3333-333333333333", "entity": "44444444-4444-4444-4444-444444444444",
       "sid": "abcdef123456", "dup": "Self-test duplicate ap", "model_name": "self_test_abcdef123456_1",
       "project_name": "self_test_abcdef123456_3", "other_name": "self_test_abcdef123456_2",
       "view": "55555555-5555-5555-5555-555555555555", "view_name": "self_test_abcdef123456 view"}


# ---------------------------------------------------------------- the page sweep (D575)
def test_every_top_level_route_of_the_app_is_swept_or_skipped_with_a_reason():
    app = (WEB / "App.jsx").read_text(encoding="utf-8")
    routes = set(re.findall(r'route\.startsWith\("(#/[a-z-]+)', app))
    known = {re.match(r"#/[a-z-]+", s).group(0) for s in ui_pages.SEEDS if s != "#/"} | set(ui_pages.SKIP_ROUTES)
    assert routes - known == set(), f"pages the sweep does not know: {sorted(routes - known)}"
    assert all(why for why in ui_pages.SKIP_ROUTES.values())


def test_seeds_fill_the_runs_own_model_and_project_and_leave_out_what_it_has_not():
    s = ui_pages.seeds(IDS)
    assert f"#/metamodel/{IDS['model']}" in s and f"#/projects/{IDS['project']}" in s
    assert not any("{" in x for x in s)
    none = ui_pages.seeds({"model": IDS["model"]})
    assert not any("/projects/" in x for x in none) and "#/projects" in none


def test_only_the_runs_own_models_and_project_are_opened():
    m, other = IDS["model"], "99999999-9999-9999-9999-999999999999"
    assert ui_pages.in_scope(f"#/metamodel/{m}/quality", IDS)
    assert ui_pages.in_scope("#/admin/banner", IDS)
    assert not ui_pages.in_scope(f"#/metamodel/{other}", IDS)
    assert ui_pages.in_scope("#/admin/sql", IDS) and not ui_pages.in_scope("#/break-glass", IDS)
    assert not ui_pages.in_scope("https://example.org/#/x", IDS)
    assert ui_pages.norm("#/admin/") == "#/admin" and ui_pages.norm("") == "#/"


@pytest.mark.parametrize("found, errors, help_state, outcome", [
    ({"head": True, "notFound": False}, [], "ok", "passed"),
    ({"head": True, "notFound": True}, [], "ok", "failed"),
    ({"head": True, "notFound": False}, ["GET /api/v1/x: 500"], "ok", "failed"),
    ({"head": False, "notFound": False}, [], "ok", "warning"),
    ({"head": True, "notFound": False}, [], "empty", "warning"),
    ({"head": True, "notFound": False}, [], "closed", "warning"),
])
def test_a_page_is_judged_the_same_way_every_time(found, errors, help_state, outcome):
    assert ui_pages.judge(found, errors, help_state)[0] == outcome


# ---------------------------------------------------------------- the journeys (D576)
def test_journeys_are_well_formed():
    kinds = set(ui_flows.STEP_KINDS)
    keys = [ui_flows.key(j) for j in ui_flows.JOURNEYS]
    assert len(keys) == len(set(keys)), "every journey has its own --journey key"
    for j in ui_flows.JOURNEYS:
        assert j["roles"], j["name"]
        for s in j["steps"]:
            assert next(iter(s)) in kinds, (j["name"], s)
        if j.get("headless_only"):
            assert j.get("why_headless"), f"{j['name']}: say why it runs headless only"
        assert j.get("refused") or j.get("why_no_refusal"), f"{j['name']}: refused to one role, or say why nobody is"
        if j.get("refused"):
            assert j["refused"]["role"] not in j["roles"], j["name"]
        for s in j["steps"]:
            if "remember" in s:
                re.compile(s["url"])
            if "click_re" in s:
                re.compile(s["click_re"])
        kept = {s["remember"] for s in j["steps"] if "remember" in s}
        used = set(re.findall(r"\{\$([a-z_]+)\}", json.dumps(j["steps"])))
        assert used <= kept, (j["name"], used - kept)
    assert sum(1 for j in ui_flows.JOURNEYS if j["smoke"]) == 5, ("the smoke test runs five key journeys (the menu bar since "
                                                                  "R2.0.1, the libraries for everyone since 12 Nov 2026)")


def test_the_browser_side_knows_the_same_step_kinds():
    js = (WEB / "selfTestDriver.js").read_text(encoding="utf-8")
    kinds = json.loads(re.search(r"STEP_KINDS = (\[[^\]]*\])", js).group(1))
    used = {next(iter(s)) for j in ui_flows.JOURNEYS for s in j["steps"]}
    assert used <= set(kinds)


def test_journeys_expand_per_role_with_a_refusal():
    js = ui_flows.journeys(IDS)
    names = [j["name"] for j in js]
    assert any(n.endswith("as committer") for n in names)
    refused = [j for j in js if j.get("refusal")]
    assert refused and all(j["steps"] == [] for j in refused)
    def strings(o):
        if isinstance(o, str):
            yield o
        elif isinstance(o, dict):
            for v in o.values():
                yield from strings(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                yield from strings(v)
    assert not [x for j in js for x in strings(j) if re.search(r"\{[a-z_]+\}", x)], "every placeholder is filled"


def test_smoke_runs_the_five_key_journeys_once_and_watch_leaves_out_the_headless_ones():
    smoke = ui_flows.journeys(IDS, smoke=True)   # content, quality, iteration, the menu bar (R2.0.1), the libraries
    assert len(smoke) == 5 and not any(j.get("refusal") for j in smoke)
    watched = ui_flows.journeys(IDS, watch=True)
    assert not any(j.get("headless_only") for j in watched)
    assert ui_flows.skipped_in_browser()


# ---------------------------------------------------------------- the role plan (D583)
def test_every_journey_runs_as_each_allowed_role_then_one_refused():
    for j in ui_flows.JOURNEYS:
        plan = ui_flows.role_plan(j)
        assert [r for r, refused in plan if not refused] == j["roles"], j["name"]
        refused = [r for r, x in plan if x]
        assert refused == ([j["refused"]["role"]] if j.get("refused") else []), j["name"]
        assert ui_flows.role_plan(j, smoke=True) == [(j["roles"][0], False)]


def test_one_role_given_runs_it_or_is_refused_or_skips():
    admin = next(j for j in ui_flows.JOURNEYS if ui_flows.key(j) == "admin")
    assert ui_flows.role_plan(admin, "it-admin") == [("it-admin", False)]
    assert ui_flows.role_plan(admin, "committer") == [("committer", True)]
    helpj = next(j for j in ui_flows.JOURNEYS if ui_flows.key(j) == "help and documentation")
    assert ui_flows.role_plan(helpj, "it-admin") == []          # nobody is refused the help: nothing to run
    assert ui_flows.role_plan(helpj, "super-admin") == [("super-admin", False)]


def test_the_roles_a_journey_names_are_test_roles_given_rights_by_the_fixtures():
    from eax.testing import fixtures
    for j in ui_flows.JOURNEYS:
        for r in j["roles"] + ([j["refused"]["role"]] if j.get("refused") else []):
            assert r in store.TEST_ROLES, (j["name"], r)
        for s in j["steps"]:
            if "as" in s and s["as"] != "{role}":
                assert s["as"] in store.TEST_ROLES, (j["name"], s)
        if "{p}" in json.dumps(j["steps"]):
            # a project journey's roles open the project: a Super Admin, or a member the fixtures add
            assert all(r == "super-admin" or r in fixtures.PROJECT_TEST_ROLES for r in j["roles"]), j["name"]


def test_new_journeys_need_their_fixtures_and_carry_their_data_to_the_browser():
    no_view = ui_flows.journeys({k: v for k, v in IDS.items() if k != "view"})
    assert not any(j["name"].startswith("drawn view") for j in no_view)
    no_child = ui_flows.journeys({k: v for k, v in IDS.items() if k != "other_model"})
    assert not any(j["name"].startswith("child merge") for j in no_child)
    watched = ui_flows.journeys(IDS, watch=True)
    ups = [s for j in watched for s in j["steps"] if "upload" in s and s.get("data")]
    assert ups and all(s.get("b64") for s in ups)
    import base64
    assert base64.b64decode(ups[0]["b64"]) == ui_flows.data_bytes(ups[0]["data"])


def test_the_test_data_folder_is_the_env_var_then_the_checkout(monkeypatch, tmp_path):
    monkeypatch.setenv("EAX_TEST_DATA", str(tmp_path))
    assert ui_flows.data_folder() == tmp_path
    monkeypatch.delenv("EAX_TEST_DATA")
    assert (ui_flows.data_folder() / "deliveries" / "good.xlsx").is_file()
    with pytest.raises(ValueError):
        ui_flows.data_bytes("../../etc/passwd")


def test_the_words_the_journeys_click_are_on_the_screens():
    """Each button, field and pop-up a journey names is in the screens' source (so a renamed button fails here first)."""
    src = "\n".join(p.read_text(encoding="utf-8") for p in WEB.glob("*.jsx"))
    for j in ui_flows.JOURNEYS:
        if ui_flows.key(j) not in ("admin", "drawn view", "import", "survey", "child merge"):
            continue
        for s in j["steps"]:
            for k in ("click", "fill"):
                t = s.get(k)
                if not isinstance(t, str) or "{" in t or t.startswith("Self-test") or s.get("optional"):
                    continue
                if t in ("Name", "Message", "Protocol", "Option 1", "Option 2"):   # shared, numbered, or the fixtures' own
                    continue
                for name in ("Application Component", "Capability"):       # the drawn view's pop-ups name the type
                    t = t.replace(name, "${typeName}")
                assert t.rstrip(".…").split(" (")[0][:12] in src, (j["name"], k, t)


def test_the_admin_journey_puts_back_the_banner_and_removes_only_its_own_schedules():
    calls = []
    state = {"banner": {"text": "self_test_abcdef123456 banner"}, "schedules": [{"id": "s1", "name": "Nightly backup"},
                                                                             {"id": "s2", "name": "self_test_abcdef123456 schedule"}]}

    def call(method, path, body=None):
        calls.append((method, path, body))
        if method == "GET" and path.endswith("/banner"):
            return 200, {"banner": state["banner"]}
        if method == "GET":
            return 200, {"schedules": state["schedules"]}
        return 200, {}
    before = {"banner": {"text": "Upgrade on Saturday", "level": "notice", "audience": "everyone"}, "schedules": ["s1"]}
    done = ui_flows.admin_restore(call, before, "abcdef123456")
    assert ("PUT", "/api/v1/admin/banner", {"text": "Upgrade on Saturday", "level": "notice", "audience": "everyone"}) in calls
    assert ("POST", "/api/v1/admin/commands/schedules/s2/remove", {}) in calls
    assert not any("s1" in c[1] for c in calls if c[0] == "POST")
    assert len(done) == 2
    calls.clear()
    ui_flows.admin_restore(call, {"banner": None, "schedules": ["s1", "s2"]}, "abcdef123456")
    assert ("DELETE", "/api/v1/admin/banner", None) in calls      # nothing was set before: the self-test's banner goes
    snap = ui_flows.admin_snapshot(call)
    assert snap["schedules"] == ["s1", "s2"]


def test_a_remembered_value_fills_later_steps():
    assert ui_flows.with_vars({"open": "#/merge-requests/{$mr}"}, {"mr": "7"}) == {"open": "#/merge-requests/7"}
    assert "importCells" in ui_flows.drop_script("Capability") and "'Capability'" in ui_flows.drop_script("Capability")


def test_one_role_runs_what_it_may_and_is_refused_the_rest():
    js = ui_flows.journeys(IDS, role="report-viewer")
    assert js and all(j["role"] == "report-viewer" for j in js)
    assert all(j.get("refusal") for j in js if not j["name"].startswith(("help", "the libraries")))
    assert any(j["name"].startswith("help") and j["steps"] for j in js)
    assert any(j["name"].startswith("the libraries") and j["steps"] for j in js)   # for everyone


def test_a_journey_is_chosen_by_part_of_its_name_and_needs_a_project_when_it_names_one():
    only = ui_flows.journeys(IDS, only=["duplicates"])
    assert only and all("duplicates" in j["name"] for j in only)
    no_project = ui_flows.journeys({k: v for k, v in IDS.items() if k != "project"})
    assert not any(j["name"].startswith("project:") for j in no_project)


# ---------------------------------------------------------------- the API writes (D577)
def test_every_write_stays_inside_the_runs_own_fixtures():
    own = {IDS["model"], IDS["other_model"], IDS["project"], IDS["entity"]}
    for w in api_writes.plan(IDS, IDS["sid"]):
        for u in re.findall(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}", json.dumps([w["path"], w.get("body")])):
            assert u in own, w
        assert w["area"] and w["what"]
        if w["method"] == "post" and isinstance(w.get("body"), dict):
            for k in ("name", "title"):
                if k in w["body"]:
                    assert w["body"][k].startswith(f"self_test_{IDS['sid']}"), w


def test_every_area_has_a_refused_write():
    plan = api_writes.plan(IDS, IDS["sid"])
    areas = {w["area"] for w in plan}
    assert {"content", "relationships", "metamodel", "projects", "surveys", "machine access", "merge requests",
            "imports", "drawn views"} <= areas
    for a in areas:
        assert any(w.get("refused") for w in plan if w["area"] == a), f"{a}: no refused write"


@pytest.mark.parametrize("status, ok, refused, outcome", [
    (201, {200, 201}, False, "passed"), (403, set(), True, "passed"), (401, set(), True, "passed"),
    (400, set(), True, "warning"), (200, set(), True, "failed"), (500, {200}, False, "failed"), (409, {200}, False, "failed"),
])
def test_a_write_is_judged(status, ok, refused, outcome):
    assert api_writes.judge(status, ok, refused)[0] == outcome


def test_the_id_of_what_a_write_made_is_found():
    assert api_writes.ident({"id": "a"}) == "a"
    assert api_writes.ident({"survey": {"guid": "b"}}) == "b"
    assert api_writes.ident("text") is None and api_writes.ident({"x": 1}) is None


# ---------------------------------------------------------------- the database checks (D577)
def test_drawn_view_bindings_are_judged():
    m = "m1"
    assert db_checks.bindings({"V (m1)": ["e1"]}, {"e1": (m, False)})[0] == "passed"
    assert db_checks.bindings({"V (m1)": ["e1"]}, {"e1": (m, True)})[0] == "warning"
    assert db_checks.bindings({"V (m1)": ["e1"]}, {})[0] == "failed"
    assert db_checks.bindings({"V (m1)": ["e1"]}, {"e1": ("m2", False)})[0] == "failed"
    assert db_checks.EA_ID.findall('<object ea_id="44444444-4444-4444-4444-444444444444" label="x">') == [IDS["entity"]]


def test_persist_json_is_checked(tmp_path):
    assert db_checks.persist_json(None)[0] == "skipped"
    (tmp_path / "banner.json").write_text('{"text": "hi"}', encoding="utf-8")
    assert db_checks.persist_json(str(tmp_path))[0] == "passed"
    (tmp_path / "schedules.json").write_text("{not json", encoding="utf-8")
    assert db_checks.persist_json(str(tmp_path))[0] == "failed"


def test_the_new_database_checks_only_read():
    for name, sql, _ in db_checks.CHECKS:
        assert re.match(r"\s*SELECT\b", sql, re.I), name
        assert not re.search(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE)\b", re.sub(r"'[^']*'", "''", sql)), name


# ---------------------------------------------------------------- the report's coverage (D577)
def _r(suite, name, outcome):
    return {"suite": suite, "name": name, "outcome": outcome}


def test_coverage_counts_pages_journeys_and_writes_by_area():
    rows = [_r("ui", "page: #/", "passed"), _r("ui", "page: #/admin", "failed"), _r("ui", "page: #/sql", "skipped"),
            _r("ui", "journey: model content", "passed"),
            _r("api", "write content: create an entity", "passed"), _r("api", "write content: refused", "failed"),
            _r("api", "write surveys: create", "passed"), _r("db", "x", "passed")]
    cov = {r[0]: r[1:] for r in report.coverage(rows)}
    pages = next(v for k, v in cov.items() if k.lower().startswith("pages"))
    assert tuple(pages) == (1, 2), pages              # (passed, out of); skipped ones are not counted
    assert "API writes: content" in cov and "API writes: surveys" in cov
    content = cov["API writes: content"]
    assert tuple(content) == (1, 2)


# ---------------------------------------------------------------- the command line a run equals (D578)
RUNS = [
    {"level": "smoke", "suites": []},
    {"level": "detailed", "suites": ["api", "ui", "db", "security", "backup"]},
    {"level": "detailed", "suites": ["api"], "role": "architect"},
    {"level": "detailed", "suites": ["ui"], "journeys": ["drawn view"], "role": "architect"},
    {"level": "detailed", "suites": ["ui"], "pages_only": True},
    {"level": "detailed", "suites": ["ui"], "watch": True, "area": "models"},
    {"level": "detailed", "suites": ["ui"], "repeat_of": 12, "repeat_warnings": True},     # a repeat (R2.36)
    {"level": "detailed", "suites": ["backup"]},                                         # eax test backup (R2.45)
]


def test_command_line():
    assert store.command_line(RUNS[0]) == ".\\eax test --smoke"
    assert store.command_line(RUNS[1], "./eax.sh") == "./eax.sh test --detailed"
    assert store.command_line(RUNS[3]) == '.\\eax test --journey "drawn view" --role architect'
    assert store.command_line(RUNS[4]) == ".\\eax test --pages-only"
    assert "from the Self-test page only" in store.command_line(RUNS[5])


def test_the_page_builds_the_same_command_line_as_the_server():
    node = shutil.which("node")
    if not node:
        pytest.skip("no node here")
    js = (WEB / "selfTestDriver.js").as_uri()
    script = (f"import({json.dumps(js)}).then(m => console.log(JSON.stringify("
              f"{json.dumps(RUNS)}.map(r => [m.commandLine(r, '.\\\\eax'), m.commandLine(r, './eaxpy.sh')]))))")
    out = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    want = [[store.command_line(r, ".\\eax"), store.command_line(r, "./eaxpy.sh")] for r in RUNS]
    assert got == want


def test_eax_test_has_two_choices_and_clean():
    """R2.0.1 (D592, D593): eax test shows smoke, full and clean; R2.36 (D605) adds failed. The older options still work
    for scripts and CI."""
    text = (ROOT / "eaxcli" / "help.txt").read_text(encoding="utf-8")
    entry = store.test_entry(text)
    assert entry["syntax"].startswith("test [smoke|full|backup|ui-review|failed")
    names = [o["flag"].split()[0] for o in entry["options"]]
    assert names == ["smoke", "full", "backup", "ui-review", "failed", "delete", "clean"], names   # ui-review: R2.12
    assert entry["examples"] == ["{eax} test", "{eax} test full", "{eax} test backup", "{eax} test ui-review", "{eax} test failed",
                                 "{eax} test failed 12 --warnings", "{eax} test delete --older-than 30",
                                 "{eax} test clean", "{eax} test clean --dry-run"]
    ops = (ROOT / "services" / "ops" / "testruns.py").read_text(encoding="utf-8")
    assert 'if "full" in args:' in ops and '+ ["--detailed"]' in ops
    for f, needle in (("eax.ps1", '$RestArgs[0] -eq "clean"'), ("eax.sh", '[ "${1:-}" = "clean" ]'),
                      ("eaxcli/main.py", 'command == "test" and rest[:1] == ["clean"]')):
        assert needle in (ROOT / f).read_text(encoding="utf-8"), f


# ---------------------------------------------------------------- the migration (0049)
def test_migration_0049_follows_0048():
    v = (ROOT / "services" / "api" / "migrations" / "versions" / "0049_selftest_coverage.py").read_text(encoding="utf-8")
    assert 'down_revision = "0048_project_iterations"' in v
    sql = (ROOT / "services" / "api" / "migrations" / "sql" / "0049_selftest_coverage.sql").read_text(encoding="utf-8")
    assert "journeys" in sql and "pages_only" in sql and "ADD COLUMN IF NOT EXISTS" in sql


def test_a_write_with_a_body_runs(monkeypatch):
    """R2.0.1 (the laptop's full run): every write with a JSON body was skipped as "an earlier write did not make what
    this one needs", because the body's own braces were taken for a {name} not filled. Only {name} counts now."""
    calls = []
    monkeypatch.setattr(api_writes, "call", lambda base, m, path, tok, body=None: (calls.append(path) or (201, {"id": "x"})))
    monkeypatch.setattr(api_writes, "wait_for", lambda *a, **k: ("passed", ""))
    got = []
    api_writes.run("http://api", {"model-admin": "t"}, IDS, lambda name, outcome, *a, **k: got.append((name, outcome)))
    assert ("write content: create an entity", "passed") in got
    assert calls and calls[0].endswith("/content/entities")
    assert api_writes.judge(404, {200}, True, {404})[0] == "passed" and api_writes.judge(404, {200}, True)[0] == "failed"
