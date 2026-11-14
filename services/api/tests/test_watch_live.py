"""Watching a self-test as it happens, and stopping it (R3.2): the snapshot, the log read in pieces, `eax test watch` and
`eax test stop`, and where they are wired."""

from __future__ import annotations

from pathlib import Path

from eax.testing import cli, live, store

REPO = Path(__file__).resolve().parents[3]


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class _Conn:
    """Answers the two queries snapshot makes: the new results and the failures."""

    def __init__(self, results):
        self.results, self.asked = results, []

    def execute(self, q, params):
        self.asked.append(params)
        if "outcome = 'failed'" in str(q):
            return _Rows([r for r in reversed(self.results) if r["outcome"] == "failed"][: params["n"]])
        return _Rows([r for r in self.results if r["id"] > params["a"]][: params["n"]])


RUN = {"id": 9, "state": "running", "step": "API: every endpoint, as architect", "stop_asked": None, "folder": "f9",
       "level": "full", "suites": ["api"], "started_at": "now"}
RESULTS = [{"id": i, "suite": "api", "name": f"check {i}", "outcome": "failed" if i == 3 else "passed",
            "detail": "boom" if i == 3 else "", "duration_ms": 5} for i in range(1, 6)]


def _patch(monkeypatch, run=RUN):
    monkeypatch.setattr(store, "run_row", lambda conn, rid: dict(run) if run and rid == run["id"] else None)
    monkeypatch.setattr(store, "tally", lambda conn, rid: {"passed": 4, "failed": 1, "skipped": 0, "warning": 0})
    monkeypatch.setattr(store, "progress", lambda conn, r, done: {"done": done, "total": 20, "left": 20 - done})


def test_snapshot_gives_what_is_new_and_every_failure(monkeypatch):
    _patch(monkeypatch)
    conn = _Conn(RESULTS)
    s = live.snapshot(conn, 9, after=2, log_from=10, read_log=lambda folder, at: (f"{folder}@{at}\n", at + 7))
    assert s["open"] and s["run"]["step"] == "API: every endpoint, as architect"
    assert [r["id"] for r in s["results"]] == [3, 4, 5] and s["after"] == 5
    assert s["failures"] == [{"id": 3, "suite": "api", "name": "check 3", "outcome": "failed", "detail": "boom", "duration_ms": 5}]
    assert s["log"] == "f9@10\n" and s["log_next"] == 17
    assert s["progress"]["left"] == 15 and s["tally"]["failed"] == 1


def test_snapshot_nothing_new_keeps_the_place(monkeypatch):
    _patch(monkeypatch)
    s = live.snapshot(_Conn(RESULTS), 9, after=5)
    assert s["results"] == [] and s["after"] == 5 and s["log"] == "" and s["log_next"] == 0


def test_snapshot_of_no_run(monkeypatch):
    _patch(monkeypatch)
    assert live.snapshot(_Conn([]), 1) is None


def test_the_log_is_read_on_from_where_it_was(tmp_path, monkeypatch):
    (tmp_path / "f9").mkdir()
    log = tmp_path / "f9" / "run.log"
    log.write_text("one\ntwo\n")
    read = live.file_log_reader(tmp_path)
    text, nxt = read("f9", 0)
    assert text == "one\ntwo\n" and nxt == 8
    with open(log, "a") as f:
        f.write("three\n")
    assert read("f9", nxt) == ("three\n", 14)
    assert read("missing", 3) == ("", 3) and read("", 0) == ("", 0)


def test_a_big_log_is_cut_at_a_whole_line(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "LOG_CHUNK", 10)
    (tmp_path / "f").mkdir()
    (tmp_path / "f" / "run.log").write_text("aaaa\nbbbb\ncccc\n")
    text, nxt = live.file_log_reader(tmp_path)("f", 0)
    assert text == "aaaa\nbbbb\n" and nxt == 10


def test_follow_prints_the_step_each_check_and_the_end():
    snaps = [
        {"run": {"id": 9, "state": "running", "step": "API: every endpoint"}, "open": True, "results": RESULTS[:2],
         "after": 2, "log": "10:00 started\n", "log_next": 14, "tally": {}},
        {"run": {"id": 9, "state": "running", "step": "API: every endpoint"}, "open": True, "results": RESULTS[2:3],
         "after": 3, "log": "", "log_next": 14, "tally": {}},
        {"run": {"id": 9, "state": "failed", "step": "done"}, "open": False, "results": [], "after": 3, "log": "",
         "log_next": 14, "tally": {"passed": 2, "failed": 1}},
    ]
    asked, out = [], []

    def get(after, at):
        asked.append((after, at))
        return snaps[len(asked) - 1]
    state = live.follow(get, out=out.append, sleep=lambda s: None, show_log=True)
    assert state == "failed" and asked == [(0, 0), (2, 14), (3, 14)]
    assert out[0] == "> API: every endpoint" and out.count("> API: every endpoint") == 1
    assert "10:00 started" in out and any("FAILED  api      check 3: boom" in x for x in out)
    assert out[-1] == "Self-test 9 failed: 2 passed, 1 failed, 0 warnings, 0 skipped"


def test_follow_without_a_run():
    out = []
    assert live.follow(lambda a, b: None, out=out.append) == "" and out == ["No such self-test run."]


def test_line_for_gives_the_reason_only_when_not_passed():
    assert live.line_for({"outcome": "passed", "suite": "ui", "name": "page", "detail": "x"}).endswith("page")
    assert live.line_for({"outcome": "skipped", "suite": "db", "name": "n", "detail": "why\nmore"}).endswith("n: why")


def test_which_run_is_watched():
    runs = [{"id": 12, "state": "passed"}, {"id": 11, "state": "running"}, {"id": 10, "state": "failed"}]
    assert cli.pick_watch(runs, [])["id"] == 11                         # the one running
    assert cli.pick_watch(runs, ["10"])["id"] == 10
    assert cli.pick_watch(runs[:1], [])["id"] == 12                     # else the last
    assert cli.pick_watch(runs, ["99"]) == {"id": 99} and cli.pick_watch([], []) is None


def test_watch_and_ctrl_c(monkeypatch):
    out = []
    monkeypatch.setattr(live, "follow", lambda *a, **k: "passed")

    class E:
        def connect(self):
            raise AssertionError("not reached: follow is replaced")
    assert cli.watch(E(), [{"id": 3, "state": "running"}], [], out=out.append) == 0
    assert "eax test stop 3" in out[0]

    def interrupted(*a, **k):
        raise KeyboardInterrupt
    monkeypatch.setattr(live, "follow", interrupted)
    out.clear()
    assert cli.watch(E(), [{"id": 3, "state": "running"}], [], out=out.append) == 0
    assert out[-1] == "Stopped watching; the run goes on."
    monkeypatch.setattr(live, "follow", lambda *a, **k: "failed")
    assert cli.watch(E(), [{"id": 3, "state": "failed"}], ["3"], out=out.append) == 1
    out.clear()
    assert cli.watch(E(), [], [], out=out.append) == 0 and "No self-test to watch" in out[0]


def test_stop_asks_the_run_to_stop_and_audits(monkeypatch):
    from contextlib import contextmanager

    from eax import audit
    asked, audited, out = [], [], []

    class Eng:
        @contextmanager
        def begin(self):
            yield "conn"

    @contextmanager
    def tests(conn):
        yield "tc"
    monkeypatch.setattr(store, "tests", tests)
    monkeypatch.setattr(store, "ask_stop", lambda tc, rid, by: asked.append((tc, rid, by)) or True)
    monkeypatch.setattr(audit, "record", lambda conn, **k: audited.append(k))
    runs = [{"id": 5, "state": "running"}, {"id": 4, "state": "passed"}]
    assert cli.stop(Eng(), runs, [], out=out.append) == 0
    assert asked[0][:2] == ("tc", 5) and "(eax test stop)" in asked[0][2]
    assert audited[0]["action"] == "selftest.stopped" and audited[0]["object_id"] == "5"
    assert "asked to stop" in out[-1]
    assert cli.stop(Eng(), runs, ["4"], out=out.append) == 0 and "nothing to stop" in out[-1] and len(asked) == 1


def test_wired_into_the_api_the_page_the_launchers_and_the_help():
    api = (REPO / "services/api/eax/api/platform_tests.py").read_text()
    assert '@blp.route("/tests/<int:run_id>/live")' in api and "live.file_log_reader(WORK_TESTS)" in api
    page = (REPO / "services/web/src/TestRuns.jsx").read_text()
    assert page.count("<TestWatch runId=") == 2 and ">Watch</button>" in page
    w = (REPO / "services/web/src/TestWatch.jsx").read_text()
    assert "/live?after=" in w and "Stop the run" in w and "/stop`" in w
    assert 'rest[:1] in (["watch"], ["stop"])' in (REPO / "eaxcli/main.py").read_text()
    assert '"${1:-}" = "watch" ] || [ "${1:-}" = "stop" ]' in (REPO / "eax.sh").read_text()
    assert '$RestArgs[0] -eq "watch" -or $RestArgs[0] -eq "stop"' in (REPO / "eax.ps1").read_text()
    h = (REPO / "eaxcli/help.txt").read_text()
    assert "|watch [run] [--log]|stop [run]|" in h and "$ {eax} test watch" in h
