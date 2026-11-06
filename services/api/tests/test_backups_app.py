"""Application and model backups (phase 8.4, D216): files, listing, pinning, clean-up, paths, routes."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from eax import backups as bk
from eax.metamodel_edit import EditError

ROOT = Path(__file__).resolve().parents[1]
MODEL = "0fe348ab-dab9-5f58-87d7-97b5a0f4f27b"


def _file(created: str, why: str = "x", kind: str = "project") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("backup.json", json.dumps({"format": bk.FORMAT, "created": created, "by": "u", "why": why, "version": "0.12.0",
                                              "model": {"id": MODEL, "name": "Fynbos Life", "kind": kind},
                                              "counts": {"entities": 3, "relationships": 1}}))
        z.writestr("package.zip", b"")
    return buf.getvalue()


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("EAX_BACKUP_MOUNT", str(tmp_path))
    return tmp_path


def test_model_backups_are_kept_newest_and_pinned(store):
    d = store / "application" / "models" / MODEL
    d.mkdir(parents=True)
    names = []
    for i in range(4):
        n = f"2026110{i}T010000Z-b{i}{bk.SUFFIX}"
        (d / n).write_bytes(_file(f"2026110{i}T010000Z", f"b{i}"))
        names.append(n)
    bk.pin("model", "", names[0], MODEL, True)
    gone = bk.cleanup(2)
    assert sorted(gone) == [f"{MODEL}/{names[1]}"]
    left = [b["file"] for b in bk.list_model(MODEL)]
    assert set(left) == {names[0], names[2], names[3]} and left[0] == names[3]      # newest first
    assert next(b for b in bk.list_model(MODEL) if b["file"] == names[0])["pinned"]


def test_application_runs_listed_cleaned_and_pinned(store):
    for i in range(4):
        run = store / "application" / f"2026110{i}T010000Z-run{i}"
        (run / "models").mkdir(parents=True)
        f = f"Fynbos-Life-0fe348ab{bk.SUFFIX}"
        (run / "models" / f).write_bytes(_file(f"2026110{i}T010000Z"))
        (run / "manifest.json").write_text(json.dumps({"tag": f"run{i}", "created": f"2026110{i}T010000Z", "status": "ok", "by": "it",
                                                       "models": [{"id": MODEL, "name": "Fynbos Life", "file": f, "status": "ok"}]}))
    bk.pin("application", "20261100T010000Z-run0", "", "", True)
    assert bk.cleanup(2) == ["20261101T010000Z-run1"]
    runs = bk.list_application()["runs"]
    assert [r["tag"] for r in runs] == ["run3", "run2", "run0"] and runs[2]["pinned"]   # pinned ones are not counted
    mine = bk.list_model(MODEL)
    assert {m["run"] for m in mine} == {"20261103T010000Z-run3", "20261102T010000Z-run2", "20261100T010000Z-run0"}
    assert mine[0]["why"] == "run3"


def test_paths_stay_inside_the_backup_folder(store):
    for where, name, file in (("application", "../etc", f"x{bk.SUFFIX}"), ("application", "run", "../../x.zip"),
                              ("uploaded", "", "passwd"), ("model", "", f"..{bk.SUFFIX}")):
        with pytest.raises(EditError):
            bk.path_of(where, name, file, MODEL)


def test_uploads_must_be_model_backups(store):
    out = bk.store_upload(_file("20261106T010000Z"), "Fynbos.eaxbackup.zip")
    assert out["model"]["name"] == "Fynbos Life" and bk.list_application()["uploaded"][0]["file"] == out["file"]
    with pytest.raises(EditError):
        bk.store_upload(b"not a zip", "evil.eaxbackup.zip")
    assert len(list((store / "application" / "uploaded").glob(f"*{bk.SUFFIX}"))) == 1


def test_human_dates():
    assert bk.human("20261106T072704Z") == "2026-11-06 07:27 UTC"


def test_routes_and_permissions():
    src = (ROOT / "eax" / "api" / "backups.py").read_text()
    for route in ('"/admin/backups"', '"/admin/backups/infrastructure"', '"/admin/backups/infrastructure/<name>/restore"',
                  '"/admin/backups/application"', '"/admin/backups/upload"'):
        i = src.index(f"@blp.route({route})")
        assert 'require_auth("system.operate")' in src[i:i + 500], route
    assert 'confirm") or "") != "RESTORE"' in src
    i = src.index('@blp.route("/models/<model>/backups")')
    assert "may_back_up" in src[i:i + 1500]
    tasks = (ROOT / "eax" / "tasks.py").read_text()
    for k in ("backup.infrastructure", "backup.application", "backup.model", "backup.restore"):
        assert f'"{k}"' in tasks
    jobs = (ROOT / "eax" / "jobs.py").read_text()
    assert "eax.backup_scheduler" in jobs and "eax.record_backup_events" in jobs
    assert 'require_auth("system.operate")' in src[src.index('"/admin/backups/schedules/<kind>"'):][:500]
    app = (ROOT / "eax" / "app.py").read_text()
    assert "_maintenance" in app and "503" in app


def test_schedules_in_words_and_matching():
    from datetime import datetime

    from eax import backup_schedule as bs
    assert bs.describe("0 1 * * *") == "every day at 01:00" and bs.describe("30 2 * * 0") == "every Sunday at 02:30"
    assert bs.matches("0 1 * * *", datetime(2026, 11, 6, 1, 0)) and not bs.matches("0 1 * * *", datetime(2026, 11, 6, 1, 1))
    assert bs.matches("0 2 * * 0", datetime(2026, 11, 8, 2, 0)) and not bs.matches("0 2 * * 0", datetime(2026, 11, 6, 2, 0))
    assert bs.matches("*/15 8-17 * * 1-5", datetime(2026, 11, 6, 9, 45)) and not bs.matches("*/15 8-17 * * 1-5", datetime(2026, 11, 7, 9, 45))
    assert bs.matches("0 3 1 * *", datetime(2026, 12, 1, 3, 0))
    for bad in ("every night", "0 25 * * *", "61 1 * * *", "0 1 * *", "0 1 * * 9"):
        with pytest.raises(EditError):
            bs.parse(bad)


def test_nothing_about_backups_in_the_config_templates():
    for kind in ("laptop", "server"):
        text_ = (ROOT.parents[1] / "deploy" / "templates" / f"eaexplorer.{kind}.env").read_text()
        assert "EAX_BACKUP_SCHEDULE" not in text_ and "EAX_BACKUP_KEEP" not in text_ and "EAX_BACKUP_MAX_AGE" not in text_


def _run(store, name="20261106T010000Z-quarter", status="ok"):
    run = store / "application" / name
    (run / "models").mkdir(parents=True)
    f = f"Fynbos-Life-0fe348ab{bk.SUFFIX}"
    (run / "models" / f).write_bytes(_file("20261106T010000Z"))
    (run / "manifest.json").write_text(json.dumps({"format": bk.APP_FORMAT, "tag": "quarter", "created": "20261106T010000Z",
                                                   "status": status, "by": "it",
                                                   "models": [{"id": MODEL, "name": "Fynbos Life", "file": f, "status": "ok"}]}))
    return run


def test_a_whole_application_backup_downloads_and_uploads(store):
    _run(store)
    z = bk.application_zip("20261106T010000Z-quarter")
    assert z.name == "20261106T010000Z-quarter.eaxapp.zip"
    with zipfile.ZipFile(z) as zz:
        assert sorted(zz.namelist()) == ["manifest.json", f"models/Fynbos-Life-0fe348ab{bk.SUFFIX}"]
    out = bk.store_application_upload(z, z.name)
    assert out["models"] == 1 and out["tag"] == "quarter" and "-uploaded-quarter" in out["run"]
    up = next(r for r in bk.list_application()["runs"] if r["name"] == out["run"])
    assert up["uploaded"] and up["models"][0]["status"] == "ok"
    assert bk.path_of("application", out["run"], up["models"][0]["file"]).is_file()
    bad = store / "bad.zip"
    with zipfile.ZipFile(bad, "w") as zz:
        zz.writestr("manifest.json", json.dumps({"format": "something else"}))
    with pytest.raises(EditError):
        bk.store_application_upload(bad, "bad.zip")
    with pytest.raises(EditError):
        bk.application_zip("../etc")


def test_a_running_application_backup_can_be_stopped(store):
    run = _run(store, status="running")
    _run(store, "20261105T010000Z-done")
    assert bk.stop_application("it_admin") == [run.name]
    assert (run / "STOP").read_text() == "it_admin" and not (store / "application" / "20261105T010000Z-done" / "STOP").exists()
    with pytest.raises(EditError):
        bk.application_zip(run.name)          # still running


def test_stop_and_whole_application_routes():
    src = (ROOT / "eax" / "api" / "backups.py").read_text()
    for route in ('"/admin/backups/stop"', '"/admin/backups/application/<name>/download"',
                  '"/admin/backups/application/<name>/restore-all"'):
        i = src.index(f"@blp.route({route})")
        assert 'require_auth("system.operate")' in src[i:i + 600], route
    i = src.index('"/admin/backups/application/<name>/restore-all"')
    assert "SUPER_ADMIN" in src[i:i + 1200] and "RESTORE" in src[i:i + 1200]
    assert '"backup.restore_all"' in (ROOT / "eax" / "tasks.py").read_text()
    assert "eax.announce_restores" in (ROOT / "eax" / "jobs.py").read_text()
    i = src.index('"/internal/restore-started"')
    assert "X-Ops-Token" in src[i:i + 900] and "compare_digest" in src[i:i + 900]
