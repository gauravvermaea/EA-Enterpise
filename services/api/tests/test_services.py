"""Optional services switched on or off (D191), the operations helper's config file handling, background tasks (D192)."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

from eax import health
from eax import services as sv

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
WEB = ROOT.parent / "web" / "src"


def _ops(tmp_path, monkeypatch):
    monkeypatch.setenv("EAX_WORK_MOUNT", str(tmp_path))
    spec = importlib.util.spec_from_file_location("ops_under_test", ROOT.parent / "ops" / "ops.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_everything_is_on_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(sv, "FILES", [tmp_path / "services.env"])
    for k in sv.SERVICES:
        monkeypatch.delenv(sv.SERVICES[k][0], raising=False)
    monkeypatch.delenv("EAX_MCP_ENABLED", raising=False)
    assert all(sv.switches().values())
    (tmp_path / "services.env").write_text("EAX_SERVICE_REPORTS=off\nEAX_SERVICE_MCP=false\n")
    sw = sv.switches()
    assert sw["reports"] is False and sw["mcp"] is False and sw["documents"] is True
    assert health.check_reports()["status"] == "off" and health.check_mcp()["status"] == "off"


def test_templates_have_every_switch_on():
    for kind in ("laptop", "server"):
        text = (REPO / f"deploy/templates/eaexplorer.{kind}.env").read_text()
        for setting, *_ in sv.SERVICES.values():
            assert f"\n{setting}=on\n" in text, (kind, setting)   # on, and no comment on the line (parsed as a value)
        assert "EAX_MCP_ENABLED" not in text


def test_ops_writes_switch_with_a_copy_and_restores(tmp_path, monkeypatch):
    ops = _ops(tmp_path, monkeypatch)
    (tmp_path / "eaexplorer.env").write_text((REPO / "deploy/templates/eaexplorer.laptop.env").read_text())
    saved = ops.copy_config("user_super_admin", "documents-off")
    ops._write(ops.set_switch(ops._read_config(), "documents", False))
    assert ops.switches()["documents"] is False
    assert "EAX_SERVICE_DOCUMENTS=off" in (tmp_path / "services.env").read_text()
    assert "PASSWORD" not in (tmp_path / "services.env").read_text()                 # no secrets in the copy for the api
    assert (tmp_path / "config-history" / saved).is_file()
    monkeypatch.setattr(ops, "apply_switch", lambda k, on: [f"{k} {on}"])
    out = ops.restore(saved, "user_super_admin")
    assert out["saved_first"] != saved and ops.switches()["documents"] is True
    assert len(ops.copies()) == 2
    try:
        ops.restore("../eaexplorer.env", "x")
        raise AssertionError("a path outside the copies was accepted")
    except FileNotFoundError:
        pass
    assert ops.set_switch(["A=1"], "drawio", False)[-1] == "EAX_SERVICE_DRAWIO=off"   # added when missing


def test_eax_commands_and_console():
    sh = (REPO / "eax.sh").read_text()
    ps = (REPO / "eax.ps1").read_text(encoding="utf-8")
    for src in (sh, ps):
        assert "config-history" in src and "services.env" in src
    assert "service <name> on|off" in sh and "service <name> on|off" in ps
    admin = (WEB / "Admin.jsx").read_text(encoding="utf-8")
    assert "/api/v1/admin/services/" in admin and "/api/v1/admin/config-copies/restore" in admin
    compose = (REPO / "docker-compose.yml").read_text()
    assert "./work:/eax-work:ro" in compose and "      - ./work:/eax-work\n" in compose
    entry = (ROOT / "entrypoint.sh").read_text()
    assert "eax.services is-on mcp" in entry and "eax.services is-on change_log" in entry


def test_tagging_runs_in_the_background():
    src = (ROOT / "eax" / "api" / "versions.py").read_text()
    assert 'tk.create(conn, "tag.create"' in src and "run_task.defer" in src
    web = (WEB / "ModelOps.jsx").read_text(encoding="utf-8")
    assert "trackTask(out.task" in web and "useTask(taskId)" in web
    assert "TaskBar" in (WEB / "App.jsx").read_text(encoding="utf-8")
    assert os.path.exists(WEB / "tasks.js")


def test_no_jsx_in_js_files():
    """Vite parses .js files as plain JavaScript: JSX in one fails the web image build (5 Nov 2026). JSX goes in .jsx."""
    import re
    tag = re.compile(r"(return\s*\(\s*<|=>\s*\(?\s*<[A-Za-z]|<(div|span|p|a|b|button|table|tr|td|ul|li|section|label|input|select)[\s>/])")
    bad = [p.name for p in WEB.glob("*.js") if tag.search(re.sub(r"//.*|/\*.*?\*/|`[^`]*`|\"[^\"\n]*\"|'[^'\n]*'", "",
                                                              p.read_text(encoding="utf-8"), flags=re.S))]
    assert not bad, f"JSX in .js files (rename them .jsx): {bad}"


def test_request_bodies_pass_their_fields():
    """Free is a schema for answers: as a request body it has no fields and refuses every one with 422 (5 Nov 2026:
    settings, services, sheets and collection sets failed). Bodies of varying shape use FreeIn."""
    api = ROOT / "eax" / "api"
    bad = [p.name for p in api.glob("*.py") if "@blp.arguments(Free)" in p.read_text()]
    assert not bad, bad
    assert "unknown = INCLUDE" in (api / "models.py").read_text().split("class FreeIn")[1].split("class CreateIn")[0]


def test_config_file_in_clear_text_copied_checked_and_saved(tmp_path, monkeypatch):
    ops = _ops(tmp_path, monkeypatch)
    cfg = Path(ops.CONFIG)
    base = ("# a comment\nEAX_HOSTNAME=a.local\nEAX_DEPLOYMENT=laptop\nEAX_DB_PASSWORD=old\nEAX_DB_MIGRATOR_PASSWORD=m\n"
            "EAX_KC_ADMIN_PASSWORD=k\nEAX_KEYCLOAK_REALM=eaexplorer\nEAX_CHANGELOG_DB_URL=postgresql://u:pw@db/x\n"
            "EAX_SERVICE_REPORTS=on\nGONE=1\n")
    cfg.write_text(base, encoding="utf-8")
    text = ops.config_text("")["text"]          # clear text (owner, 5 Nov 2026)
    assert "EAX_DB_PASSWORD=old" in text and "u:pw@" in text and ops.config_text("")["editable"]
    kept = ops.copy_config("u", "kept-by-hand")
    assert ops.config_text(kept)["editable"] is False and "kept-by-hand" in kept

    # check: syntax, duplicates and needed settings refuse; password changes warn; what changes is listed
    bad = ops.check_text("EAX_HOSTNAME=a\nEAX_HOSTNAME=b\nnot a setting\n9X=1")
    assert not bad["ok"] and len([e for e in bad["errors"] if e.startswith("Line")]) == 3
    assert any("EAX_DB_PASSWORD is missing" in e for e in bad["errors"])
    new = base.replace("old", "new").replace("EAX_SERVICE_REPORTS=on", "EAX_SERVICE_REPORTS=off").replace("GONE=1", "ADDED=2")
    chk = ops.check_text(new)
    assert chk["ok"] and any("EAX_DB_PASSWORD changed" in w for w in chk["warnings"])
    rows = {r["setting"]: r for r in chk["rows"]}
    assert rows["EAX_DB_PASSWORD"]["a"] == "old" and rows["EAX_DB_PASSWORD"]["b"] == "new"
    assert rows["GONE"]["change"] == "removed" and rows["ADDED"]["change"] == "added"
    with pytest.raises(ValueError):
        ops.save_text("x", "u", "bad")

    applied = []
    monkeypatch.setattr(ops, "_in_background", lambda key, what, fn: applied.append(what))
    out = ops.save_text(new, "u", "rotate db")
    assert cfg.read_text(encoding="utf-8") == new and out["saved_first"] and applied == ["config file saved"]
    assert ops.switches()["reports"] is False
    assert "EAX_SERVICE_REPORTS=off" in (tmp_path / "services.env").read_text(encoding="utf-8")
    assert ops.save_text(new, "u", "again")["saved_first"] is None          # nothing changed: no copy

    d = {r["setting"]: r for r in ops.config_diff(kept, "")["rows"]}       # compare: clear text too
    assert d["EAX_DB_PASSWORD"]["a"] == "old" and d["EAX_DB_PASSWORD"]["b"] == "new"
    for bad_name in ("../eaexplorer.env", "eaexplorer.env.x/../../etc"):
        with pytest.raises(FileNotFoundError):
            ops.config_text(bad_name)


def test_start_does_not_rerun_a_finished_reports_setup(tmp_path, monkeypatch):
    ops = _ops(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(ops, "_container", lambda n: {"id": n, "state": "exited"})
    monkeypatch.setattr(ops, "_finished_ok", lambda cid: True)
    monkeypatch.setattr(ops, "docker", lambda *a, **k: calls.append(a) or "")
    log = ops.apply_switch("reports", True)
    assert calls == [("start", "reports")] and "not run again" in log[0]


def test_core_services_are_listed():
    assert {c["key"] for c in sv.describe_core()} == {"web", "api", "keycloak", "db", "proxy", "ops"}


def test_each_service_switches_on_its_own(tmp_path, monkeypatch):
    ops = _ops(tmp_path, monkeypatch)
    import threading as th
    gate = th.Event()
    ops._in_background("reports", "reports off", lambda: gate.wait(5) and [])
    ops._in_background("drawio", "drawio off", lambda: ["stopped drawio"])
    for _ in range(50):
        if not ops.busy("drawio"):
            break
        th.Event().wait(0.02)
    assert ops.busy("reports") and not ops.busy("drawio") and ops.jobs["drawio"]["log"] == ["stopped drawio"]
    assert ops.switching()["busy"]
    gate.set()


def test_container_stats_from_docker(tmp_path, monkeypatch):
    ops = _ops(tmp_path, monkeypatch)
    monkeypatch.setattr(ops, "containers", lambda: [
        {"id": "aaa111bbb222ccc", "name": "eax-api-1", "service": "api", "state": "running", "status": "Up", "image": "x"},
        {"id": "ddd444eee555fff", "name": "eax-drawio-1", "service": "drawio", "state": "exited", "status": "Exited", "image": "y"}])
    monkeypatch.setattr(ops, "project", lambda: "eax")

    def fake(*a, **k):
        if a[0] == "stats":
            return '{"ID":"aaa111bbb222","CPUPerc":"2.50%","MemUsage":"512MiB / 15.5GiB","MemPerc":"3.2%","NetIO":"1kB / 2kB","BlockIO":"0B / 0B","PIDs":"9"}\n'
        if a[0] == "inspect":
            return ("aaa111bbb222ccc|healthy|2026-11-05T20:00:00Z|1|eax_pg,\nddd444eee555fff|none|2026-11-05T19:00:00Z|0|\n")
        if a[0] == "ps":
            return "aaa111bbb222|12.5MB (virtual 300MB)\nddd444eee555|0B (virtual 1GB)\n"
        return "{}"
    monkeypatch.setattr(ops, "docker", fake)
    ops._disk_cache.update(at=ops.time.time(), data={"eax_pg": 2_000_000_000})
    out = {c["service"]: c for c in ops.stats(fresh=True)["containers"]}
    api = out["api"]
    assert api["cpu_percent"] == 2.5 and api["memory_bytes"] == 512 * 1024 * 1024 and api["pids"] == 9
    assert api["health"] == "healthy" and api["restarts"] == 1 and api["volume_bytes"] == 2_000_000_000
    assert api["layer_bytes"] == 12_500_000 and out["drawio"]["cpu_percent"] is None
