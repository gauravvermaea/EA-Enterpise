"""Settings that survive resets (D558), scheduled eax commands (D559), the banner (D558) and the reset-survival test
(D561). Docker, eaxpy and the operations helper are fakes; the reset is the real cleanup code path on a temporary
installation folder."""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from eaxcli import banner as B  # noqa: E402
from eaxcli import commands as C  # noqa: E402
from eaxcli import main as M  # noqa: E402
from eaxcli import persist as P  # noqa: E402
from eaxcli import reset_survival as RS  # noqa: E402
from eaxcli import schedules as S  # noqa: E402

TZ = ZoneInfo("Africa/Johannesburg")
SUPER, IT = ["super-admin"], ["it-admin"]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("EAX_PERSIST_DIR", raising=False)
    monkeypatch.setenv("EAX_TIMEZONE", "Africa/Johannesburg")


def _install(tmp: Path) -> Path:
    (tmp / "work" / "logs").mkdir(parents=True)
    (tmp / "work" / "eaexplorer.env").write_text("EAX_INSTALLATION_NAME=demo-laptop\nEAX_DEPLOYMENT=laptop\n", encoding="utf-8")
    (tmp / "work" / "backups" / "infrastructure").mkdir(parents=True)
    return tmp


def _reset(root: Path, monkeypatch) -> int:
    """What clean-restart does to the folders: the real `cleanup --all --yes` (no config file: no docker), then init."""
    monkeypatch.setattr(M, "WORK", root / "work")
    monkeypatch.setattr(M, "ENV_FILE", root / "work" / "eaexplorer.env")
    (root / "work" / "eaexplorer.env").rename(root / "work" / "env.old")        # no compose 'down' in a test
    M.cleanup(["--all", "--yes"])
    (root / "work" / "eaexplorer.env").write_text("EAX_INSTALLATION_NAME=demo-laptop\nEAX_DEPLOYMENT=laptop\n", encoding="utf-8")
    return 0


# ---------------------------------------------------------------- the persist/ files
def test_writes_are_atomic_and_a_broken_file_falls_back_to_its_last_good_copy(tmp_path):
    f = tmp_path / "persist" / "x.json"
    P.write_json(f, {"version": 1, "a": 1})
    P.write_json(f, {"version": 1, "a": 2})
    assert json.loads(f.read_text())["a"] == 2 and json.loads((f.parent / "x.json.bak").read_text())["a"] == 1
    assert not list(f.parent.glob("*.tmp*"))                       # nothing half-written left behind
    f.write_text("{ not json", encoding="utf-8")                     # edited by hand, badly
    data, warn = P.read_json(f, {"a": 0})
    assert data["a"] == 1 and "last good copy" in warn
    P.write_json(f, {"version": 1, "a": 3})                          # a bad file never becomes the .bak
    assert json.loads((f.parent / "x.json.bak").read_text())["a"] == 1
    (f.parent / "x.json.bak").unlink()
    f.write_text("[]", encoding="utf-8")
    data, warn = P.read_json(f, {"a": 0})
    assert data == {"a": 0} and "no good copy" in warn
    with pytest.raises(TypeError):
        P.write_json(f, {"a": object()})                             # never writes what would not read back


def test_persist_is_outside_work_and_configurable(tmp_path, monkeypatch):
    root = _install(tmp_path)
    assert P.folder(root) == root / "persist"
    (root / "work" / "eaexplorer.env").write_text("EAX_PERSIST_DIR=/srv/eax-persist\n", encoding="utf-8")
    assert P.folder(root) == Path("/srv/eax-persist")
    gi = (REPO / ".gitignore").read_text(encoding="utf-8")
    assert "\npersist/\n" in gi
    compose = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    assert "${EAX_PERSIST_DIR:-./persist}:/eax-persist" in compose and "${EAX_PERSIST_DIR:-./persist}:/persist" in compose


# ---------------------------------------------------------------- cron and presets
def test_cron_next_runs_and_words():
    at = datetime(2026, 11, 10, 22, 50, tzinfo=TZ)
    assert S.next_after("0 2 * * *", at) == datetime(2026, 11, 11, 2, 0, tzinfo=TZ)
    assert S.next_after("30 6 * * 1", at) == datetime(2026, 11, 16, 6, 30, tzinfo=TZ)       # the next Monday
    assert S.next_after("15 * * * *", at) == datetime(2026, 11, 10, 23, 15, tzinfo=TZ)
    assert S.next_after("*/20 9-17 * * 1-5", at) == datetime(2026, 11, 11, 9, 0, tzinfo=TZ)
    assert S.next_after("0 0 1 1 *", at) == datetime(2027, 1, 1, 0, 0, tzinfo=TZ)
    assert S.describe({"cron": "0 2 * * *"}) == "every day at 02:00"
    assert S.describe({"cron": "30 6 * * 1"}) == "every Monday at 06:30"
    assert S.describe({"cron": "15 * * * *"}) == "every hour at :15"
    assert S.describe({"once_at": "2026-12-01T09:00"}) == "once at 2026-12-01 09:00"
    assert S.preset("weekly", "07:45", day=0) == {"cron": "45 7 * * 0"}
    for bad in ("0 2 * *", "61 2 * * *", "0 2 * * 9", "x 2 * * *"):
        with pytest.raises(S.ScheduleError):
            S.parse(bad)
    with pytest.raises(S.ScheduleError):
        S.preset("nightly", "25:00")


# ---------------------------------------------------------------- making schedules
def test_a_schedule_is_checked_like_a_command_and_a_wipe_needs_the_strong_confirm_once(tmp_path):
    root = _install(tmp_path)
    s = S.make({"name": "Nightly backup", "argv": ["backup", "nightly"], "preset": {"kind": "nightly", "time_": "01:30"}},
               "it_admin", IT, "demo-laptop", root)
    assert s["cron"] == "30 1 * * *" and s["enabled"] and not s["wipe"] and s["when"] == "every day at 01:30"
    for bad, why in [(["init"], "machine itself"), (["console"], "machine itself"), (["logs", "api"], "keeps going"),
                     (["ls"], "not an eax command"), (["backup", "a;b"], "not allowed")]:
        with pytest.raises((S.ScheduleError, C.Refused), match=why):
            S.make({"name": f"x{bad[0]}", "argv": bad, "cron": "0 3 * * *"}, "it_admin", IT, "demo-laptop", root)
    with pytest.raises(C.Refused):                                    # a wipe: Super Admins only
        S.make({"name": "Reset", "argv": ["clean-restart", "laptop"], "cron": "0 2 * * *",
                "confirm": {"typed": "demo-laptop", "understood": True}}, "it_admin", IT, "demo-laptop", root)
    with pytest.raises(C.Refused, match="installation's name"):
        S.make({"name": "Reset", "argv": ["clean-restart", "laptop"], "cron": "0 2 * * *",
                "confirm": {"typed": "demo", "understood": True}}, "su", SUPER, "demo-laptop", root)
    d = S.demo_reset("su", SUPER, "demo-laptop", "demo-laptop", True, root=root)
    assert d["argv"] == ["clean-restart", "laptop"] and d["cron"] == "0 2 * * *" and d["wipe"] and not d["backup_first"]
    assert d["banner"] and d["confirmed"]["installation"] == "demo-laptop"
    with pytest.raises(S.ScheduleError, match="on already"):
        S.demo_reset("su", SUPER, "demo-laptop", "demo-laptop", True, root=root)
    S.change(d["id"], "off", "su", SUPER, root)
    again = S.demo_reset("su", SUPER, "demo-laptop", "demo-laptop", True, at="03:15", root=root)   # off: turned on again
    assert again["id"] == d["id"] and again["enabled"] and again["cron"] == "15 3 * * *"
    with pytest.raises(C.Refused):                                   # turning a wipe schedule off: Super Admins too
        S.change(d["id"], "off", "it_admin", IT, root)
    assert not S.change(d["id"], "off", "su", SUPER, root)["enabled"]
    S.change(d["id"], "on", "su", SUPER, root)
    on_disk = json.loads((root / "persist" / "schedules.json").read_text())
    assert on_disk["version"] == 1 and "_comment" in on_disk and len(on_disk["schedules"]) == 2


def test_tick_starts_what_is_due_skips_what_was_missed_and_waits_while_busy(tmp_path):
    root = _install(tmp_path)
    s = S.make({"name": "Nightly backup", "argv": ["backup", "nightly"], "cron": "0 2 * * *"}, "it", IT, "demo-laptop", root)
    S._set(s["id"], "checked", "2026-11-10T22:00:00+02:00", root)
    started = []
    start = lambda x: started.append(x["id"]) or "run-1"  # noqa: E731
    assert S.tick(start, lambda: False, root, now=datetime(2026, 11, 11, 1, 59, tzinfo=TZ)) == []
    out = S.tick(start, lambda: False, root, now=datetime(2026, 11, 11, 2, 0, 20, tzinfo=TZ))
    assert out == [{"id": s["id"], "what": "started", "run": "run-1"}] and started == [s["id"]]
    assert S.tick(start, lambda: False, root, now=datetime(2026, 11, 11, 2, 1, tzinfo=TZ)) == []      # once only
    # the machine was off over the next 02:00 and comes back at 04:30: skipped, recorded
    out = S.tick(start, lambda: False, root, now=datetime(2026, 11, 12, 4, 30, tzinfo=TZ))
    assert out[0]["what"] == "skipped-missed" and "not running" in S.find(s["id"], root)["last"]["note"]
    # back at 02:40 the night after: within the hour, so it still runs once
    out = S.tick(start, lambda: False, root, now=datetime(2026, 11, 13, 2, 40, tzinfo=TZ))
    assert out[0]["what"] == "started"
    # busy: waits, then is skipped after 30 minutes
    t0 = datetime(2026, 11, 14, 2, 0, 10, tzinfo=TZ)
    assert S.tick(start, lambda: True, root, now=t0)[0]["what"] == "waiting"
    assert S.tick(start, lambda: True, root, now=t0 + timedelta(minutes=10)) == []
    assert S.tick(start, lambda: True, root, now=t0 + timedelta(minutes=31))[0]["what"] == "skipped-busy"
    once = S.make({"name": "Once", "argv": ["status"], "preset": {"kind": "once", "at": "2026-11-20T09:00"}}, "it", IT, "demo-laptop", root)
    assert S.tick(start, lambda: False, root, now=datetime(2026, 11, 20, 9, 0, 30, tzinfo=TZ))[-1]["what"] == "started"
    assert not S.find(once["id"], root)["enabled"]


# ---------------------------------------------------------------- the banner
def test_no_banner_shows_nothing_and_a_banner_keeps_to_its_times_and_audience(tmp_path):
    root = _install(tmp_path)
    assert B.current(root) is None                                    # no file: nothing is shown
    b = B.set_banner({"text": "Upgrade on Saturday", "level": "notice", "link": "javascript:alert(1)",
                      "starts": "2026-11-10T08:00", "ends": "2026-11-12T08:00"}, "it_admin", root=root)
    assert b["level"] == "notice" and b["by"] == "it_admin"
    assert B.current(root, now=datetime(2026, 11, 9, 12, 0, tzinfo=TZ)) is None
    now = B.current(root, now=datetime(2026, 11, 11, 12, 0, tzinfo=TZ))
    assert now["text"] == "Upgrade on Saturday" and not now["link_safe"]          # shown as text, never run
    assert B.current(root, now=datetime(2026, 11, 12, 8, 0, tzinfo=TZ)) is None
    B.set_banner({"text": "Admins: reset tonight", "audience": "admins", "link": "#/admin/commands"}, "su", root=root)
    assert B.current(root) is None and B.current(root, admin=True)["link_safe"]
    for bad in ({"text": ""}, {"text": "x", "level": "red"}, {"text": "x", "starts": "2026-11-12T08:00", "ends": "2026-11-11T08:00"}):
        with pytest.raises(ValueError):
            B.set_banner(bad, "su", root=root)
    assert B.clear("su", root) and B.current(root, admin=True) is None and not B.clear("su", root)
    hist = B.load(root)[0]["history"]
    assert [h["what"] for h in hist] == ["set", "set", "cleared"]
    B.set_banner({"text": "x"}, "su", source="schedule:abc123", root=root)
    assert not B.clear("su", root, source="schedule:zzz") and B.clear("su", root, source="schedule:abc123")


# ---------------------------------------------------------------- surviving a reset
def test_a_reset_deletes_work_but_persist_survives_byte_for_byte_and_comes_back(tmp_path, monkeypatch):
    root = _install(tmp_path)
    (root / "work" / "logs" / "eax.log").write_text("log", encoding="utf-8")
    d = S.demo_reset("su", SUPER, "demo-laptop", "demo-laptop", True, root=root)
    B.set_banner({"text": S.banner_text(d)}, "su", source=f"schedule:{d['id']}", root=root)
    (root / "persist" / "safety-backups" / "20261110T2200Z-safety-x").mkdir(parents=True)
    (root / "persist" / "safety-backups" / "20261110T2200Z-safety-x" / "manifest.json").write_text("{}", encoding="utf-8")
    before = {p: p.read_bytes() for p in (root / "persist").rglob("*") if p.is_file()}
    assert _reset(root, monkeypatch) == 0
    assert not (root / "work" / "logs").exists() and not (root / "work" / "backups").exists()       # work/ emptied
    assert {p: p.read_bytes() for p in (root / "persist").rglob("*") if p.is_file()} == before     # persist/ intact
    # what the operations helper reads at start-up: the schedules and the banner are back for the screens
    listing = S.listing(root, now=datetime(2026, 11, 10, 23, 0, tzinfo=TZ))
    demo = next(s for s in listing["schedules"] if s["id"] == d["id"])
    assert demo["enabled"] and demo["when"] == "every day at 02:00" and demo["next"].endswith("T02:00+02:00")
    assert demo["next"][:10] >= datetime.now(TZ).strftime("%Y-%m-%d")         # the next 02:00, whenever the test runs
    assert "resets every day at 02:00" in B.current(root)["text"]
    # and the nightly reset still fires after the reset
    S._set(d["id"], "checked", "2026-11-10T23:00:00+02:00", root)
    fired = S.tick(lambda s: "run-n", lambda: False, root, now=datetime(2026, 11, 11, 2, 0, 30, tzinfo=TZ))
    assert fired == [{"id": d["id"], "what": "started", "run": "run-n"}]


def test_the_reset_survival_test_passes_when_persist_survives_and_fails_when_it_does_not(tmp_path, monkeypatch):
    root = _install(tmp_path)
    B.set_banner({"text": "Kept"}, "su", root=root)
    (root / "work" / "eaexplorer.env.self-test-marker").write_text("x", encoding="utf-8")
    rec = RS.run(root, lambda: _reset(root, monkeypatch), lambda: True, log=lambda t: None, run_id="r1", strict=True)
    assert rec["state"] == "passed", rec["checks"]
    assert not any(s.get("name") == "self_test_r1" for s in S.load(root)[0])            # markers removed after
    assert "self_test_marker" not in B.load(root)[0] and B.current(root)["text"] == "Kept"
    assert RS.history(root)[0]["id"] == "r1"
    # a reset that also deleted persist/ (what this test is for): the test says so
    root2 = _install(tmp_path / "two")

    def bad_reset():
        import shutil
        shutil.rmtree(root2 / "persist" / "schedules.json", ignore_errors=True)
        (root2 / "persist" / "schedules.json").unlink(missing_ok=True)
        return _reset(root2, monkeypatch)
    (root2 / "work" / "eaexplorer.env.self-test-marker").write_text("x", encoding="utf-8")
    rec = RS.run(root2, bad_reset, lambda: True, log=lambda t: None, run_id="r2", strict=True)
    assert rec["state"] == "failed" and any(c["result"] == "failed" and "marker schedule" in c["name"] for c in rec["checks"])


def test_reset_survival_is_a_wipe_command_for_super_admins_with_the_strong_confirm():
    argv = C.check_argv(["test", "--reset-survival"])
    assert C.kind_of_argv(argv) == "wipe" and C.kind_of_argv(["test", "--smoke"]) == "run"
    with pytest.raises(C.Refused):
        C.allowed_argv(argv, IT)
    C.allowed_argv(argv, SUPER)
    with pytest.raises(C.Refused):
        C.check_confirm(argv, "nope", "demo-laptop", True)
    C.check_confirm(argv, "demo-laptop", "demo-laptop", True)
    assert RS.main(REPO, ["--confirm", "wrong-name"]) == 2               # from the command line: asks for the name


# ---------------------------------------------------------------- the operations helper (docker a fake)
def _ops(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("ops_commandcentre_j", REPO / "services" / "ops" / "commandcentre.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    calls = []
    m.hooks.update(docker=lambda *a: calls.append(a) or "", me=lambda: {"project": "eax", "image": "eaexplorer/ops:dev",
                                                                         "install": "/opt/eaexplorer"},
                   read_config=lambda: ["EAX_INSTALLATION_NAME=demo-laptop", "EAX_TIMEZONE=Africa/Johannesburg"],
                   tickets={}, tlock=threading.Lock(), idle_minutes=lambda: 15)
    monkeypatch.setattr(m, "RUNS", str(tmp_path / "commands"))
    monkeypatch.setenv("EAX_PERSIST_DIR", str(tmp_path / "persist"))
    return m, calls


def test_the_helper_schedules_runs_and_announces_the_demo_reset(tmp_path, monkeypatch):
    m, calls = _ops(tmp_path, monkeypatch)
    s = m.schedule_add({"demo": True, "by": "su", "roles": SUPER, "confirm": {"typed": "demo-laptop", "understood": True}})
    assert s["wipe"] and "resets every day at 02:00" in m.banner_now(False)["banner"]["text"]
    lst = m.schedules_list()
    assert lst["schedules"][0]["name"] == "Demo reset every night" and lst["installation"] == "demo-laptop"
    out = m.schedule_change(s["id"], "run", {"by": "su", "roles": SUPER})
    create = calls[0]
    assert create[0] == "create" and "eaxcli.cmdrun" in create and out["id"] in create and "sh" not in create
    assert "EAX_SCHEDULE=" + s["id"] in create and "EAX_SAFETY_BACKUP=0" in create and out["id"].find(f"sched{s['id']}") > 0
    assert "EAX_PERSIST_DIR=/opt/eaexplorer/persist" in create and create[-2:] == ("clean-restart", "laptop")
    with pytest.raises(C.Refused):
        m.schedule_change(s["id"], "run", {"by": "it", "roles": IT})
    m.schedule_change(s["id"], "remove", {"by": "su", "roles": SUPER})
    assert m.banner_now(True)["banner"] is None                       # its banner went with it
    assert m.schedules_list()["schedules"] == []
    assert m.seed_persist("laptop") == 0                               # the file exists now: never seeded over
    (tmp_path / "persist" / "schedules.json").unlink()
    assert m.seed_persist("laptop") == 4 and len(m.schedules_list()["schedules"]) == 4
    assert m.banner_now(True)["banner"] is None and m.banner_all()["history"]   # a past banner, none showing


def test_busy_ignores_console_sessions(tmp_path, monkeypatch):
    m, _ = _ops(tmp_path, monkeypatch)
    m.hooks["docker"] = lambda *a: "console-20261110\n"
    assert not m.busy()
    m.hooks["docker"] = lambda *a: "console-20261110\n20261110T2300Z-backup-ab12\n"
    assert m.busy()


def test_the_screens_and_the_routes_are_wired():
    app = (REPO / "services" / "api" / "eax" / "app.py").read_text(encoding="utf-8")
    assert "from .api.banner import blp as banner_blp" in app
    cc = (REPO / "services" / "api" / "eax" / "api" / "command_centre.py").read_text(encoding="utf-8")
    assert '"/schedules"' in cc and '"/reset-survival"' in cc
    web = REPO / "services" / "web" / "src"
    assert "<AdminBanner />" in (web / "App.jsx").read_text(encoding="utf-8")
    assert '["banner", "Banner"' in (web / "Admin.jsx").read_text(encoding="utf-8")
    assert '["schedules", "Schedules"]' in (web / "CommandCentre.jsx").read_text(encoding="utf-8")
    # the reset-survival test is command line only since R2.0.1 (D592: the Self-test page has Smoke or Full only)
    assert "--reset-survival" in (REPO / "eaxcli" / "main.py").read_text(encoding="utf-8")
