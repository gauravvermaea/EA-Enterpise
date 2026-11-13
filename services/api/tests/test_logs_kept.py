"""R2.30 (back up and clean the logs; the default level by deployment), R2.31 (the logs of each container on the web),
R2.32 (logs written to a mounted disk): eaxcli/logkeep.py, shared by eax and the operations helper."""

from __future__ import annotations

import os
import sys
import time
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))


def test_ship_writes_each_line_once_to_its_day_masked(tmp_path):
    from eaxcli import logkeep as K
    lines = {"c1": ["2026-11-12T23:59:59.000000001Z api started",
                    "2026-11-13T00:00:01.000000002Z ERROR db password=s3cret failed",
                    "2026-11-13T00:00:02.000000003Z GET /x Authorization: Bearer abcdefghijklmnop"]}
    asked = []

    def read_since(cid, since):
        asked.append(since)
        return lines[cid]
    out = K.ship(tmp_path, [{"id": "c1", "service": "api"}], read_since, now=1794528000)
    assert out == {"api": 3}
    day12 = (tmp_path / "containers/api/2026-11-12.log").read_text()
    day13 = (tmp_path / "containers/api/2026-11-13.log").read_text()
    assert "api started" in day12 and "password=****" in day13 and "s3cret" not in day13 and "Bearer ****" in day13
    assert K.ship(tmp_path, [{"id": "c1", "service": "api"}], read_since) == {"api": 0}     # nothing twice
    assert asked[-1].startswith("2026-11-13T00:00:02")


def test_read_merges_filters_and_pages(tmp_path):
    from eaxcli import logkeep as K
    for svc, rows in (("api", ["2026-11-13T09:00:00Z info a", "2026-11-13T09:30:00Z ERROR b req-42"]),
                      ("db", ["2026-11-13T09:15:00Z WARNING c", "2026-11-13T11:00:00Z debug d"])):
        f = tmp_path / "containers" / svc / "2026-11-13.log"
        f.parent.mkdir(parents=True)
        f.write_text("\n".join(rows) + "\n")
    got = K.read(tmp_path, ["api", "db"], "2026-11-13")
    assert [x["line"].split()[2] for x in got["lines"]] == ["a", "c", "b", "d"] and got["total"] == 4    # merged by time
    assert [x["level"] for x in K.read(tmp_path, ["api", "db"], "2026-11-13", level="warning")["lines"]] == ["warning", "error"]
    assert K.read(tmp_path, ["api"], "2026-11-13", q="REQ-42")["total"] == 1                      # a request id
    assert K.read(tmp_path, ["api", "db"], "2026-11-13", since="09:10", until="10:00")["total"] == 2
    assert K.read(tmp_path, ["api", "db"], "2026-11-13", size=3, page=1)["lines"][0]["line"].endswith(" d")
    assert [f["service"] for f in K.files(tmp_path)] == ["db", "api"] or len(K.files(tmp_path)) == 2


def test_backup_and_clean(tmp_path):
    from eaxcli import logkeep as K
    base, own, zips = tmp_path / "logs", tmp_path / "work/logs", tmp_path / "work/backups/logs"
    for d, name in ((base / "containers/api", "2026-10-01.log"), (base / "containers/api", "2026-11-13.log"), (own, "up.log")):
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text("x\n")
    out = K.backup(base, own, zips, "Before Upgrade!")
    assert out["files"] == 3 and out["file"].endswith("-logs-beforeupgrade.zip")
    assert sorted(zipfile.ZipFile(zips / out["file"]).namelist()) == ["containers/api/2026-10-01.log",
                                                                     "containers/api/2026-11-13.log", "eax/up.log"]
    old = time.time() - 40 * 86400
    os.utime(own / "up.log", (old, old))
    os.utime(zips / out["file"], (old, old))
    gone = K.clean(base, own, zips, 30, now=time.mktime((2026, 11, 13, 12, 0, 0, 0, 0, -1)))["deleted"]
    assert gone == sorted(["containers/api/2026-10-01.log", "work/logs/up.log", f"backups/logs/{out['file']}"])
    assert (base / "containers/api/2026-11-13.log").exists() and K.clean(base, own, zips, 0)["deleted"] == []


def test_the_command_line(tmp_path, monkeypatch, capsys):
    from eaxcli import logkeep as K
    from eaxcli import logs_cli
    monkeypatch.setattr(logs_cli, "ROOT", tmp_path)
    monkeypatch.setenv("EAX_LOGS_DIR", str(tmp_path / "logs"))
    (tmp_path / "logs/containers/api").mkdir(parents=True)
    (tmp_path / "logs/containers/api/2020-01-01.log").write_text("x\n")
    assert logs_cli.main(["backup"]) == 0 and "work/backups/logs/" in capsys.readouterr().out
    assert logs_cli.main(["clean", "--older-than", "7"], ask=lambda _q: "no") == 1
    assert logs_cli.main(["clean", "--older-than", "7", "--yes"]) == 0
    assert not (tmp_path / "logs/containers/api/2020-01-01.log").exists()
    assert K.default_keep_days("laptop") == 14 and K.default_keep_days("server") == 90


def test_level_and_keep_days_default_by_deployment(monkeypatch):
    from eax import settings as st
    monkeypatch.setenv("EAX_DEPLOYMENT", "laptop")
    assert st.default_of("log_level") == "DEBUG" and st.default_of("logs_keep_days") == 14
    monkeypatch.setenv("EAX_DEPLOYMENT", "server")
    assert st.default_of("log_level") == "ERROR" and st.default_of("logs_keep_days") == 90
    assert st.default_of("upload_max_mb") == st.REGISTRY["upload_max_mb"][3]


def test_wired_everywhere():
    sh, ps1, main = (REPO / "eax.sh").read_text(), (REPO / "eax.ps1").read_text(), (REPO / "eaxcli/main.py").read_text()
    assert 'logs) case "${2:-}" in backup|clean) exec "$BASH" ./eaxpy.sh' in sh
    assert '$Command -eq "logs" -and $RestArgs.Count -gt 0 -and $RestArgs[0] -in @("backup", "clean")' in ps1
    assert "logs_cli.main(rest)" in main
    assert "$ {eax} logs clean --older-than 30 --yes" in (REPO / "eaxcli/help.txt").read_text()
    ops = (REPO / "services/ops/ops.py").read_text()
    assert "logsops.start()" in ops and '"/logs/files", "/logs/read"' in ops and '"/logs/backup", "/logs/clean"' in ops
    assert "${EAX_LOGS_DIR:-./logs}:/eax-logs" in (REPO / "docker-compose.yml").read_text()
    admin = (REPO / "services/api/eax/api/admin.py").read_text()
    assert '"/admin/logs/read"' in admin and '"/admin/logs/<any(backup, clean):what>"' in admin
    assert '"eax.logs_clean"' in (REPO / "services/api/eax/jobs.py").read_text()
    web = (REPO / "services/web/src/ContainerConsole.jsx").read_text()
    assert "function KeptLogs" in web and "/api/v1/admin/logs/read" in web and "Live" in web


def test_eax_logs_and_backups_are_read_like_a_container(tmp_path):
    """R2.31: eax's own logs and the log backups open in the same viewer, a page at a time, secrets masked."""
    from eaxcli import logkeep as K
    own, zips = tmp_path / "work/logs", tmp_path / "work/backups/logs"
    own.mkdir(parents=True)
    (own / "eax-up.log").write_text("starting\nERROR password=hunter2 failed\n")
    base = tmp_path / "logs"
    (base / "containers/api").mkdir(parents=True)
    (base / "containers/api/2026-11-13.log").write_text("2026-11-13T01:00:00Z hello\n")
    z = K.backup(base, own, zips)["file"]
    listed = K.own_files(own, zips)
    assert [f["name"] for f in listed["own"]] == ["eax-up.log"] and [f["name"] for f in listed["backups"]] == [z]
    got = K.read_own(own, "eax-up.log", q="error")
    assert got["total"] == 1 and "hunter2" not in got["lines"][0]["line"] and got["lines"][0]["level"] == "error"
    assert sorted(K.read_backup(zips, z)["members"]) == ["containers/api/2026-11-13.log", "eax/eax-up.log"]
    assert K.read_backup(zips, z, "containers/api/2026-11-13.log")["lines"][0]["line"].endswith("hello")
    for bad in ("../x.log", "x.txt"):
        with pytest.raises(ValueError):
            K.read_own(own, bad)
    with pytest.raises(ValueError):
        K.read_backup(zips, "../evil.zip")


def test_a_log_backup_before_every_reset_and_update():
    """R2.30: cleanup (and so clean-restart) and an update first back the logs up where no reset deletes them."""
    from eaxcli import logkeep as K
    assert K.kept_backups(Path("/x/logs")) == Path("/x/logs/backups")
    assert '"$BASH" ./eaxpy.sh logs backup before-cleanup --outside-work' in (REPO / "eax.sh").read_text()
    assert 'logs backup before-cleanup --outside-work' in (REPO / "eax.ps1").read_text()
    assert 'logkeep.backup(base, WORK / "logs", logkeep.kept_backups(base), "before-cleanup")' in (REPO / "eaxcli/main.py").read_text()
    assert '"before-update")' in (REPO / "services/ops/updates.py").read_text()
    web = (REPO / "services/web/src/ContainerConsole.jsx").read_text()
    assert "function OwnLogs" in web and "/api/v1/admin/logs/own" in web
