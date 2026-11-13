"""The Command centre and the Console (D554): eax commands from a web page, in EA Explorer and in eax deploy's page.

The catalogue is read from eaxcli/help.txt; only known commands with their own options run (never a shell); IT and
Super Admins may run them, the wipe commands Super Admins only, behind the installation's name, "I understand" and a
backup first; every run and console line is kept. Docker, eaxpy and the operations helper are fakes here.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from eaxcli import cmdrun  # noqa: E402
from eaxcli import commands as C  # noqa: E402
from eaxcli import help as H  # noqa: E402
from eaxcli import webconsole as W  # noqa: E402


# ---------------------------------------------------------------- the catalogue from help.txt
def test_every_command_in_the_help_is_in_the_catalogue():
    doc = H.parse(H.SOURCE.read_text(encoding="utf-8"), {"unix", "sh"})
    in_help = {c["names"][0] for s in doc["sections"] for c in s["commands"]}
    cat = C.catalogue()
    listed = {c["name"] for g in cat["groups"] for c in g["commands"]}
    assert listed == in_help
    assert [g["title"] for g in cat["groups"]] == [s["title"] for s in doc["sections"]]
    k = {c["name"]: c for g in cat["groups"] for c in g["commands"]}
    assert {n for n, c in k.items() if c["kind"] == "wipe"} == {"cleanup", "clean-run", "clean-restart", "clean-debug"}
    assert all(k[n]["role"] == "super-admin" for n in C.WIPE)
    assert k["stop"]["kind"] == "offline" and k["init"]["kind"] == "host" and k["console"]["kind"] == "interactive"
    assert k["status"]["summary"] and k["backup"]["examples"]
    assert all(c["host_why"] for c in k.values() if c["kind"] == "host")


# ---------------------------------------------------------------- what may be typed
@pytest.mark.parametrize("line,argv", [
    ("eax status", ["status"]), ("status", ["status"]), ("./eax.sh backup nightly", ["backup", "nightly"]),
    (".\\eax restore latest --what db", ["restore", "latest", "--what", "db"]), ("down", ["stop"]),
    ("service reports off", ["service", "reports", "off"]), ("update --channel rc --to v0.19.0", ["update", "--channel", "rc", "--to", "v0.19.0"]),
    ("test --smoke --suite api", ["test", "--smoke", "--suite", "api"]), ("help restore", ["help", "restore"]),
    ("import --all", ["import", "--all"]), ("cleanup --all", ["cleanup", "--all"]),
])
def test_eax_lines_are_taken(line, argv):
    assert C.parse_line(line) == argv


@pytest.mark.parametrize("line", [
    "ls", "bash", "sh -c id", "status; rm -rf /", "status && whoami", "status | cat", "backup $(id)", "backup `id`",
    "backup a>b", "service reports maybe", "update --channel nightly", "backup 'a b'", "status --nope", "restore-log",
    "backup tag\nrm", "maintenance", "python3 -c 1",
])
def test_anything_else_is_refused(line):
    with pytest.raises(C.Refused):
        C.parse_line(line)


def test_the_guided_form_builds_and_checks_the_command():
    assert C.build_argv("restore", {"arg0": "latest", "--what": "db", "--yes": True}) == ["restore", "latest", "--what", "db", "--yes"]
    assert C.build_argv("up", {"arg0": "api proxy", "--wait-all": True}) == ["up", "api", "proxy", "--wait-all"]
    assert C.build_argv("secrets", {"arg0": "push", "--to": "aws:eax", "--to:flag": "--to"}) == ["secrets", "push", "--to", "aws:eax"]
    with pytest.raises(C.Refused):
        C.build_argv("service", {"arg0": "reports"})                 # on|off is needed
    with pytest.raises(C.Refused):
        C.build_argv("backup", {"arg0": "x;reboot"})
    assert C.with_yes(["cleanup", "--all"]) == ["cleanup", "--all", "--yes"]
    assert C.with_yes(["status"]) == ["status"]


def test_rights_and_the_strong_confirm():
    C.allowed("status", ["it-admin"])
    C.allowed("cleanup", ["super-admin"])
    with pytest.raises(C.Refused):
        C.allowed("status", ["user", "model-creator"])
    with pytest.raises(C.Refused):
        C.allowed("clean-restart", ["it-admin"])
    plan = C.wipe_plan(["cleanup", "--all", "--certificate"])
    assert any("database" in d for d in plan["deletes"]) and any("certificate" in d for d in plan["deletes"])
    assert "safety-backups" in plan["backup_first"] and plan["backups_deleted"]
    assert not any("database" in d for d in C.wipe_plan(["cleanup"])["deletes"])
    C.check_confirm(["status"], "", "", False)                       # nothing to confirm
    with pytest.raises(C.Refused):
        C.check_confirm(["cleanup"], "acme-ea", "acme-ea", False)     # not ticked
    with pytest.raises(C.Refused):
        C.check_confirm(["clean-run"], "acme", "acme-ea", True)       # wrong name
    C.check_confirm(["clean-run"], "acme-ea", "acme-ea", True)


# ---------------------------------------------------------------- a run, kept (eaxpy a fake)
def _fake_install(tmp: Path) -> Path:
    (tmp / "work").mkdir()
    (tmp / "eaxpy.py").write_text(
        "import sys, pathlib\n"
        "print('eaxpy', *sys.argv[1:])\n"
        "if sys.argv[1] == 'backup':\n"
        "    d = pathlib.Path('work/backups/infrastructure/20261110T2200Z-' + sys.argv[2]); d.mkdir(parents=True)\n"
        "    (d / 'manifest.json').write_text('{}')\n"
        "if sys.argv[1] == 'cleanup':\n"
        "    import shutil; shutil.rmtree('work'); pathlib.Path('work').mkdir()\n"
        "sys.exit(3 if sys.argv[1] == 'diag' else 0)\n", encoding="utf-8")
    (tmp / "work" / "eaexplorer.env").write_text("EAX_INSTALLATION_NAME=acme-ea\n", encoding="utf-8")
    return tmp


def test_a_run_is_kept_with_its_output_and_exit_code(tmp_path):
    root = _fake_install(tmp_path)
    assert cmdrun.run("r1", "it_admin", ["status"], root) == 0
    out = cmdrun.output("r1", 0, root)
    assert "eaxpy status" in out["text"] and out["status"]["exit_code"] == 0 and out["status"]["by"] == "it_admin"
    assert cmdrun.run("r2", "it_admin", ["diag"], root) == 3
    assert cmdrun.output("r2", 0, root)["status"]["state"] == "failed"
    assert {r["id"] for r in cmdrun.history(root)} == {"r1", "r2"}
    with pytest.raises(C.Refused):
        cmdrun.run("r3", "x", ["rm", "-rf", "/"], root)


def test_a_wipe_backs_up_first_and_keeps_its_record(tmp_path):
    root = _fake_install(tmp_path)
    assert C.installation_name(root) == "acme-ea"
    assert cmdrun.run("w1", "super_admin", ["cleanup", "--all"], root) == 0
    kept = list((root / "persist" / "safety-backups").glob("*-safety-w1"))
    assert kept and (kept[0] / "manifest.json").is_file()            # the backup outlives the cleanup
    out = cmdrun.output("w1", 0, root)
    assert "eaxpy cleanup --all --yes" in out["text"] and out["status"]["kind"] == "wipe"


# ---------------------------------------------------------------- the Console
def test_the_console_takes_eax_commands_only_and_keeps_everything(tmp_path, monkeypatch, capsys):
    root = _fake_install(tmp_path)
    s = W.Session("it_admin", ["it-admin"], local=False, root=root, session="s1")
    ran = []
    monkeypatch.setattr(s, "spawn", lambda argv: ran.append(argv) or 0)
    for line in ["ls -la", "status; reboot", "status", "backup nightly", "init", "clean-restart"]:
        assert s.one(line)
    assert s.one("exit") is False
    assert ran == [["status"], ["backup", "nightly"]]                # init is host-only; clean-restart is Super Admins'
    rows = [json.loads(x) for x in (root / "work" / "commands" / "console-s1" / "commands.jsonl").read_text().splitlines()]
    assert [bool(r["refused"]) for r in rows] == [True, True, False, False, True, True]
    assert rows[2]["command"] == "eax status" and rows[2]["exit_code"] == 0 and rows[2]["by"] == "it_admin"
    assert "not an eax command" in (root / "work" / "commands" / "console-s1" / "transcript.log").read_text()


def test_the_console_wipe_needs_the_name_and_i_understand(tmp_path, monkeypatch):
    root = _fake_install(tmp_path)
    s = W.Session("super_admin", ["super-admin"], local=True, root=root, session="s2")
    ran = []
    monkeypatch.setattr(s, "spawn", lambda argv: ran.append(argv) or 0)
    answers = iter(["acme", "I understand", "acme-ea", "I understand"])
    monkeypatch.setattr(s, "ask", lambda prompt: next(answers))
    s.one("cleanup --all")                                           # the wrong name: nothing runs
    assert ran == []
    s.one("cleanup --all")
    assert ran == [["cleanup", "--all", "--yes"]] and list((root / "persist" / "safety-backups").glob("*-safety-s2"))


# ---------------------------------------------------------------- the operations helper's side (docker a fake)
def _ops(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("ops_commandcentre", REPO / "services" / "ops" / "commandcentre.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    calls = []
    m.hooks.update(docker=lambda *a: calls.append(a) or "", me=lambda: {"project": "eax", "image": "eaexplorer/ops:dev",
                                                                         "install": "/opt/eaexplorer"},
                   read_config=lambda: ["EAX_INSTALLATION_NAME=acme-ea"], tickets={}, tlock=threading.Lock(),
                   idle_minutes=lambda: 15)
    monkeypatch.setattr(m, "RUNS", str(tmp_path / "commands"))
    return m, calls


def test_the_helper_starts_a_container_never_a_shell(tmp_path, monkeypatch):
    m, calls = _ops(tmp_path, monkeypatch)
    out = m.start({"argv": ["backup", "nightly"], "by": "it_admin", "roles": ["it-admin"]})
    assert out["kind"] == "run" and not out["goes_offline"]
    create = calls[0]
    assert create[0] == "create" and "--entrypoint" in create and "python3" in create and "sh" not in create
    assert create[-7:] == ("-m", "eaxcli.cmdrun", out["id"], "it_admin", "--", "backup", "nightly")
    assert calls[1][0] == "start"
    assert m.start({"name": "service", "values": {"arg0": "reports", "arg1": "off"}, "by": "x", "roles": ["it-admin"]})["argv"] == ["service", "reports", "off"]
    for bad, why in [({"argv": ["init"]}, "machine itself"), ({"argv": ["console"]}, "Console"),
                     ({"argv": ["ls"]}, "not an eax command"), ({"argv": ["backup", "a;b"]}, "not allowed")]:
        with pytest.raises(m.C.Refused, match=why):
            m.start({**bad, "by": "x", "roles": ["it-admin"]})
    with pytest.raises(m.C.Refused):
        m.start({"argv": ["clean-restart"], "by": "x", "roles": ["it-admin"]})          # Super Admins only
    with pytest.raises(m.C.Refused):
        m.start({"argv": ["clean-restart"], "by": "x", "roles": ["super-admin"], "confirm": {"typed": "nope", "understood": True}})
    assert m.start({"argv": ["clean-restart"], "by": "x", "roles": ["super-admin"],
                    "confirm": {"typed": "acme-ea", "understood": True}})["goes_offline"]
    with pytest.raises(m.C.Refused):
        m.start({"argv": ["status"], "by": "x", "roles": ["user"]})


def test_the_console_ticket_runs_the_web_console(tmp_path, monkeypatch):
    m, _ = _ops(tmp_path, monkeypatch)
    t = m.console_ticket({"by": "it_admin", "roles": ["it-admin", "bad role!"], "cols": 100, "rows": 30})
    got = m.hooks["tickets"][t["ticket"]]
    assert got["argv"][:2] == ["docker", "run"] and got["argv"][-2:] == ["-m", "eaxcli.webconsole"]
    assert "EAX_CONSOLE_ROLES=it-admin" in got["argv"] and t["session"].startswith("console-")
    with pytest.raises(m.C.Refused):
        m.console_ticket({"by": "x", "roles": ["user"]})


def test_history_detail_stop_and_ack(tmp_path, monkeypatch):
    m, _ = _ops(tmp_path, monkeypatch)
    d = tmp_path / "commands" / "20261110T2000Z-logs-ab12"
    d.mkdir(parents=True)
    (d / "status.json").write_text(json.dumps({"id": d.name, "argv": ["logs"], "command": "eax logs", "by": "a",
                                               "started": "2026-11-10T20:00:00Z", "state": "running"}))
    (d / "output.log").write_text("line one\nline two\n")
    assert m.detail(d.name, 0)["text"] == "line one\nline two\n" and m.detail(d.name, 9)["text"] == "line two\n"
    assert m.stop(d.name, "b")["state"] == "stopped"
    assert m.ack([d.name]) == 1 and m.ack([d.name]) == 0
    with pytest.raises(FileNotFoundError):
        m.detail("../../etc", 0)


# ---------------------------------------------------------------- eax deploy's page: the same catalogue and checks
def test_the_deploy_page_offers_commands_and_needs_its_key(tmp_path, monkeypatch):
    from eaxcli import deploy_commands as DC
    from eaxcli import deploy_web as DW
    state = DW.State({}, plan=False)
    stop = threading.Event()
    server = ThreadingHTTPServer(("127.0.0.1", 0), DW.make_handler(state, "k3y", stop))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def call(path, body=None, key="k3y"):
        req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={"X-Deploy-Key": key, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:      # noqa: S310 - the test's own server
            return json.loads(r.read())
    started = []
    monkeypatch.setattr(DC.subprocess, "Popen", lambda cmd, **k: started.append(cmd))
    try:
        with pytest.raises(urllib.error.HTTPError) as e:
            call("/api/commands", key="wrong")
        assert e.value.code == 403
        cat = call("/api/commands")
        assert not cat["remote"] and any(g["title"] == "Start and stop" for g in cat["groups"])
        r = call("/api/commands/run", {"argv": ["status"]})
        assert r["where"] == "here" and started[-1][-2:] == ["--", "status"] and "eaxcli.cmdrun" in started[-1]
        for argv in (["deploy"], ["console"], ["ls"], ["status;id"]):
            with pytest.raises(urllib.error.HTTPError) as e:
                call("/api/commands/run", {"argv": argv})
            assert e.value.code == 400
        with pytest.raises(urllib.error.HTTPError):
            call("/api/commands/run", {"argv": ["clean-run"], "confirm": {"typed": "nope", "understood": True}})
        page = urllib.request.urlopen(base + "/", timeout=10).read().decode()       # noqa: S310
        assert 'data-tab="commands"' in page and 'data-tab="console"' in page
    finally:
        server.shutdown()


def test_the_deploy_page_targets_the_server_it_set_up():
    from eaxcli import deploy_commands as DC
    t = DC.Target.from_answers({"kind": "server", "where": "ssh", "ssh_target": "ops@10.0.0.5", "ssh_key": "/k",
                                "install_dir": "/opt/eax"}, deployed=True)
    assert t.remote and t.ssh[-1] == "ops@10.0.0.5" and t.folder == "/opt/eax"
    assert not DC.Target.from_answers({"kind": "laptop"}, deployed=True).remote
    assert not DC.Target.from_answers({"kind": "server", "where": "ssh", "ssh_target": "x@y"}, deployed=False).remote


def test_laptop_sample_runs_show_each_state(tmp_path, monkeypatch):
    m, _ = _ops(tmp_path, monkeypatch)
    assert m.seed_samples("server") == 0
    assert m.seed_samples("laptop") == 5
    assert m.seed_samples("laptop") == 0                              # made once
    states = {r["state"] for r in m.history()}
    assert {"done", "failed", "stopped"} <= states
    console = m.detail("console-20261109T1000Z-sa05")
    assert any(c["refused"] for c in console["commands"]) and "eax>" in console["text"]
