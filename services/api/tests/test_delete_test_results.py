"""R2.43 (owner, 12 Nov 2026: "delete test logs both on web and UI so that all the captured images, logs videos all are
deleted. Otherwise this will take a lot of space") and R2.40 ("please tell how many tests are left as well when in the
screen")."""

from __future__ import annotations

import contextlib
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]


def _ops():
    spec = importlib.util.spec_from_file_location("ops_testruns_r243", REPO / "services" / "ops" / "testruns.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_helper_removes_only_test_folders(tmp_path):
    ops = _ops()
    ops.WORK = str(tmp_path)
    (tmp_path / "tests" / "20261112T1-run").mkdir(parents=True)
    (tmp_path / "tests" / "20261112T1-run" / "video.webm").write_text("v")
    (tmp_path / "keep.txt").write_text("k")
    out = ops.delete_results(["20261112T1-run", "../keep.txt", "gone-already"])
    assert out == {"removed": ["20261112T1-run", "gone-already"], "left": ["../keep.txt"]}
    assert not (tmp_path / "tests" / "20261112T1-run").exists() and (tmp_path / "keep.txt").exists()


def test_which_runs_and_the_usage():
    from eax.testing import cleanup
    with pytest.raises(ValueError):
        cleanup.pick(None, "", None)
    with pytest.raises(ValueError):
        cleanup.pick(None, "x", None)
    with pytest.raises(ValueError):
        cleanup.pick(None, "all", 0)


def test_a_delete_purges_then_removes_rows_and_folders(monkeypatch):
    from eax.testing import cleanup
    calls = []

    class Conn:
        def execute(self, sql, params=None):
            q = str(sql)
            calls.append(q.split()[0] + " " + (q.split("FROM")[1].split()[0] if "FROM" in q else ""))
            if q.startswith("SELECT id, folder, state"):
                state = "running" if params["id"] == 2 else "failed"
                return type("R", (), {"mappings": lambda s: type("M", (), {"first": lambda s2: {"id": params["id"], "folder": f"f{params['id']}", "state": state}})()})()
            return type("R", (), {"rowcount": 5})()
    eng = type("E", (), {"begin": lambda s: contextlib.nullcontext(Conn())})()
    monkeypatch.setattr(cleanup.fx, "purge", lambda conn, rid, by: {"models": 2, "projects": 1, "service_accounts": 3, "credentials": 3})
    got = []
    out = cleanup.delete(eng, [1, 2], "me", lambda folders: (got.extend(folders), {"removed": folders, "left": []})[1])
    assert out["runs"] == 1 and out["results"] == 5 and out["fixtures"] == 9 and got == ["f1"]
    assert "run 2 is still going" in out["notes"][0]
    assert any(c.startswith("DELETE tests.test_runs") for c in calls)
    assert "Deleted 1 run(s)" in cleanup.message(out)


def test_wired_on_the_web_the_command_line_and_once_a_day():
    api = (REPO / "services/api/eax/api/platform_tests.py").read_text()
    assert '@blp.route("/tests/delete")' in api and '"keep_days" in data' in api
    assert '"eax.test_results_cleanup"' in (REPO / "services/api/eax/jobs.py").read_text()
    page = (REPO / "services/web/src/TestRuns.jsx").read_text()
    assert "function DeleteResults" in page and "Delete all test results..." in page and ">Delete</button>" in page
    for f in ("eax.sh", "eax.ps1", "eaxcli/main.py"):                                   # eax in sync (D331)
        src = (REPO / f).read_text()
        assert '"delete"' in src or "cli delete" in src, f
    sys.path.insert(0, str(REPO))
    from eaxcli import commands as C
    assert C.check_argv(["test", "delete", "--older-than", "30", "--yes"]) == ["test", "delete", "--older-than", "30", "--yes"]
    assert "  delete  deletes test runs for good" in (REPO / "eaxcli/help.txt").read_text()


def test_checks_left_are_shown_while_a_run_goes_on():
    store = (REPO / "services/api/eax/testing/store.py").read_text()
    assert "def progress(conn, run" in store and '"progress": progress(conn, run, len(every))' in store
    page = (REPO / "services/web/src/TestRuns.jsx").read_text()
    assert "<Progress p={d.progress} />" in page and "left ({p.percent}%)" in page
    run = (REPO / "services/api/eax/testing/run.py").read_text()
    assert "def where(self) -> str:" in run and 'msg = f"{msg}  {self.where()}"' in run      # and on the command line
