"""R3.8: the full backup-and-restore test (eax/testing/restore_check.py): back up, change, restore each way, compare
the content each time; from the command line only; the results recorded after the last restore; the safety backup put
back when a step fails; the backups it made removed."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from eax.testing import restore_check as rc

REPO = Path(__file__).resolve().parents[3]
BEFORE = {"m1": {"name": "self_test_x_1", "entities": 7, "relationships": 2, "attributes": 3, "sum": "aa"},
          "m2": {"name": "self_test_x_2", "entities": 2, "relationships": 0, "attributes": 0, "sum": "bb"},
          "project:p1": {"name": "self_test_x_3", "steps": 5, "items": 4, "members": 2, "sum": "cc"}}


def test_compare_says_what_differs():
    assert rc.compare(BEFORE, {k: dict(v) for k, v in BEFORE.items()}) == []
    after = {k: dict(v) for k, v in BEFORE.items()}
    after["m1"]["entities"] = 6
    after["m2"]["sum"] = "zz"
    del after["project:p1"]
    d = rc.compare(BEFORE, after)
    assert "self_test_x_1: entities 7 before, 6 after" in d
    assert "self_test_x_2: the content differs (same counts)" in d and "self_test_x_3 is missing" in d
    assert rc.compare({"project:p": {"skipped": "elsewhere"}}, {}) == []


class _Install:
    """An installation behind the API: backups, tasks, restores; the content dirty after a change until a restore."""

    def __init__(self, restores_work=True):
        self.dirty, self.calls, self.restores_work, self.deleted = False, [], restores_work, []

    def call(self, base, method, path, token, body=None):
        self.calls.append((method, path, body))
        if method == "GET" and path == "/api/health":
            return 200, {}
        if method == "GET" and path == "/api/v1/me":
            return 200, {}
        if method == "GET" and path.startswith("/api/v1/tasks/"):
            name = path.rsplit("/", 1)[1]
            return 200, {"done": True, "status": "done", "result": {"name": name, "model": "m9"}}
        if method == "GET" and path == "/api/v1/admin/backups":
            return 200, {"infrastructure": {"restore_choices": {"full": "", "app": "", "app+data": "", "db": "", "files": ""},
                                            "infrastructure": [{"name": "20991231T000000Z-before", "kind": "before-restore",
                                                                "created": "20991231T000000Z"}]},
                         "application": {"runs": [{"name": "app1", "models": [{"id": "m1", "file": "m1.eaxbackup.zip"}]}]}}
        if method == "GET" and path == "/api/v1/admin/backups/restore":
            return 200, {"busy": False}
        if method == "POST" and path == "/api/v1/admin/backups/infrastructure":
            return 202, {"id": "infra1"}
        if method == "POST" and path == "/api/v1/admin/backups/application":
            return 202, {"id": "app1"}
        if method == "POST" and ("restore" in path):
            if self.restores_work:
                self.dirty = False
            return 202, {"id": "task-restore"}
        if method == "POST" and path.endswith("/delete"):
            self.deleted.append(path)
            return 200, {}
        return 404, {}


def _wire(monkeypatch, inst):
    monkeypatch.setattr(rc, "fingerprint", lambda engine, models, projects:
                        {k: ({**v, "sum": "changed"} if inst.dirty else dict(v)) for k, v in BEFORE.items()})
    monkeypatch.setattr(rc, "change", lambda engine, models, projects, mark: setattr(inst, "dirty", True) or 3)
    monkeypatch.setattr(rc, "wait_task", lambda base, token, task, seconds, call=None:
                        {"done": True, "status": "done", "result": {"name": task.get("id"), "model": "m9"}})


def test_the_whole_test_passes_when_every_restore_puts_the_content_back(monkeypatch):
    inst, recorded = _Install(), []
    _wire(monkeypatch, inst)
    tally = rc.run("http://api", "tok", {"model": "m1", "other_model": "m2", "project": "p1"},
                   lambda *a: recorded.append(a), lambda m: None, None, 7, "eax", call=inst.call, sleep=lambda s: None)
    names = [r[0] for r in recorded]
    assert tally["failed"] == 0, [r for r in recorded if r[1] == "failed"]
    for what in ("db", "app+data", "files", "full"):
        assert f"restore: infrastructure restore ({what})" in names
        assert f"restore: after the infrastructure restore ({what}): the content is as before the backup" in names
        assert f"restore: signing in after the infrastructure restore ({what})" in names
    assert "restore: restore all from the application backup" in names and "restore: one model put back over itself" in names
    assert "restore: the safety backup put back" not in names                      # nothing failed
    assert any("infra1/delete" in p for p in inst.deleted) and any("app1/delete" in p for p in inst.deleted)
    assert any("before/delete" in p for p in inst.deleted)                         # the restore's own safety copies too
    over = next(b for m, p, b in inst.calls if p == "/api/v1/admin/backups/restore-model")
    assert over["mode"] == "over" and over["confirm"] == "self_test_x_1"           # the model's name, as the API asks


def test_a_restore_that_does_not_put_the_content_back_fails_and_the_safety_backup_is_put_back(monkeypatch):
    inst, recorded = _Install(restores_work=False), []
    _wire(monkeypatch, inst)
    tally = rc.run("http://api", "tok", {"model": "m1", "project": "p1"}, lambda *a: recorded.append(a),
                   lambda m: None, None, 7, "eax", call=inst.call, sleep=lambda s: None)
    assert tally["failed"] > 0
    failed = [r[0] for r in recorded if r[1] == "failed"]
    assert any("the content is as before the backup" in n for n in failed)
    assert "restore: the safety backup put back" in [r[0] for r in recorded]


def test_the_results_are_recorded_only_after_the_last_restore(monkeypatch):
    inst, events = _Install(), []
    _wire(monkeypatch, inst)
    orig = inst.call
    inst.call = lambda *a, **k: events.append("api") or orig(*a, **k)
    rc.run("http://api", "tok", {"model": "m1"}, lambda *a: events.append("record"), lambda m: None, None, 7, "eax",
           call=inst.call, sleep=lambda s: None)
    first = events.index("record")
    assert "api" not in events[first:]                         # every record after the last call to the installation


@pytest.mark.parametrize("trigger", ["web", ""])
def test_from_the_web_it_is_skipped_with_the_reason(trigger):
    recorded = []
    rc.run("http://api", "tok", {"model": "m1"}, lambda *a: recorded.append(a), lambda m: None, None, 7, trigger,
           call=lambda *a, **k: pytest.fail("no call from the web"))
    assert recorded == [("restore: the full backup and restore test", "skipped", rc.CLI_ONLY, 0)]


def test_the_suite_is_wired_in_and_the_web_cannot_start_it():
    from eax.testing import SUITES, WEB_SUITES
    assert SUITES[-1] == "restore" and "restore" not in WEB_SUITES
    run = (REPO / "services/api/eax/testing/run.py").read_text()
    assert '_restore_suite(r, tokens, ids, run_id, args.trigger)' in run
    api = (REPO / "services/api/eax/api/platform_tests.py").read_text()
    assert '"suites": list(WEB_SUITES)' in api and "The restore test runs from the command line only" in api
    sql = (REPO / "services/api/migrations/sql/0068_selftest_restore_suite.sql").read_text()
    assert "'backup', 'restore']" in sql and "'backup', 'restore'))" in sql
    help_ = (REPO / "eaxcli/help.txt").read_text()
    assert "$ {eax} test restore" in help_ and "|backup|restore|" in help_


def _testruns():
    spec = importlib.util.spec_from_file_location("testruns_r38", REPO / "services/ops/testruns.py")
    tr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tr)
    return tr


def test_eax_test_restore_and_backup_restore_pick_the_suite_and_ask_first():
    tr = _testruns()
    assert tr.suites_of(["restore"]) == ["restore"] and tr.suites_of(["backup-restore"]) == ["restore"]
    assert tr.suites_of([])[-1] == "restore"                        # full ends with it
    assert tr.restore_agreed(["--yes"], ["restore"]) and tr.restore_agreed(["--ci"], ["restore"])
    assert tr.restore_agreed([], ["restore"], ask=lambda q: "yes", tty=True)
    assert not tr.restore_agreed([], ["restore"], ask=lambda q: "no", tty=True)
    assert not tr.restore_agreed([], ["restore"], tty=False)       # no terminal, no --yes: left out


def test_backup_names_made_during_the_test():
    import time
    now = time.time()
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now + 120))
    old = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now - 3600))
    assert rc._after(stamp, now) and not rc._after(old, now) and not rc._after("garbage", now)
