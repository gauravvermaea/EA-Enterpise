"""Infrastructure backups and restores in the operations helper (phase 8.4, D216), with Docker replaced."""

from __future__ import annotations

import importlib.util
import json
import os
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _ops(tmp_path, monkeypatch):
    work, backups, repo = tmp_path / "work", tmp_path / "backups", tmp_path / "repo"
    for d in (work, backups, repo / "deploy" / "compose"):
        d.mkdir(parents=True)
    (repo / "docker-compose.yml").write_text("services: {}\n")
    (work / "eaexplorer.env").write_text("EAX_TIMEZONE=UTC\nEAX_HOSTNAME=now\n")
    monkeypatch.setenv("EAX_WORK_MOUNT", str(work))
    monkeypatch.setenv("EAX_BACKUP_MOUNT", str(backups))
    monkeypatch.setenv("EAX_REPO_MOUNT", str(repo))
    monkeypatch.setenv("EAX_API_URL", "http://127.0.0.1:9")    # nothing listens: "could not tell everyone now"
    spec = importlib.util.spec_from_file_location("ops_backup_test", ROOT.parent / "ops" / "ops.py")
    ops = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ops)
    state = {"api": "running", "dms": "running", "keycloak": "running", "backup": "running", "db": "running", "proxy": "running",
             "reports": "exited"}
    calls: list[list[str]] = []
    monkeypatch.setattr(ops, "containers", lambda: [{"id": f"id-{k}", "name": k, "service": k, "state": v, "status": "",
                                                     "image": f"eaexplorer/{k}:0.12.0", "self": False} for k, v in state.items()])

    def docker(*args, timeout=120):
        calls.append(list(args))
        if args[0] == "stop":
            state[args[-1][3:]] = "exited"
        if args[0] == "start":
            state[args[-1][3:]] = "running"
        if args[:2] == ("image", "inspect"):
            return json.dumps([{"Id": "sha256:abcdef1234567890", "RepoDigests": [], "Created": "2026-11-06"}])
        return ""
    monkeypatch.setattr(ops, "docker", docker)

    class R:
        def __init__(self, code=0, out=""):
            self.returncode, self.stdout, self.stderr = code, out, ""

    def run(args, **k):   # docker exec <id> backup.sh <rel> | restore.sh <rel> --dbs .. --files ..
        calls.append(list(args))
        if args[3] == "backup.sh":
            folder = backups / args[4]
            (folder / "databases").mkdir(parents=True, exist_ok=True)
            (folder / "files").mkdir(parents=True, exist_ok=True)
            for n in ("eaexplorer", "keycloak", "superset", "mayan"):
                (folder / "databases" / f"{n}.dump").write_text(n)
            (folder / "files" / "documents.tar.gz").write_text("docs")
            (folder / "SHA256SUMS").write_text("x")
            return R(0, "backup: done")
        return R(0, "restore: done")
    monkeypatch.setattr(ops.subprocess, "run", run)

    class Popen:   # docker exec <id> restore.sh <rel> --dbs .. --files ..: its lines, as they come
        def __init__(self, args, **k):
            import io
            calls.append(list(args))
            self.stdout = io.StringIO("restore: checking the checksums\nrestore: done\n")

        def wait(self):
            return 0
    monkeypatch.setattr(ops.subprocess, "Popen", Popen)
    return ops, work, backups, calls, state


def test_backup_is_tagged_with_code_config_and_manifest(tmp_path, monkeypatch):
    ops, work, backups, calls, _ = _ops(tmp_path, monkeypatch)
    m = ops._do_backup("Before the demo!", "user_it_admin", "on-demand", "0.12.0")
    assert m["status"] == "ok" and m["name"].endswith("-Before-the-demo") and m["tag"] == "Before the demo!"
    folder = backups / "infrastructure" / m["name"]
    assert (folder / "config" / "eaexplorer.env").read_text().startswith("EAX_TIMEZONE")
    assert (folder / "code" / "docker-compose.yml").exists()
    rel = json.loads((folder / "code" / "release.json").read_text())
    assert rel["version"] == "0.12.0" and {i["service"] for i in rel["images"]} >= {"api", "dms"}
    assert m["parts"]["databases"] == ["eaexplorer", "keycloak", "mayan", "superset"] and m["parts"]["files"] == ["documents"]
    listed = ops.list_infra()
    assert listed[0]["name"] == m["name"] and listed[0]["by"] == "user_it_admin" and not listed[0]["pinned"]
    ev = ops.take_events()
    assert ev[0]["kind"] == "backup" and ev[0]["status"] == "ok" and ops.take_events() == []


def test_keep_the_newest_and_the_pinned(tmp_path, monkeypatch):
    ops, *_ = _ops(tmp_path, monkeypatch)
    names = []
    for i in range(4):
        names.append(ops._do_backup(f"b{i}", "x", "scheduled", "0.12.0")["name"])
        time.sleep(1.05)   # one a second: the folder names carry the time
    ops.pin_backup(names[0], True)
    gone = ops.cleanup_infra(2)       # keep 2 (Administration > Backups)
    assert gone == [names[1]]
    left = {m["name"] for m in ops.list_infra()}
    assert left == {names[0], names[2], names[3]}


def test_restore_app_and_data_in_maintenance(tmp_path, monkeypatch):
    ops, work, backups, calls, state = _ops(tmp_path, monkeypatch)
    m = ops._do_backup("nightly", "system", "scheduled", "0.12.0")
    (work / "eaexplorer.env").write_text("EAX_TIMEZONE=UTC\nEAX_HOSTNAME=changed\n")
    seen = {}
    real_popen = ops.subprocess.Popen

    def watch(args, **k):
        if args[3] == "restore.sh":
            seen["maintenance"] = ops.maintenance()
            seen["stopped"] = sorted(s for s, v in state.items() if v == "exited")
            seen["page"] = (work / "proxy" / "maintenance").exists()
        return real_popen(args, **k)
    monkeypatch.setattr(ops.subprocess, "Popen", watch)
    r = ops._do_restore(m["name"], "app+data", "user_super_admin", "0.12.0")
    assert r["status"] == "ok", r
    assert sorted(r["databases"]) == ["eaexplorer", "mayan"] and r["files"] == ["documents"] and r["config"]
    restore = next(c for c in calls if len(c) > 3 and c[3] == "restore.sh")
    assert restore[restore.index("--dbs") + 1] in ("eaexplorer,mayan", "mayan,eaexplorer")
    assert seen["maintenance"]["by"] == "user_super_admin" and ops.maintenance() is None      # read-only while restoring, then off
    assert {"api", "dms"} <= set(seen["stopped"]) and state["api"] == state["dms"] == "running"   # stopped, then started again
    assert "EAX_HOSTNAME=now" in (work / "eaexplorer.env").read_text()                       # the config file came back
    assert any(n.startswith("eaexplorer.env.") for n in os.listdir(work / "config-history"))   # the one before is kept
    before = next(x for x in ops.list_infra() if x["kind"] == "before-restore")
    assert before["pinned"] and r["before"] == before["name"]                                  # the state before, kept and pinned
    # the whole environment came down (D230): all but db, backup, ops and proxy; the proxy showed its page
    assert set(seen["stopped"]) == {"api", "dms", "keycloak", "reports"} and seen["page"]
    assert not (work / "proxy" / "maintenance").exists()
    assert any(c[:1] == ["start"] and c[-1] == "id-keycloak" for c in calls)                # everyone signs in again
    assert not any(c[:1] == ["start"] and c[-1] == "id-reports" for c in calls)             # was not running: stays so


def test_restore_refuses_a_newer_backup_and_a_failed_one(tmp_path, monkeypatch):
    ops, *_ = _ops(tmp_path, monkeypatch)
    m = ops._do_backup("future", "x", "on-demand", "0.13.0")
    r = ops._do_restore(m["name"], "db", "x", "0.12.0")
    assert r["status"] == "failed" and "newer than this installation" in r["error"]
    assert "newer than" in ops.restore_detail(r["restore"])["error"]                 # recorded, with why
    assert ops._do_restore(m["name"], "app", "x", "0.12.0")["status"] == "ok"   # the config file alone is fine
    assert ops._do_restore("nothing-here", "full", "x", "0.12.0")["status"] == "failed"


def test_partial_restore_warns_and_choices():
    src = (ROOT.parent / "ops" / "ops.py").read_text()
    for what in ("full", "app", "app+data", "db", "files"):
        assert f'"{what}":' in src
    assert "point at them may no longer" in src and "PINNED" in src


def test_a_backup_removes_the_oldest_beyond_keep(tmp_path, monkeypatch):
    ops, *_ = _ops(tmp_path, monkeypatch)
    names = []
    for i in range(3):
        names.append(ops._do_backup(f"n{i}", "system", "scheduled", "0.12.0", keep=2)["name"])
        time.sleep(1.05)
    assert [m["name"] for m in ops.list_infra()] == [names[2], names[1]]


def test_restores_are_recorded_with_their_log(tmp_path, monkeypatch):
    ops, work, backups, calls, state = _ops(tmp_path, monkeypatch)
    m = ops._do_backup("nightly", "system", "scheduled", "0.12.0")
    r = ops._do_restore(m["name"], "db", "user_it_admin", "0.12.0")
    assert r["status"] == "ok" and r["restore"]
    d = ops.restore_detail(r["restore"])
    assert d["status"] == "ok" and d["kind"] == "infrastructure" and d["by"] == "user_it_admin" and d["finished"]
    assert any("backup of the current state: ok" in line for line in d["log"]) and any("starting api" in line for line in d["log"])
    assert "token_sha" not in d and ops.list_restores()[0]["id"] == r["restore"]
    assert ops.active_restore() == {"active": False}
    assert ops.delete_restore(r["restore"]) == {"deleted": r["restore"]} and ops.list_restores() == []


def test_a_failed_restore_is_recorded_and_services_come_back(tmp_path, monkeypatch):
    ops, work, backups, calls, state = _ops(tmp_path, monkeypatch)
    m = ops._do_backup("nightly", "system", "scheduled", "0.12.0")
    class Fail:
        def __init__(self, *a, **k):
            import io
            self.stdout = io.StringIO("restore: database eaexplorer: restoring\npg_restore: error: boom\nrestore: FAILED: nothing was changed\n")

        def wait(self):
            return 1
    monkeypatch.setattr(ops.subprocess, "Popen", Fail)
    r = ops._do_restore(m["name"], "full", "x", "0.12.0")
    assert r["status"] == "failed" and "nothing was changed" in r["error"]
    d = ops.restore_detail(r["restore"])
    assert d["status"] == "failed" and any("pg_restore: error: boom" in line for line in d["log"])
    assert ops.maintenance() is None and state["api"] == "running" and state["keycloak"] == "running"


def test_follow_token_and_interrupted_restores(tmp_path, monkeypatch):
    ops, *_ = _ops(tmp_path, monkeypatch)
    rec, token = ops.new_restore("infrastructure", "x", "full", "it")
    assert ops.restore_detail(rec["id"], token=token)["id"] == rec["id"]
    with pytest.raises(PermissionError):
        ops.restore_detail(rec["id"], token="wrong")
    ops._set_maintenance(True, "Restoring x", "it")
    assert ops._block.acquire(blocking=False)    # running
    assert ops.active_restore()["active"] and ops.active_restore()["id"] == rec["id"]
    with pytest.raises(ValueError):
        ops.delete_restore(rec["id"])            # still running
    ops._block.release()
    ops.recover_after_restart()                  # the helper restarted in the middle
    assert ops.restore_detail(rec["id"])["status"] == "interrupted" and ops.maintenance() is None


def test_delete_backups_by_hand(tmp_path, monkeypatch):
    ops, *_ = _ops(tmp_path, monkeypatch)
    m = ops._do_backup("one", "x", "on-demand", "0.12.0")
    ops.pin_backup(m["name"], True)
    with pytest.raises(ValueError, match="pinned"):
        ops.delete_infra_backup(m["name"])
    ops.pin_backup(m["name"], False)
    assert ops.delete_infra_backup(m["name"]) == {"deleted": m["name"]} and ops.list_infra() == []


def test_a_cut_off_restore_does_not_lock_forever(tmp_path, monkeypatch):
    """D227: a restore marked running while nobody holds the lock (the helper or the eax command stopped) is settled, so
    the lock page goes and the restore can be run again."""
    ops, *_ = _ops(tmp_path, monkeypatch)
    rec, _ = ops.new_restore("infrastructure", "x", "full", "it")
    ops._set_maintenance(True, "Restoring x", "it")
    assert ops._block.acquire(blocking=False)          # while it runs, it is active
    assert ops.active_restore()["active"]
    ops._block.release()                               # it stopped without finishing
    assert ops.active_restore() == {"active": False}
    assert ops.restore_detail(rec["id"])["status"] == "interrupted" and ops.maintenance() is None


def test_restore_by_name_tag_or_latest(tmp_path, monkeypatch):
    ops, *_ = _ops(tmp_path, monkeypatch)
    a = ops._do_backup("nightly", "system", "scheduled", "0.12.0")["name"]
    time.sleep(1.05)
    b = ops._do_backup("Before upgrade", "x", "on-demand", "0.12.0")["name"]
    time.sleep(1.05)
    c = ops._do_backup("nightly", "system", "scheduled", "0.12.0")["name"]
    assert ops.resolve_backup("latest") == c and ops.resolve_backup("LATEST") == c
    assert ops.resolve_backup("nightly") == c                     # the newest with that tag
    assert ops.resolve_backup("Before upgrade") == b and ops.resolve_backup("Before-upgrade") == b
    assert ops.resolve_backup(a) == a                             # a full name as before
    with pytest.raises(FileNotFoundError):
        ops.resolve_backup("weekly")


def test_everyone_is_told_when_a_restore_starts(tmp_path, monkeypatch):
    ops, *_ = _ops(tmp_path, monkeypatch)
    sent = []

    class Answer:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self.body

    def urlopen(req, timeout=0):
        sent.append((req.full_url, req.headers.get("X-ops-token"), json.loads(req.data)))
        return Answer(b'{"notified": true}')
    import urllib.request
    m = ops._do_backup("nightly", "system", "scheduled", "0.12.0")
    r = ops._do_restore(m["name"], "db", "it", "0.12.0")             # the API cannot be reached: said in the log
    assert any("could not tell everyone now" in line for line in ops.restore_detail(r["restore"])["log"])
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    r = ops._do_restore(m["name"], "db", "it", "0.12.0")
    assert sent and sent[0][0].endswith("/api/v1/internal/restore-started") and sent[0][2] == {"restore": r["restore"]}
    assert any("everyone is told" in line for line in ops.restore_detail(r["restore"])["log"])


def test_a_backup_can_be_stopped(tmp_path, monkeypatch):
    ops, work, backups, calls, state = _ops(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        ops.stop_backup("it")                                       # nothing runs
    real = ops.subprocess.run

    def killed(args, **k):   # backup.sh is killed half way: someone asked to stop
        if len(args) > 3 and args[3] == "backup.sh":
            (backups / args[4] / "databases").mkdir(parents=True, exist_ok=True)
            (backups / ".stop").write_text("it_admin")
            return type("R", (), {"returncode": 143, "stdout": "", "stderr": "Terminated"})()
        return real(args, **k)
    monkeypatch.setattr(ops.subprocess, "run", killed)
    m = ops._do_backup("nightly", "system", "scheduled", "0.12.0")
    assert m["status"] == "stopped" and "it_admin" in m["error"]
    assert not (backups / "infrastructure" / m["name"]).exists() and not (backups / ".stop").exists()
    assert ops.list_infra() == []


def test_stop_asks_the_running_backups(tmp_path, monkeypatch):
    ops, work, backups, calls, state = _ops(tmp_path, monkeypatch)
    run = backups / "infrastructure" / "20261106T010000Z-nightly"
    run.mkdir(parents=True)
    (run / "manifest.json").write_text(json.dumps({"tag": "nightly", "status": "running", "created": "20261106T010000Z"}))
    app = backups / "application" / "20261106T020000Z-weekly"
    app.mkdir(parents=True)
    (app / "manifest.json").write_text(json.dumps({"tag": "weekly", "status": "running"}))
    assert ops._block.acquire(blocking=False)                      # a backup holds the lock
    try:
        out = ops.stop_backup("it_admin")["stopping"]
    finally:
        ops._block.release()
    assert run.name in out and any("weekly" in x for x in out)
    assert (backups / ".stop").read_text() == "it_admin" and (app / "STOP").exists()
    assert any("pkill -f backup.sh" in " ".join(c) for c in calls)
    (backups / ".stop").unlink()
    out = ops.stop_backup("it_admin")["stopping"]                  # nobody holds the lock: a leftover, deleted
    assert any("left unfinished" in x for x in out) and not run.exists()


def test_a_restore_cannot_be_stopped(tmp_path, monkeypatch):
    ops, *_ = _ops(tmp_path, monkeypatch)
    rec, _ = ops.new_restore("infrastructure", "x", "full", "it")
    with pytest.raises(ValueError, match="restore is running"):
        ops.stop_backup("it")


def test_the_maintenance_page_is_the_first_step(tmp_path, monkeypatch):
    ops, work, backups, calls, state = _ops(tmp_path, monkeypatch)
    m = ops._do_backup("nightly", "system", "scheduled", "0.12.0")
    seen = {}

    def tell(rec):        # everyone is told after the page is on
        seen["page"] = (work / "proxy" / "maintenance").exists()
    monkeypatch.setattr(ops, "_tell_everyone", tell)
    r = ops._do_restore(m["name"], "db", "it", "0.12.0")
    assert r["status"] == "ok" and seen["page"] and not (work / "proxy" / "maintenance").exists()
    log = ops.restore_detail(r["restore"])["log"]
    assert "maintenance page on" in log[0]
    r = ops._do_restore(m["name"], "db", "it", "0.0.1")           # refused (a newer backup): the page goes off again
    assert r["status"] == "failed" and not (work / "proxy" / "maintenance").exists() and ops.maintenance() is None
