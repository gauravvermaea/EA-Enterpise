"""R2.45 (owner, 12 Nov 2026: "do u test application backup and infra backup in your testing? If not it should be. Please
test it atleast in command line at the end of test as a last test") and R2.46 ("If we can not do reliable backups and
restores from web, then we should just show the command to run")."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]


def test_the_backup_suite_backs_up_restores_and_cleans_up(monkeypatch):
    from eax.testing import backups_check as bc
    monkeypatch.setattr(bc.time, "sleep", lambda s: None)
    monkeypatch.setattr(bc, "counts", lambda engine, guid: (12, 7))
    calls = []

    def call(base, method, path, token, body=None, timeout=60):
        calls.append((method, path))
        if method == "POST" and path.endswith("/admin/backups/infrastructure"):
            return 202, {"id": "t1"}
        if path.endswith("/verify"):
            return 202, {"id": "t2"}
        if path.endswith("/admin/backups/application"):
            return 202, {"id": "t3"}
        if path.endswith("/restore-model"):
            assert body["mode"] == "new" and body["new_name"] == "self_test_abc_4" and body["file"] == "m.eaxbackup.zip"
            return 202, {"id": "t4"}
        if path == "/api/v1/tasks/t1":
            return 200, {"done": True, "status": "done", "message": "made", "result": {"name": "INF"}}
        if path == "/api/v1/tasks/t2":
            return 200, {"done": True, "status": "done", "result": {"checks": [
                {"name": "checksums", "ok": True, "detail": "9 files"}, {"name": "database eaexplorer", "ok": True, "detail": "x"}]}}
        if path == "/api/v1/tasks/t3":
            return 200, {"done": True, "status": "done", "result": {"name": "APP"}}
        if path == "/api/v1/tasks/t4":
            return 200, {"done": True, "status": "done", "result": {"model": "NEW"}}
        if path == "/api/v1/admin/backups":
            return 200, {"application": {"runs": [{"name": "APP", "models": [{"file": "m.eaxbackup.zip"}]}]}}
        if path.endswith("/delete"):
            return 200, {}
        raise AssertionError(path)
    got, fixtures = [], []
    out = bc.run("http://x", "tok", {"model": "M", "sid": "abc"}, lambda n, o, d="", ms=0: got.append((n, o)),
                 lambda m: None, None, 7, lambda k, i, n: fixtures.append((k, i, n)), call=call)
    assert out == {"passed": 6, "failed": 0}
    assert [n for n, _ in got] == ["backup: an infrastructure backup", "backup: trial restore: checksums",
                                   "backup: trial restore: database eaexplorer", "backup: an application backup of the test model",
                                   "backup: the test model restored from its backup", "backup: the test's backups removed"]
    assert fixtures == [("model", "NEW", "self_test_abc_4")]                     # the restored model is purged with the run
    assert ("POST", "/api/v1/admin/backups/infrastructure/INF/delete") in calls and \
        ("POST", "/api/v1/admin/backups/application/APP/delete") in calls        # nothing left behind (D593)


def test_a_failed_backup_is_a_failed_check(monkeypatch):
    from eax.testing import backups_check as bc
    monkeypatch.setattr(bc.time, "sleep", lambda s: None)

    def call(base, method, path, token, body=None, timeout=60):
        if path.endswith("/infrastructure"):
            return 202, {"id": "t1"}
        if path == "/api/v1/tasks/t1":
            return 200, {"done": True, "status": "failed", "message": "files reports could not be read: ./x: Permission denied"}
        return 409, {"message": "no"}
    got = []
    bc.run("http://x", "tok", {}, lambda n, o, d="", ms=0: got.append((n, o, d)), lambda m: None, None, 7,
           lambda *a: None, call=call)
    assert got == [("backup: an infrastructure backup", "failed", "files reports could not be read: ./x: Permission denied")]


def test_backup_is_the_last_suite_of_a_full_test_and_eax_test_backup():
    from eax.testing import SUITES
    assert SUITES[-1] == "backup"
    run = (REPO / "services/api/eax/testing/run.py").read_text()
    assert run.index('if "backup" in suites:') > run.index('if "security" in suites:')
    ops = (REPO / "services/ops/testruns.py").read_text()
    assert 'SUITES = ("api", "ui", "db", "security", "backup")' in ops
    sys.path.insert(0, str(REPO))
    from eaxcli import commands as C
    assert C.check_argv(["test", "backup"]) == ["test", "backup"]


@pytest.mark.skipif(not shutil.which("sh") or not shutil.which("sha256sum"), reason="needs a POSIX shell")
def test_verify_sh_reports_each_check(tmp_path):
    root = tmp_path / "backups"
    b = root / "infrastructure" / "X"
    (b / "databases").mkdir(parents=True)
    (b / "files").mkdir()
    (b / "databases" / "eaexplorer.dump").write_text("dump")
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("a")
    subprocess.run(["tar", "-C", str(src), "-czf", str(b / "files" / "tls.tar.gz"), "."], check=True)
    subprocess.run("find . -type f ! -name SHA256SUMS | sed 's|^./||' | sort | xargs sha256sum > SHA256SUMS", shell=True, cwd=b, check=True)
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "psql").write_text("#!/bin/sh\necho 40\n")
    (bin_ / "restore.sh").write_text("#!/bin/sh\necho restore: ok\n")
    for f in bin_.iterdir():
        f.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}", "EAX_BACKUP_ROOT": str(root), "EAX_RESTORE_SH": str(bin_ / "restore.sh")}
    r = subprocess.run(["sh", str(REPO / "services/backup/verify.sh"), "infrastructure/X"], capture_output=True, text=True, env=env)
    lines = [x.split("\t") for x in r.stdout.splitlines() if x.startswith("CHECK")]
    assert [(x[1], x[2]) for x in lines] == [("checksums", "ok"), ("files tls", "ok"), ("database eaexplorer", "ok")], r.stdout
    assert r.returncode == 0
    (b / "files" / "tls.tar.gz").write_text("damaged")                        # changed since it was written
    r = subprocess.run(["sh", str(REPO / "services/backup/verify.sh"), "infrastructure/X"], capture_output=True, text=True, env=env)
    lines = {x.split("\t")[1]: x.split("\t")[2] for x in r.stdout.splitlines() if x.startswith("CHECK")}
    assert lines["checksums"] == "failed" and lines["files tls"] == "failed" and r.returncode == 1


@pytest.mark.skipif(not shutil.which("sh") or not shutil.which("sha256sum"), reason="needs a POSIX shell")
def test_verify_sh_works_with_busybox_sha256sum(tmp_path):
    """Full self-test, 13 Nov 2026: "backup: trial restore: checksums" failed with "sha256sum: unrecognized option:
    quiet": the backup image is Alpine, whose BusyBox sha256sum has no long options. verify.sh uses plain -c."""
    real = shutil.which("sha256sum")
    b = tmp_path / "backups" / "infrastructure" / "X"
    (b / "databases").mkdir(parents=True)
    (b / "databases" / "eaexplorer.dump").write_text("dump")
    subprocess.run(f"find . -type f ! -name SHA256SUMS | sed 's|^./||' | sort | xargs {real} > SHA256SUMS", shell=True, cwd=b, check=True)
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "sha256sum").write_text("#!/bin/sh\nfor a in \"$@\"; do case \"$a\" in --*) echo \"sha256sum: unrecognized option: ${a#--}\" >&2;"
                                    f" exit 1;; esac; done\nexec {real} \"$@\"\n")
    (bin_ / "psql").write_text("#!/bin/sh\necho 40\n")
    (bin_ / "restore.sh").write_text("#!/bin/sh\necho restore: ok\n")
    for f in bin_.iterdir():
        f.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}", "EAX_BACKUP_ROOT": str(tmp_path / "backups"),
           "EAX_RESTORE_SH": str(bin_ / "restore.sh")}
    r = subprocess.run(["sh", str(REPO / "services/backup/verify.sh"), "infrastructure/X"], capture_output=True, text=True, env=env)
    checks = {x.split("\t")[1]: x.split("\t")[2:] for x in r.stdout.splitlines() if x.startswith("CHECK")}
    assert checks["checksums"][0] == "ok", r.stdout
    (b / "databases" / "eaexplorer.dump").write_text("changed")
    r = subprocess.run(["sh", str(REPO / "services/backup/verify.sh"), "infrastructure/X"], capture_output=True, text=True, env=env)
    checks = {x.split("\t")[1]: x.split("\t")[2:] for x in r.stdout.splitlines() if x.startswith("CHECK")}
    assert checks["checksums"][0] == "failed" and "eaexplorer.dump" in checks["checksums"][1]
    assert "unrecognized" not in checks["checksums"][1]


def test_the_helper_reads_verify_lines():
    spec = importlib.util.spec_from_file_location("ops_r245", REPO / "services" / "ops" / "ops.py")
    src = (REPO / "services" / "ops" / "ops.py").read_text()
    assert 're.match(r"^/backups/([A-Za-z0-9._-]+)/verify$", self.path)' in src
    ns: dict = {}
    exec(src[src.index("def parse_checks"):src.index("def verify_backup")], ns)   # the parser alone
    assert ns["parse_checks"]("x\nCHECK\tchecksums\tok\t3 files\nCHECK\tdatabase a\tfailed\tno\n") == [
        {"name": "checksums", "ok": True, "detail": "3 files"}, {"name": "database a", "ok": False, "detail": "no"}]
    assert spec is not None


def test_the_backups_page_disables_its_buttons_with_the_reason_until_the_web_is_proven():
    """R2.62 (owner, 13 Nov 2026): "dont hide these buttons diable them with reason. We should be able to override the
    diable as a user". Every backup and restore button is always shown; until a self-test proves them it is disabled,
    its tooltip says why, the commands are offered, and "Use them anyway" enables them and is audited."""
    page = (REPO / "services/web/src/Backups.jsx").read_text()
    assert "proven &&" not in page                                          # nothing is hidden any more
    assert "function WebNotProven" in page and page.count("<WebNotProven gate={gate}") == 2
    assert '<button className="primary" disabled={!ready || !data.on || st.busy} title={why} onClick={backupNow}>Back up now</button>' in page
    assert '<button className="primary" disabled={!ready} title={why} onClick={backupNow}>Back up every model and project now</button>' in page
    assert page.count("disabled={!ready") >= 6 and page.count("title={why}") >= 5   # backups, restores, restore all
    assert "Use them anyway" in page and '"/api/v1/admin/backups/override"' in page
    assert "const ready = proven || override;" in page
    api = (REPO / "services/api/eax/api/backups.py").read_text()
    assert "def web_proven(conn)" in api and '"web": proven' in api and "x.suite = 'backup'" in api
    assert '@blp.route("/admin/backups/override")' in api and '_audit("backup.web_override"' in api and "return record_override(" in api


def test_using_the_buttons_anyway_is_in_the_audit_trail(monkeypatch):
    try:
        from eax.api import backups as B
    except ImportError as exc:                       # only where Flask is a stub; the test runner has the real one
        pytest.skip(f"needs Flask: {exc}")
    seen = []
    monkeypatch.setattr(B, "_audit", lambda *a: seen.append(a))
    assert B.record_override("1 of 12 backup checks failed.") == {"recorded": True}
    assert B.record_override(None) == {"recorded": True}
    assert seen == [("backup.web_override", "backup", "web", {"why": "1 of 12 backup checks failed."}),
                    ("backup.web_override", "backup", "web", {"why": ""})]
