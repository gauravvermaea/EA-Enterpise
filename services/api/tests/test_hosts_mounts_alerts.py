"""Release 2: the Docker engine (R2.16), the mounts (R2.17), a file explorer in each container (R2.18) and alerts when a
container is not working (R2.19), all in the operations helper (services/ops/hostwatch.py) and read through the API."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
WEB = REPO / "services" / "web" / "src"


@pytest.fixture()
def hw(tmp_path, monkeypatch):
    sys.path.insert(0, str(REPO / "services" / "ops"))
    spec = importlib.util.spec_from_file_location("hostwatch_r216", REPO / "services" / "ops" / "hostwatch.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.STATE_FILE = str(tmp_path / "alerts.json")
    mod.HISTORY_FILE = str(tmp_path / "history.jsonl")
    mod.hooks.update(values=lambda: {}, console_on=lambda: True, token="t")
    return mod


# ---------------------------------------------------------------- R2.16 the engine
def test_cpu_memory_and_levels(hw):
    assert hw.cpu_percent("cpu  100 0 100 800 0 0 0 0\n") is None          # the first look has nothing to compare
    assert hw.cpu_percent("cpu  200 0 200 1600 0 0 0 0\n") == 20.0          # 200 busy of 1000
    m = hw.meminfo("MemTotal:  1000 kB\nMemAvailable:  250 kB\n")
    assert m == {"MemTotal": 1024000, "MemAvailable": 256000}
    assert [hw.level(v, 80, 90) for v in (10, 85, 95, None)] == ["green", "amber", "red", "unknown"]
    assert hw.thresholds()["disk"] == {"warn": 80, "alert": 90}
    hw.hooks["values"] = lambda: {"EAX_HOST_WARN_CPU": "50"}
    assert hw.thresholds()["cpu"]["warn"] == 50


def test_the_host_summary_and_its_history(hw):
    hw.hooks.update(
        docker=lambda *a, **k: json.dumps({"Name": "laptop", "NCPU": 8, "ServerVersion": "29.0", "MemTotal": 8e9,
                                           "ContainersRunning": 12, "Containers": 14}) if a[0] == "info" else "2.30",
        stats=lambda fresh=False: {"containers": [{"key": "api", "state": "running", "cpu_percent": 3.5, "memory_bytes": 4e8},
                                                  {"key": "db", "state": "running", "cpu_percent": 1.5, "memory_bytes": 6e8}],
                                   "filesystems": [{"path": "/", "used_percent": 95.0}], "docker_disk": []},
        filesystems=lambda: [], host_cpus=lambda: 8)
    h = hw.host(sample=True)
    assert h["name"] == "laptop" and h["cpus"] == 8 and h["eax_memory_bytes"] == 1e9 and h["eax_cpu_percent"] == 5.0
    assert h["levels"]["disk"] == "red" and h["shares"][0]["service"] == "db"
    assert len(hw._history()) == 1 and hw._history()[0]["disk"] == 95.0


# ---------------------------------------------------------------- R2.17 the mounts
def test_mounts_are_grouped_and_a_read_only_work_folder_is_a_warning(hw):
    inspected = [{"Id": "aaa111111111", "State": {"Running": True}, "Mounts": [
                     {"Type": "bind", "Source": "/host/work", "Destination": "/eax-work", "RW": False},
                     {"Type": "volume", "Name": "eax_db", "Source": "/var/lib/docker/volumes/eax_db", "Destination": "/data", "RW": True},
                     {"Type": "bind", "Source": "/var/run/docker.sock", "Destination": "/var/run/docker.sock", "RW": True}]},
                 {"Id": "bbb222222222", "State": {"Running": True}, "Mounts": [
                     {"Type": "volume", "Name": "eax_db", "Destination": "/var/lib/postgresql/data", "RW": True}]}]
    hw.hooks.update(containers=lambda: [{"id": "aaa111111111", "service": "ops", "key": "ops"},
                                        {"id": "bbb222222222", "service": "db", "key": "db"}],
                    docker=lambda *a, **k: json.dumps(inspected), volume_sizes=lambda: {"eax_db": 5000})
    out = hw.mounts()["mounts"]
    assert [m["source"] for m in out] == ["eax_db", "/host/work"]               # volumes first; Docker's socket left out
    db = out[0]
    assert db["bytes"] == 5000 and {u["service"] for u in db["used_by"]} == {"ops", "db"} and not db["warnings"]
    assert "must be writable" in out[1]["warnings"][0]


def test_a_mount_is_looked_into_read_only(hw):
    calls = []
    hw.hooks.update(me_image=lambda: "eaexplorer/ops:dev",
                    docker=lambda *a, **k: calls.append(a) or json.dumps({"files": 2, "bytes": 10, "disk_total": 100, "disk_free": 5,
                                                                          "largest": [], "newest": [], "oldest": [], "folders": []}))
    hw.mounts = lambda: {"mounts": [{"id": "abc123abc123", "source": "eax_db", "warnings": []}]}
    out = hw.probe("abc123abc123", "summary")
    assert "eax_db:/m:ro" in calls[0] and "--network" in calls[0] and "none" in calls[0]
    assert out["files"] == 2 and "nearly full" in out["warnings"][0]
    with pytest.raises(FileNotFoundError):
        hw.probe("ffffffffffff", "summary")


# ---------------------------------------------------------------- R2.18 a file explorer in each container
def test_what_is_never_written_or_shown(hw):
    assert hw.write_check("ops", "/app/ops.py") == "The operations helper's own files are read only."
    for p in ("/run/secrets/db", "/var/run/docker.sock", "/root/.ssh/id_rsa", "/proc/1/environ", "/x/credentials"):
        assert hw.write_check("api", p), p
        assert hw.hidden(p) or p.startswith("/proc"), p
    assert "database's data folder" in hw.write_check("db", "/var/lib/postgresql/data/pg_hba.conf")
    assert hw.write_check("db", "/var/lib/postgresql/data/pg_hba.conf", "database") == ""
    assert hw.write_check("api", "/tmp/notes.txt") == ""
    assert hw._clean("a/../../etc") == "/etc"


def test_an_edit_is_refused_when_the_file_changed_and_a_delete_needs_its_path(hw, monkeypatch):
    import hashlib
    import io
    import tarfile
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        info = tarfile.TarInfo("notes.txt")
        info.size = 3
        t.addfile(info, io.BytesIO(b"old"))
    written = []
    monkeypatch.setattr(hw, "_cid", lambda s: "c1")
    monkeypatch.setattr(hw, "_cp_out", lambda cid, p: buf.getvalue())
    monkeypatch.setattr(hw, "_cp_in", lambda cid, folder, files: written.append((folder, files)))
    monkeypatch.setattr(hw, "_exec", lambda cid, *cmd, **k: written.append(cmd) or "")
    with pytest.raises(ValueError, match="changed since you opened it"):
        hw.files_change("api", {"op": "write", "path": "/tmp/notes.txt", "content": "new", "sha256": "x" * 64})
    out = hw.files_change("api", {"op": "write", "path": "/tmp/notes.txt", "content": "new",
                                  "sha256": hashlib.sha256(b"old").hexdigest()})
    assert out["before"] == "old" and out["after"] == "new" and written[-1] == ("/tmp", {"notes.txt": b"new"})
    with pytest.raises(ValueError, match="confirm with the full path"):
        hw.files_change("api", {"op": "delete", "path": "/tmp/notes.txt"})
    hw.files_change("api", {"op": "delete", "path": "/tmp/notes.txt", "confirm_path": "/tmp/notes.txt"})
    assert written[-1] == ("rm", "-rf", "--", "/tmp/notes.txt")
    with pytest.raises(PermissionError):
        hw.files_change("ops", {"op": "mkdir", "path": "/app/x"})
    hw.hooks["console_on"] = lambda: False
    with pytest.raises(PermissionError, match="EAX_CONTAINER_CONSOLE=off"):
        hw.files_list("api", "/")


def test_a_linked_folder_opens_and_shows_what_is_in_it(hw, monkeypatch, tmp_path):
    """R2.60 (owner, 13 Nov 2026): "double click on a folder at root level, there is no folders inside it". /bin, /lib
    and /sbin are links to /usr/... on most images: find was given the link itself, listed nothing, and the link was not
    marked as a folder. The real command runs here against a folder holding a link to a folder."""
    import subprocess
    real = tmp_path / "usr" / "bin"
    (real / "deeper").mkdir(parents=True)
    (real / "tool").write_text("x")
    (tmp_path / "bin").symlink_to(real)
    (tmp_path / "notes.txt").write_text("hi")
    monkeypatch.setattr(hw, "_cid", lambda s: "c1")
    monkeypatch.setattr(hw, "_exec", lambda cid, *cmd, **k: subprocess.run(list(cmd), capture_output=True, text=True).stdout)
    hw.hooks["docker"] = lambda *a, **k: json.dumps([{"Mounts": []}])
    top = {e["name"]: e for e in hw.files_list("api", str(tmp_path))["entries"]}
    assert top["bin"]["dir"] and top["bin"]["link"] and top["usr"]["dir"] and not top["notes.txt"]["dir"]
    inside = hw.files_list("api", str(tmp_path / "bin"))["entries"]
    assert [(e["name"], e["dir"]) for e in inside] == [("deeper", True), ("tool", False)]
    assert all(e["path"].startswith(str(tmp_path / "bin") + "/") for e in inside)
    assert hw.files_list("api", str(tmp_path / "usr"))["entries"][0]["path"] == str(tmp_path / "usr" / "bin")
    assert '"cp", "-L"' in (REPO / "services" / "ops" / "hostwatch.py").read_text()   # a linked file opens too


def test_the_files_tab_is_an_explorer_view():
    """R2.58 and R2.60 (owner, 13 Nov 2026): "Fix it with the Windows explorer view": a folder tree on the left, the
    folder's contents on the right, double click opens, a File menu, Back / Forward / Up and the path."""
    fx = (WEB / "FileExplorer.jsx").read_text()
    assert 'role="tree"' in fx and "<TreeNode" in fx and "onDoubleClick={() => openItem(f)}" in fx
    assert 'role="menubar"' in fx and ">File</button>" in fx
    for label in ("New folder", "Upload...", '"Open"', "Rename", "Move to...", "Copy to...", "Delete", "Refresh"):
        assert label in fx, label
    assert 'aria-label="Back"' in fx and 'aria-label="Forward"' in fx and 'aria-label="Up"' in fx
    assert "export function crumbs(p)" in fx and 'e.key === "Enter"' in fx
    cc = (WEB / "ContainerConsole.jsx").read_text()
    assert "<FileExplorer service={service}" in cc and "function Files(" not in cc
    assert ".fx-panes" in (WEB / "styles.css").read_text()


# ---------------------------------------------------------------- R2.19 alerts
ROWS = [{"key": "api", "service": "api", "state": "running", "health": "healthy", "restarts": 0},
        {"key": "setup", "service": "setup", "state": "exited", "exit_code": 0},
        {"key": "reports", "service": "reports", "state": "exited", "exit_code": 137, "status": "Exited (137)"},
        {"key": "web", "service": "web", "state": "running", "health": "unhealthy"},
        {"key": "db", "service": "db", "state": "running", "oom_killed": True}]


def test_what_counts_as_not_working(hw):
    kinds = {(p["service"], p["kind"]) for p in hw.assess(ROWS, {"disk": "red", "cpu": "amber"})}
    assert kinds == {("reports", "stopped"), ("web", "unhealthy"), ("db", "oom"), ("host", "host-disk")}
    seen = {}
    hw.assess([{"key": "api", "service": "api", "state": "running", "restarts": 1}], {}, seen)
    again = hw.assess([{"key": "api", "service": "api", "state": "running", "restarts": 4}], {}, seen)
    assert again[0]["kind"] == "restarting"
    assert hw.assess([{"key": "setup", "service": "setup", "state": "exited", "exit_code": 1}])[0]["kind"] == "stopped"


def test_one_alert_per_problem_a_reminder_later_and_a_recovery(hw):
    open_ = {}
    p = [{"key": "web:unhealthy", "service": "web", "kind": "unhealthy", "detail": ""}]
    assert [e["event"] for e in hw.step(p, open_, 0, 60)] == ["alert"]
    assert hw.step(p, open_, 60, 60) == []                                   # a minute later: not told again
    assert [e["event"] for e in hw.step(p, open_, 3601, 60)] == ["reminder"]
    rec = hw.step([], open_, 3700, 60)
    assert [e["event"] for e in rec] == ["recovered"] and rec[0]["minutes"] == 61.7 and open_ == {}
    assert "is working again" in hw.text_of(rec[0])


def test_the_watcher_keeps_alerts_while_the_api_is_down_and_tests_itself(hw, monkeypatch):
    hw.hooks.update(stats=lambda fresh=False: {"containers": ROWS[:2]}, restarting=lambda: False, maintenance=lambda: None)
    monkeypatch.setattr(hw, "host", lambda sample=False: {"levels": {}})
    monkeypatch.setattr(hw, "_deliver", lambda s: 0)                         # the API is down
    hw.test_alert("api")
    ev = hw.watch_once(now=1000.0)
    assert [(e["event"], e["service"]) for e in ev] == [("alert", "api")] and "Container api has stopped" in ev[0]["text"]
    assert len(hw._load()["outbox"]) == 1 and hw.alerts()["open"][0]["text"].startswith("Container api")
    ev = hw.watch_once(now=1060.0)
    assert [e["event"] for e in ev] == ["recovered"] and len(hw._load()["outbox"]) == 2
    hw.hooks["restarting"] = lambda: True                                    # a restart on purpose: no alerts
    assert hw.watch_once(now=1120.0) == []


def test_auto_restart_is_off_by_default_and_limited(hw):
    done = []
    hw.hooks["restart_service"] = done.append
    s = {"restarts": {}, "history": [], "outbox": []}
    e = [{"event": "alert", "service": "web", "kind": "unhealthy", "key": "web:unhealthy"}]
    hw._auto_restart(s, e, 0)
    assert done == []
    hw.hooks["values"] = lambda: {"EAX_ALERT_AUTO_RESTART": "web", "EAX_ALERT_AUTO_RESTART_MAX": "2"}
    for t in (1, 2, 3):
        hw._auto_restart(s, e, t)
    assert done == ["web", "web"] and s["history"][-1]["event"] == "restart-skipped"


def test_the_api_turns_alerts_into_notifications(monkeypatch):
    from eax import container_alerts as ca
    made, audited = [], []
    monkeypatch.setattr(ca, "admins", lambda conn: ["it1", "sa1"])
    monkeypatch.setattr(ca.notify, "create", lambda conn, **k: made.append(k) or 1)
    monkeypatch.setattr(ca.audit, "record", lambda conn, **k: audited.append(k["action"]))
    n = ca.tell(None, [{"event": "alert", "service": "web", "kind": "unhealthy", "text": "Container web is unhealthy"},
                       {"event": "recovered", "service": "web", "kind": "unhealthy", "text": "Container web is working again"},
                       {"event": "nonsense"}])
    assert n == 2 and made[0]["needs_action"] and not made[1]["needs_action"]
    assert made[0]["recipients"] == ["it1", "sa1"] and made[0]["category"] == "system"   # the webhooks get "system"
    assert audited == ["container.alert", "container.recovered"]


# ---------------------------------------------------------------- wiring
def test_the_helper_the_api_and_the_screens_are_wired():
    ops = (REPO / "services" / "ops" / "ops.py").read_text()
    assert "import hostwatch" in ops and "hostwatch.loop" in ops and "_hostwatch_get" in ops and "/alerts/test" in ops
    assert "COPY hostwatch.py /app/hostwatch.py" in (REPO / "services" / "ops" / "Dockerfile").read_text()
    admin = (REPO / "services" / "api" / "eax" / "api" / "admin.py").read_text()
    for route in ("/admin/hosts", "/admin/mounts", "/admin/mounts/<mid>", "/admin/containers/<service>/files",
                  "/admin/containers/<service>/files/content", "/admin/containers/<service>/files/download", "/admin/alerts",
                  "/internal/container-alerts"):
        assert f'@blp.route("{route}")' in admin, route
    menu = (WEB / "menu.js").read_text()
    assert '"#/admin/hosts"' in menu and '"#/admin/mounts"' in menu
    assert '["files", "Files"]' in (WEB / "ContainerConsole.jsx").read_text()
    assert "<ContainerAlertBanner />" in (WEB / "App.jsx").read_text()


def test_the_self_test_raises_an_alert_and_sees_its_recovery(monkeypatch):
    from eax.testing import run as R
    t = {"now": 1000.0}
    monkeypatch.setattr(R.time, "time", lambda: t["now"])
    monkeypatch.setattr(R.time, "sleep", lambda s: t.update(now=t["now"] + s))
    answers = iter([[], [{"at": 1001, "event": "alert", "detail": "a test alert (self-test)"}],
                    [{"at": 1061, "event": "recovered", "kind": "stopped", "detail": "a test alert (self-test)"},
                     {"at": 1001, "event": "alert", "detail": "a test alert (self-test)"}]])

    def call(api, method, path, token, size=1500):
        return (200, "{}") if method == "post" else (200, json.dumps({"history": next(answers)}))
    monkeypatch.setattr(R.api_matrix, "call", call)
    got = []
    R.alert_check("http://api", "tok", lambda name, outcome, detail="", ms=0: got.append((name, outcome)), lambda m: None)
    assert got == [("alerts: a container that stops raises an alert", "passed"), ("alerts: its recovery is told", "passed")]


def test_measurements_and_watchers_are_not_critical():
    """R2.35 decided (13 Nov 2026, D645): the limit of 10 stays; coverage, the alert check and the UI review's notes are
    non-critical; the application's own checks stay critical."""
    from eax.testing import health
    assert health.NON_CRITICAL_LIMIT == 10
    assert health.importance("api", "coverage: the API's code run by this test") == "non-critical"
    assert health.importance("api", "alerts: a container that stops raises an alert") == "non-critical"
    assert health.importance("ui", "UI review: projects as architect") == "non-critical"
    assert health.importance("api", "GET /api/v1/models as architect") == "critical"
    assert health.importance("security", "headers") == "non-critical"


def test_short_lived_containers_from_the_helpers_image_are_not_services(tmp_path, monkeypatch):
    """Owner, 13 Nov 2026 ("What is Ops1 container?", a screenshot with five stopped "ops-1" rows and a red banner): the
    Command centre, updates and mount looks start containers from the ops image, which carries Compose's labels; they
    were listed as more ops containers, the stopped ones as problems. Only containers Compose made for a service count."""
    sys.path.insert(0, str(REPO / "services" / "ops"))
    spec = importlib.util.spec_from_file_location("ops_svc_r219", REPO / "services" / "ops" / "ops.py")
    ops = importlib.util.module_from_spec(spec)
    monkeypatch.setenv("EAX_WORK_MOUNT", str(tmp_path))
    spec.loader.exec_module(ops)
    assert ops.is_service_container("sha256abc", "False")
    assert not ops.is_service_container("", "")                 # a command's container: no config hash
    assert not ops.is_service_container("sha256abc", "True")    # docker compose run
    rows = {"a1": "ops|1|hash1|False", "b2": "ops|1||", "c3": "ops|1||", "d4": "db|1|hash2|False"}
    monkeypatch.setattr(ops, "project", lambda: "eaexplorer")

    def docker(*a, **k):
        if a[0] == "ps":
            return "\n".join(json.dumps({"ID": i, "Names": f"n{i}", "State": "exited" if i in ("b2", "c3") else "running",
                                         "Status": "", "Image": "x"}) for i in rows)
        return rows[a[-1]]
    monkeypatch.setattr(ops, "docker", docker)
    assert [(c["key"], c["id"]) for c in ops.containers()] == [("db", "d4"), ("ops", "a1")]
    admin = (REPO / "services" / "api" / "eax" / "api" / "admin.py").read_text()
    assert "is not answering" in admin and "urlopen" not in admin[admin.index("class Alerts"):admin.index("class AlertTest")]


def test_every_container_says_what_it_is_for():
    """Owner, 13 Nov 2026: "In the container list can we please add what each container is for in the table"."""
    import re

    import yaml
    web = (WEB / "ContainerConsole.jsx").read_text()
    block = web[web.index("export const PURPOSE = {"):web.index("};", web.index("export const PURPOSE = {"))]
    said = set(re.findall(r'^\s+"?([a-z-]+)"?:', block, re.M))
    services = set(yaml.safe_load((REPO / "docker-compose.yml").read_text())["services"])
    assert services <= said, services - said
    assert "<th>What it is for</th>" in web and "purposeOf(c)" in web


def test_only_current_containers_unless_asked():
    """Owner, 13 Nov 2026: "Lets ensure only current and relevent containers are shown. Dead are not unless asked for"."""
    web = (WEB / "ContainerConsole.jsx").read_text()
    assert "export function isCurrent(c)" in web and '"dead"' in web and '["setup", "reports-init"]' in web
    assert "every.filter(isCurrent)" in web and "showAll || isCurrent(c)" in web and "Show stopped" in web


def test_a_busy_minute_or_a_start_up_is_not_a_host_alert(hw):
    """Owner, 13 Nov 2026: "Not working: The host CPU is high" while two containers were starting, "all containers are
    ok". The host is an alert only when a level stays at its alert line for EAX_ALERT_HOST_MINUTES (10) samples in a
    row, never while EA Explorer starts, and the banner calls it "Needs attention", not "Not working"."""
    t = hw.thresholds()
    hot = [{"cpu": 95, "memory": 50, "disk": 50}] * 10
    assert hw.sustained(hot, t, 10)["cpu"] == "red"
    assert hw.sustained(hot[:9], t, 10)["cpu"] == "green"                     # not ten minutes yet
    assert hw.sustained(hot[:9] + [{"cpu": 40}], t, 10)["cpu"] == "green"     # dropped back
    assert hw.starting([{"state": "running", "health": "starting"}]) and not hw.starting([{"state": "running"}])
    assert hw.text_of({"event": "alert", "service": "host", "kind": "host-cpu"}) == "The host's CPU has been high"
    web = (WEB / "Hosts.jsx").read_text()
    assert "Needs attention:" in web and 'o.service !== "host"' in web


def test_the_helper_answers_a_hosts_or_alerts_request_once(tmp_path, monkeypatch):
    """The ops log (13 Nov 2026) showed "GET /alerts -> 200" and then "GET /alerts -> 404" for each request: the answer
    was sent, then the handler went on to its 404. It answers once now."""
    spec = importlib.util.spec_from_file_location("ops_once_r219", REPO / "services" / "ops" / "ops.py")
    ops = importlib.util.module_from_spec(spec)
    monkeypatch.setenv("EAX_WORK_MOUNT", str(tmp_path))
    monkeypatch.setenv("EAX_OPS_TOKEN", "t")
    spec.loader.exec_module(ops)
    monkeypatch.setattr(ops, "TOKEN", "t")
    monkeypatch.setattr(ops.hostwatch, "alerts", lambda: {"open": []})
    sent = []
    h = ops.Handler.__new__(ops.Handler)
    h.path, h.headers = "/alerts", {"X-Ops-Token": "t"}
    h._send = lambda code, body: sent.append(code)
    h.do_GET()
    assert sent == [200]
