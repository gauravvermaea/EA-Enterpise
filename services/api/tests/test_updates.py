"""Updates (phase 36, D417, D510 to D516): channels, forward only, one release at a time, retry, roll back, schedule.

Everything runs against a local bare git repository made here, with tags on release (v0.18.0, v0.19.0, v0.20.0), rc
(v0.20.0-rc.1, v0.21.0-rc.1) and commits on main; docker compose, the operations helper and the API are fakes.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from eaxcli import releases as R  # noqa: E402
from eaxcli import updater as U  # noqa: E402

pytestmark = pytest.mark.skipif(not shutil.which("git"), reason="git is not installed")


def sh(*args, cwd):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


def commit(work: Path, version: str, msg: str, notes: str | None = None) -> None:
    (work / "services" / "api").mkdir(parents=True, exist_ok=True)
    (work / "services" / "api" / "version.toml").write_text(f'version = "{version}"\n')
    (work / "docker-compose.yml").write_text(f"# {version}\n")
    if notes:
        (work / "releases").mkdir(exist_ok=True)
        (work / "releases" / f"{version}.md").write_text(notes)
    if version == "0.20.0":
        (work / "new-in-0.20.txt").write_text("new file\n")
    (work / "CHANGES.txt").write_text(msg + "\n")
    sh("add", "-A", cwd=work)
    sh("commit", "-q", "-m", msg, cwd=work)


@pytest.fixture()
def origin(tmp_path):
    """A bare repository with the three channels."""
    bare, work = tmp_path / "origin.git", tmp_path / "author"
    sh("init", "-q", "--bare", str(bare), cwd=tmp_path)
    sh("init", "-q", "-b", "main", str(work), cwd=tmp_path)
    for v, notes in [("0.18.0", "# 0.18.0\nBatch 2."), ("0.19.0", "# 0.19.0\nThe last set."),
                     ("0.20.0-rc.1", None), ("0.20.0", "# 0.20.0\nThe twentieth."), ("0.21.0-rc.1", "# 0.21.0-rc.1\nTrying.")]:
        commit(work, v, f"version {v}", notes)
        sh("tag", f"v{v}", cwd=work)
    commit(work, "0.21.0", "main: after the rc")
    commit(work, "0.21.0", "main: another change")
    sh("branch", "release", "v0.20.0", cwd=work)
    sh("branch", "rc", "v0.21.0-rc.1", cwd=work)
    sh("push", "-q", str(bare), "main", "release", "rc", "--tags", cwd=work)
    return str(bare)


# ---------------------------------------------------------------- versions
def test_versions_sort_and_compare():
    assert R.newer("0.20.0", "0.20.0-rc.3") and R.newer("0.20.0-rc.2", "0.20.0-rc.1") and R.newer("0.20.0", "0.19.9")
    assert not R.newer("0.19.0", "0.19.0") and not R.newer("nonsense", "0.1.0")
    assert R.base("0.20.0-rc.2") == "0.20.0" and R.is_rc("v0.20.0-rc.2")


def test_each_channel_offers_only_newer_versions_with_notes(origin, tmp_path):
    prod = R.available(origin, "prod", {"version": "0.18.0"}, tmp_path / "c")
    assert [v.version for v in prod] == ["0.19.0", "0.20.0"]                  # no RCs, nothing at or below 0.18.0
    assert prod[-1].notes.startswith("# 0.20.0") and prod[-1].date
    rc = R.available(origin, "rc", {"version": "0.19.0"}, tmp_path / "c")
    assert [v.version for v in rc] == ["0.20.0-rc.1", "0.20.0", "0.21.0-rc.1"]
    assert rc[1].notes.startswith("# 0.20.0") and rc[2].notes.startswith("# 0.21.0-rc.1")
    assert R.available(origin, "prod", {"version": "0.20.0"}, tmp_path / "c") == []   # forward only


def test_latest_offers_commits_after_the_installed_one(origin, tmp_path):
    cache = tmp_path / "c"
    every = R.available(origin, "latest", {"version": "0.19.0", "commit": ""}, cache)
    assert len(every) == 1 and every[0].title == "main: another change"     # installed commit unknown: the newest only
    rc_commit = R.tags(origin)["v0.21.0-rc.1"]
    after = R.available(origin, "latest", {"version": "0.21.0-rc.1", "commit": rc_commit}, cache)
    assert [v.title for v in after] == ["main: after the rc", "main: another change"]
    assert "Commits since" in after[-1].notes


def test_plan_goes_one_release_at_a_time(origin, tmp_path):
    offered = R.available(origin, "rc", {"version": "0.18.0"}, tmp_path / "c")
    pick = R.plan(offered, "0.21.0-rc.1")
    assert pick.steps == ["v0.19.0", "v0.20.0", "v0.21.0-rc.1"]               # 0.20.0's RC skipped: its release is offered
    assert R.plan(offered).version == "0.21.0-rc.1"
    with pytest.raises(R.ReleaseError):
        R.plan(offered, "0.17.0")                                           # never backwards
    with pytest.raises(R.ReleaseError):
        R.plan([], "")


def test_export_writes_one_versions_files(origin, tmp_path):
    sha = R.export(origin, "v0.19.0", tmp_path / "out")
    assert len(sha) == 40 and '"0.19.0"' in (tmp_path / "out" / "services" / "api" / "version.toml").read_text()


def test_the_support_policy_is_the_same_in_the_api():
    sys.path.insert(0, str(REPO / "services" / "api"))
    from eax import releases_policy as P
    rel = ["0.17.0", "0.18.0", "0.18.1", "0.19.0", "0.20.0-rc.1"]
    for v in ["0.17.0", "0.18.1", "0.19.0", "0.20.0-rc.1", "0.19.0-rc.2", "0.21.0", "x"]:
        assert P.supported(v, rel) == R.supported(v, rel), v
    assert R.supported("0.17.0", rel)[0] is False and R.supported("0.18.0", rel)[0] is True
    assert R.supported("0.19.0-rc.2", rel)[0] is False                      # its release is out


# ---------------------------------------------------------------- the updater
class FakeEnv(U.Env):
    def __init__(self, root, fail_builds=0, fail_health_at=""):
        super().__init__(root, "eaxtest")
        self.calls, self.fail_builds, self.fail_health_at = [], fail_builds, fail_health_at
        self.backups, self.restores = [], []

    def compose(self, args, log=None, timeout=3600):
        self.calls.append(args[0])
        if args[0] == "build" and self.fail_builds:
            self.fail_builds -= 1
            raise U.UpdateError("docker compose build failed (exit 1)")

    def ops(self, method, path, body=None, timeout=30):
        if path == "/backups/backup":
            name = f"2026-backup-{len(self.backups) + 1}"
            self.backups.append((name, body))
            self._last = name
            return {"started": True}
        if path == "/backups":
            return {"state": {"busy": False, "result": {"status": "ok", "name": getattr(self, "_last", "")}}}
        if path == "/backups/restore":
            self.restores.append(body)
            return {"restore": "r1"}
        if path.startswith("/restores/"):
            return {"status": "ok"}
        raise AssertionError(path)

    def heartbeat(self):
        toml = (self.root / "services" / "api" / "version.toml").read_text()
        v = toml.split('"')[1]
        if v == self.fail_health_at:
            return {"version": "old", "versions_match": False, "status": "warning"}
        return {"version": v, "versions_match": True, "status": "ok"}

    def sleep(self, s):
        pass


@pytest.fixture()
def install(origin, tmp_path):
    """An installation: a git checkout at v0.18.0 with a local change and its work folder."""
    root = tmp_path / "install"
    subprocess.run(["git", "clone", "-q", origin, str(root)], check=True)
    sh("checkout", "-q", "--detach", "v0.18.0", cwd=root)
    (root / "work").mkdir()
    (root / "work" / "eaexplorer.env").write_text("EAX_DEPLOYMENT=laptop\n")
    (root / "docker-compose.yml").write_text("# 0.18.0 with a local change\n")
    (root / "library" / "templates").mkdir(parents=True)
    (root / "library" / "templates" / "mine.docx").write_text("the owner's file")
    return root


def request(u, origin, steps, to, uid="u1"):
    req = {"id": uid, "by": "user_it_admin", "channel": "rc", "to": to, "url": origin, "steps": steps}
    U.write_json(u.dir / uid / "request.json", req)
    return req


def test_an_update_backs_up_then_goes_one_release_at_a_time(install, origin):
    env = FakeEnv(install)
    u = U.Updater(env)
    out = u.start(request(u, origin, ["v0.19.0", "v0.20.0"], "0.20.0"))
    assert out["status"] == "ok" and [s["status"] for s in out["steps"]] == ["ok", "ok"]
    assert env.backups[0][1]["pinned"] and env.backups[0][1]["version"] == "0.18.0"
    assert env.calls == ["build", "up", "build", "up"]
    inst = json.loads((u.dir / "installed.json").read_text())
    assert inst["version"] == "0.20.0" and inst["ref"] == "v0.20.0"
    assert not (install / "work" / "maintenance.json").exists() and not u.current_path.exists()
    hist = json.loads((u.dir / "history.json").read_text())
    assert hist[-1]["status"] == "ok" and hist[-1]["from"]["version"] == "0.18.0"
    code = json.loads((u.dir / "u1" / "code.json").read_text())
    assert "docker-compose.yml" in code["local_changes"]                    # local changes kept in the backup
    assert (install / "library" / "templates" / "mine.docx").exists()


def test_a_failed_step_stops_and_retry_carries_on(install, origin):
    env = FakeEnv(install, fail_builds=1)
    u = U.Updater(env)
    out = u.start(request(u, origin, ["v0.19.0", "v0.20.0"], "0.20.0"))
    assert out["status"] == "failed" and "Step 1" in out["error"]
    assert (install / "work" / "maintenance.json").exists()                 # the maintenance page stays on
    assert json.loads(u.current_path.read_text())["status"] == "failed"
    with pytest.raises(U.UpdateError):
        U.Updater(env).start(request(u, origin, ["v0.20.0"], "0.20.0", uid="u2"))   # one at a time
    out = U.Updater(env).retry("user_super_admin")
    assert out["status"] == "ok" and json.loads((u.dir / "installed.json").read_text())["version"] == "0.20.0"


def test_rollback_puts_back_the_code_and_the_backup(install, origin):
    env = FakeEnv(install, fail_health_at="0.20.0")
    U.HEALTH_MINUTES = 0
    u = U.Updater(env)
    out = u.start(request(u, origin, ["v0.19.0", "v0.20.0"], "0.20.0"))
    assert out["status"] == "failed" and (install / "new-in-0.20.txt").exists()
    out = U.Updater(env).rollback("user_it_admin")
    assert out["status"] == "rolled-back" and out["failed_version"] == "0.20.0"
    assert '"0.18.0"' in (install / "services" / "api" / "version.toml").read_text()
    assert (install / "docker-compose.yml").read_text() == "# 0.18.0 with a local change\n"   # local change back
    assert not (install / "new-in-0.20.txt").exists()                       # files the newer version added: gone
    assert (install / "library" / "templates" / "mine.docx").exists()       # never touched
    assert env.restores[0]["name"] == "2026-backup-1" and env.restores[0]["what"] == "full"
    assert env.restores[0]["version"] == "0.18.0"
    assert json.loads((u.dir / "failed-versions.json").read_text()) == ["0.20.0"]
    assert not (install / "work" / "maintenance.json").exists()
    U.HEALTH_MINUTES = 20


def test_a_backup_that_fails_changes_nothing(install, origin):
    env = FakeEnv(install)
    env.ops = lambda *a, **k: (_ for _ in ()).throw(U.UpdateError("the backup container is not running"))
    u = U.Updater(env)
    out = u.start(request(u, origin, ["v0.19.0"], "0.19.0"))
    assert out["status"] == "not-started" and env.calls == []
    assert '"0.18.0"' in (install / "services" / "api" / "version.toml").read_text()
    assert not (install / "work" / "maintenance.json").exists()


def test_a_folder_that_is_not_a_git_checkout_is_updated_from_the_version_files(install, origin):
    shutil.rmtree(install / ".git")
    env = FakeEnv(install)
    u = U.Updater(env)
    assert u.start(request(u, origin, ["v0.19.0"], "0.19.0"))["status"] == "ok"
    assert '"0.19.0"' in (install / "services" / "api" / "version.toml").read_text()
    assert (install / "work" / "eaexplorer.env").exists() and (install / "library" / "templates" / "mine.docx").exists()


# ---------------------------------------------------------------- the operations helper: schedule
def _ops_updates(tmp_path, monkeypatch):
    monkeypatch.setenv("EAX_WORK_MOUNT", str(tmp_path / "work"))
    monkeypatch.setenv("EAX_REPO_MOUNT", str(REPO))
    spec = importlib.util.spec_from_file_location("ops_updates", REPO / "services" / "ops" / "updates.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_a_scheduled_update_starts_when_its_time_comes(tmp_path, monkeypatch):
    m = _ops_updates(tmp_path, monkeypatch)
    started = []
    monkeypatch.setattr(m, "_launch", lambda ch, pick, by, rid="": started.append((ch, pick.steps, by, rid)))
    at = (datetime.now(UTC) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    m._write("scheduled.json", {"id": "s1", "channel": "prod", "to": "0.20.0", "ref": "v0.20.0",
                                "steps": ["v0.19.0", "v0.20.0"], "at": at, "by": "user_it_admin"})
    assert m.scheduler_tick() == "waiting" and not started
    assert m.scheduler_tick(now=datetime.now(UTC).timestamp() + 7200) == "started"
    assert started == [("prod", ["v0.19.0", "v0.20.0"], "user_it_admin", "s1")]
    assert m._read("scheduled.json") is None


def test_times_are_read_plainly(tmp_path, monkeypatch):
    m = _ops_updates(tmp_path, monkeypatch)
    assert m._parse_at("23:59").endswith("Z")
    later = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    assert m._parse_at(later).startswith(later[:10])
    with pytest.raises(ValueError):
        m._parse_at("2020-01-01T10:00")
    with pytest.raises(ValueError):
        m._parse_at("tonight")


def test_the_container_scripts_are_quoted(tmp_path, monkeypatch):
    m = _ops_updates(tmp_path, monkeypatch)
    cmd = m._shell("/srv/eax", "abc", "updater", ["run", "--id", "abc", "--by", "o'neil"])
    assert "cp -r eaxcli work/updates/abc/runner/" in cmd and "'o'\\''neil'" in cmd


# ---------------------------------------------------------------- the API's copy of the history
def test_history_rows_are_mapped_safely():
    sys.path.insert(0, str(REPO / "services" / "api"))
    from eax import updates as up
    r = up._row({"id": "u1", "status": "weird", "channel": "nightly", "from": {"version": "0.18.0", "commit": "abc"},
                 "to": "0.19.0", "started": "2026-11-10T20:00:00Z", "steps": [{"ref": "v0.19.0", "status": "ok"}]})
    assert r["status"] == "failed" and r["channel"] == "prod" and r["from_version"] == "0.18.0"
    assert r["started_at"].year == 2026 and json.loads(r["steps"])[0]["ref"] == "v0.19.0"


def test_the_migration_and_the_backup_cover_the_history():
    sql = (REPO / "services" / "api" / "migrations" / "sql" / "0044_updates.sql").read_text()
    assert "core.update_history" in sql and "'0.19.0'" in sql
