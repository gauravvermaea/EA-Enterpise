"""A self-test waits only for the containers it tests (owner, 13 Nov 2026: "I am not happy that we need to wait for
everything to be started for running test. Why is sample data and industry pack needed for testing?"; D652)."""

from __future__ import annotations

import contextlib
import json

from eax.testing import run as R


def _c(svc, state="running", health="healthy", code=0):
    return {"service": svc, "state": state, "health": health, "exit_code": code}


def test_each_container_under_test_is_up_starting_failed_or_off():
    got = R.readiness([_c("api"), _c("reports", health="starting"), _c("dms", "created", ""), _c("drawio", "exited", "", 0),
                       _c("views", "exited", "", 137), _c("library", health="unhealthy")])
    assert got["api"] == "up" and got["reports"] == "starting" and got["dms"] == "starting"
    assert got["drawio"] == "off" and got["views"] == "failed" and got["library"] == "failed"
    assert got["web"] == "off"                                     # not there: switched off
    assert "reports-init" not in R.UNDER_TEST and "setup" not in R.UNDER_TEST   # nothing for the sample data or packs


class _Run:
    def __init__(self):
        self.id, self.logs, self.results, self.steps = 1, [], [], []
        self.engine = type("E", (), {"begin": lambda s: contextlib.nullcontext(None)})()

    def log(self, m):
        self.logs.append(m)

    def recorder(self, suite):
        return lambda name, outcome, detail="", ms=0: self.results.append((name, outcome, detail))


def test_it_waits_for_a_starting_service_then_goes_on(monkeypatch):
    every = [_c(s) for s in R.UNDER_TEST]
    answers = iter([[*every[:-1], _c("drawio", health="starting")], every])
    t = {"now": 0.0}
    monkeypatch.setattr(R.store, "set_state", lambda conn, rid, **k: None)
    r = _Run()
    R.services_ready(r, "tok", call=lambda *a, **k: (200, json.dumps({"containers": next(answers)})),
                     sleep=lambda p: t.update(now=t["now"] + p), clock=lambda: t["now"])
    assert r.logs == ["waiting for draw.io to finish starting"]
    assert r.results == [("start-up: the services under test are up", "passed", "all up")]


def test_a_service_still_starting_after_the_wait_fails_its_check_and_the_run_goes_on(monkeypatch):
    every = [_c(s) for s in R.UNDER_TEST if s != "reports"] + [_c("reports", health="starting")]
    t = {"now": 0.0}
    monkeypatch.setattr(R.store, "set_state", lambda conn, rid, **k: None)
    r = _Run()
    R.services_ready(r, "tok", wait=30, pause=10, call=lambda *a, **k: (200, json.dumps({"containers": every})),
                     sleep=lambda p: t.update(now=t["now"] + p), clock=lambda: t["now"])
    assert ("start-up: Reports", "failed", "still starting after the wait") in r.results
    assert r.results[0][1] == "failed" and len(r.logs) == 3


def test_a_switched_off_service_is_skipped_not_waited_for(monkeypatch):
    every = [_c(s) for s in R.UNDER_TEST if s != "dms"]
    monkeypatch.setattr(R.store, "set_state", lambda conn, rid, **k: None)
    r = _Run()
    R.services_ready(r, "tok", call=lambda *a, **k: (200, json.dumps({"containers": every})), sleep=lambda p: None)
    assert r.logs == [] and ("start-up: Documents", "skipped", "switched off: its checks are skipped") in r.results


def test_the_run_waits_after_its_accounts_and_before_its_models():
    src = (R.__file__ and open(R.__file__, encoding="utf-8").read())
    i, j, k = (src.index("tokens = fixtures.accounts("), src.index("services_ready(r, tokens.get"),
               src.index("ids = fixtures.models_and_project("))
    assert i < j < k
