"""R3.13: the 297 checks the last Release 2 full test skipped. 219 API checks had "a path parameter the run's fixtures
cannot fill": the ids are now found one level up (reads only), and writes are called with an id that is never there;
74 "heavy or live" reads are now checked, bounded; persist/ is mounted in a runner the operations helper starts; the
break-glass page is opened in a browser of its own, and the Classic "Everything else" page in the sweep."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from eax.testing import api_matrix as am
from eax.testing import ui_pages

REPO = Path(__file__).resolve().parents[3]


def test_an_id_is_found_from_the_list_one_level_up():
    asked = []

    def call(base, method, path, token=None, timeout=60, size=1500):
        asked.append((method, path, token, size))
        if path == "/api/v1/projects/P1/documents":
            return 200, json.dumps({"documents": [{"doc": "D7", "name": "Vision"}]})
        if path == "/api/v1/admin/containers":
            return 200, json.dumps([{"service": "api", "id": "c1"}])
        return 404, ""
    cache: dict = {}
    got = am.discover("http://x", "/api/v1/projects/{project}/documents/{doc}", {"project": "P1"}, "SUPER", cache, call=call)
    assert got["doc"] == "D7" and asked == [("get", "/api/v1/projects/P1/documents", "SUPER", None)]
    am.discover("http://x", "/api/v1/projects/{project}/documents/{doc}/versions", {"project": "P1"}, "SUPER", cache, call=call)
    assert len(asked) == 1                                         # each list read once
    assert am.discover("http://x", "/api/v1/admin/containers/{service}/logs", {}, "S", {}, call=call)["service"] == "api"
    assert "x" not in am.discover("http://x", "/api/v1/things/{x}", {}, "S", {}, call=call)     # nothing listed: not found


def _spec(*paths):
    return {"security": [{"bearerAuth": []}],
            "paths": {p: {m: {} for m in ms} for p, ms in paths}}


def _jobs(spec, ids, tokens, call):
    names = []
    am.run("http://x", spec, tokens, ids, None, lambda name, outcome, detail, ms, **kw: names.append((name, outcome, detail)),
           workers=1)
    return names


def test_heavy_reads_are_checked_bounded_and_writes_never_touch_real_ids(monkeypatch):
    calls = []

    def call(base, method, path, token=None, timeout=60, size=1500):
        calls.append((method, path, token))
        if token is None:
            return 401, ""
        if path.endswith("/backups") and method == "get":
            return 200, json.dumps({"infrastructure": {"infrastructure": [{"name": "B1"}]}})
        return 403, ""
    monkeypatch.setattr(am, "call", call)
    spec = _spec(("/api/v1/admin/backups", ["get"]),
                 ("/api/v1/admin/backups/infrastructure/{name}/restore", ["post"]),
                 ("/api/v1/models/{model}/package", ["get"]))
    rows = _jobs(spec, {"model": "M1"}, {"super-admin": "S", "no-role": "N"}, call)
    names = {n for n, _o, _d in rows}
    assert not any(o == "skipped" for _n, o, _d in rows), rows
    assert "GET /api/v1/admin/backups: every test role" in names                          # a heavy read, bounded
    assert "GET /api/v1/models/{model}/package: as no-role (a download or a stream: read once)" in names
    assert "GET /api/v1/models/{model}/package: every test role" not in names            # the costly file: not as every role
    restore = [p for m, p, t in calls if m == "post"]
    assert restore and all(am.NOTHING in p for p in restore)                              # never a real backup's name


def test_what_still_cannot_be_called_says_which_id_is_missing(monkeypatch):
    monkeypatch.setattr(am, "call", lambda *a, **k: (404, ""))
    rows = _jobs(_spec(("/api/v1/surveys/{sid}/results", ["get"])), {}, {"super-admin": "S"}, am.call)
    assert rows == [("GET /api/v1/surveys/{sid}/results: skipped", "skipped",
                     "the test data has no {sid} to call it with (none listed one level up)")]


def test_persist_is_mounted_in_a_runner_the_helper_starts():
    spec = importlib.util.spec_from_file_location("testruns_r313", REPO / "services/ops/testruns.py")
    tr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tr)
    mounts = [{"Destination": "/eax-work", "Source": "C:\\\\eax\\\\work"}, {"Destination": "/eax-persist", "Source": "C:\\\\eax\\\\persist"}]
    tr.H["docker"] = lambda *a, **k: json.dumps(mounts) if a[0] == "inspect" else ""
    tr.socket.gethostname = lambda: "ops"
    info = {"Config": {"Env": ["EAX_X=1"]}, "NetworkSettings": {"Networks": {"eax_backend": {}}}}
    tr.runner_image = lambda info=None: "eaexplorer/testrunner:dev"
    args = tr._runner_args(info, "eax-testrunner", "F1", ["run"])
    assert "C:\\\\eax\\\\persist:/persist:ro" in args


def test_the_break_glass_page_is_opened_alone_and_everything_else_in_the_sweep():
    assert "#/more" in ui_pages.SEEDS and "#/more" not in ui_pages.SKIP_ROUTES
    assert ui_pages.TESTED_ALONE == {"#/break-glass"}
    seen = []

    class Loc:
        first = None

        def wait_for(self, **_k):
            seen.append("waited")

    class Page:
        def goto(self, url, **_k):
            seen.append(url)

        def locator(self, sel):
            seen.append(sel)
            loc = Loc()
            loc.first = loc
            return loc
    out = []
    assert ui_pages.break_glass_page(Page(), "https://x", lambda *a: out.append(a)) == "passed"
    assert seen[0] == "https://x/#/break-glass" and "Break-glass sign-in" in seen[1] and out[0][0] == "page: #/break-glass"
    src = (REPO / "services/api/eax/testing/ui_journeys.py").read_text()
    assert "ui_pages.break_glass_page(alone.new_page(), base, rec)" in src
