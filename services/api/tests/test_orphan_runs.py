"""R2.64 (owner, 13 Nov 2026): self-test 2 stayed "Running" for good after `eax up` restarted its test runner, and Stop
could not end it (Stop only asks the runner, which was gone). Whoever runs a run now touches .alive in its folder every
20 seconds; a run marked running with no heartbeat for 3 minutes, started more than 5 minutes ago, is closed as stopped
with the reason, when the Self-test page or `eax test` looks, when a run starts, and at once on Stop."""

from __future__ import annotations

import importlib.util
import os
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_a_run_is_an_orphan_only_without_a_recent_heartbeat(tmp_path):
    from eax.testing import alive
    now = time.time()
    folder = tmp_path / "20261113T154600Z-run2"
    assert alive.is_orphan(folder, now - 3600, now)                   # never beat (killed before this fix, or at once)
    assert not alive.is_orphan(folder, now - 60, now)                 # just started: the runner may still be coming up
    alive.beat(folder)
    assert not alive.is_orphan(folder, now - 3600, now)               # beating
    os.utime(folder / alive.BEAT_FILE, (now - 600, now - 600))
    assert alive.is_orphan(folder, now - 3600, now)                   # silent for 10 minutes
    assert alive.is_orphan(None, now - 3600, now)                     # no folder recorded


def test_keep_beating_writes_the_heartbeat_until_stopped(tmp_path):
    from eax.testing import alive
    stop = alive.keep_beating(tmp_path / "f")
    for _ in range(50):
        if alive.last_beat(tmp_path / "f"):
            break
        time.sleep(0.02)
    stop.set()
    assert alive.last_beat(tmp_path / "f") is not None


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class _Conn:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, sql, params=None):
        return _Rows(self.rows)


def test_close_orphans_stops_the_dead_runs_and_leaves_the_live_ones(tmp_path, monkeypatch):
    from eax.testing import alive, store
    now = time.time()
    alive.beat(tmp_path / "live")
    closed = []
    monkeypatch.setattr(store, "finish", lambda conn, rid, error="", stopped="": closed.append((rid, stopped)) or "stopped")
    rows = [{"id": 2, "folder": "dead", "started": now - 5400},       # the laptop's run 2: 89 minutes, no heartbeat
            {"id": 3, "folder": "live", "started": now - 5400},       # beating: left alone
            {"id": 4, "folder": "", "started": now - 30}]             # just started: left alone
    assert store.close_orphans(_Conn(rows), tmp_path, now) == [2]
    assert closed == [(2, store.GONE)] and "no longer running" in store.GONE
    assert store.close_orphans(_Conn(rows), tmp_path / "missing", now) == []   # work/tests not readable: nothing closed


def test_whoever_runs_a_run_keeps_its_heartbeat():
    run = (REPO / "services/api/eax/testing/run.py").read_text()
    assert run.count("alive.keep_beating(r.dir)") == 2                # the run, and its collect step
    ops = (REPO / "services/ops/testruns.py").read_text()
    assert 'beating = keep_beating(f"{WORK}/tests/{folder}")' in ops and "beating.set()" in ops
    spec = importlib.util.spec_from_file_location("testruns_r264", REPO / "services/ops/testruns.py")
    tr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tr)
    from eax.testing import alive
    assert (tr.BEAT_FILE, tr.BEAT_EVERY) == (alive.BEAT_FILE, alive.EVERY)   # the same heartbeat as the API reads


def test_the_page_eax_test_and_stop_close_dead_runs():
    api = (REPO / "services/api/eax/api/platform_tests.py").read_text()
    assert api.count("_tidy()") >= 4                                  # the list, a run, starting one, Stop
    stop = api[api.index('@blp.route("/tests/<int:run_id>/stop")'):api.index('@blp.route("/tests/<int:run_id>/browser")')]
    assert "if run_id in _tidy():" in stop and "closed as stopped" in stop
    start = api[api.index("def post(self, data):"):api.index("busy = tc.execute(")]
    assert "_tidy()" in start                                         # a dead run no longer blocks a new one
    cli = (REPO / "services/api/eax/testing/cli.py").read_text()
    assert "store.close_orphans(conn)" in cli
