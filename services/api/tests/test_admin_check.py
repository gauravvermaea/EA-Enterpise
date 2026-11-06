"""The sign-in check for IT and Super Admins (D215): what counts as a problem."""

from pathlib import Path

from eax import admin_check as ac

ROOT = Path(__file__).resolve().parents[1]


def _c(service, state="running", **k):
    return {"service": service, "state": state, "health": "healthy", "restarts": 0, "memory_percent": 10, "exit_code": 0,
            "oom_killed": False, **k}


def test_all_well_is_quiet():
    h = {"checks": {"api": {"name": "API", "status": "up", "response_ms": 3}}, "containers": [_c("api"), _c("setup", "exited")]}
    assert ac.find_problems(h, want={"api": True}, cert_days=200, versions=("0.11.0", "0.11.0")) == []


def test_containers_services_backups_certificates_and_versions():
    h = {"checks": {
            "api": {"name": "API", "status": "up", "response_ms": 3},
            "documents": {"name": "Documents", "status": "up", "response_ms": 1450},
            "drawio": {"name": "Diagrams", "status": "down", "detail": "not reachable"},
            "reports": {"name": "Reports", "status": "off"},
            "backups": {"name": "Backup", "status": "warning", "detail": "no backup yet"},
            "ops": {"name": "Operations helper", "status": "up"}},
         "containers": [_c("api"), _c("dms", memory_percent=98.1, restarts=3), _c("drawio", "exited", exit_code=137, oom_killed=True),
                        _c("reports", "exited"), _c("keycloak", health="unhealthy"), _c("reports-init", "exited", exit_code=1)]}
    out = ac.find_problems(h, want={"api": True, "dms": True, "drawio": True, "reports": False, "keycloak": True},
                           cert_days=12, versions=("0.10.1", "0.11.0"))
    texts = [p["text"] for p in out]
    reds = [p["text"] for p in out if p["level"] == "red"]
    assert any("drawio was stopped for running out of memory" in t for t in reds)
    assert any("drawio is exited, exit code 137 but should be running" in t for t in reds)
    assert any("keycloak: Docker says unhealthy" in t for t in reds)
    assert any("reports-init (set-up) ended with exit code 1" in t for t in reds)
    assert any("Diagrams is down" in t for t in reds)
    assert any("database is at version 0.10.1" in t for t in reds)
    assert not any(t.startswith("reports is") for t in texts)            # switched off: not a problem
    assert any("dms uses 98% of its memory limit" in t for t in texts) and any("dms restarted 3 times" in t for t in texts)
    assert any("Documents answered slowly (1450 ms)" in t for t in texts)
    assert "no backup yet" in texts
    assert any("certificate expires in 12 days" in t for t in texts)
    assert out[0]["level"] == "red" and out[-1]["level"] == "amber"     # red first


def test_default_passwords_on_a_server_by_name_only():
    env = {"EAX_DB_PASSWORD": "P^55w0rd1234&", "EAX_OPS_TOKEN": "eax-ops-laptop", "EAX_KC_ADMIN_PASSWORD": "Str0ng!",
           "EAX_HOSTNAME": "P^55w0rd1234&"}
    assert ac.default_secrets(env) == ["EAX_DB_PASSWORD", "EAX_OPS_TOKEN"]
    out = ac.find_problems({"checks": {}, "containers": []}, deployment="server", env=env)
    assert len(out) == 1 and "EAX_DB_PASSWORD, EAX_OPS_TOKEN" in out[0]["text"] and "P^55" not in out[0]["text"]
    assert ac.find_problems({"checks": {}, "containers": []}, deployment="laptop", env=env) == []   # fine on a laptop


def test_only_it_and_super_admins_and_in_the_background():
    src = (ROOT / "eax" / "api" / "admin.py").read_text()
    i = src.index('"/admin/sign-in-check"')
    block = src[i:i + 900]
    assert 'require_auth("system.operate")' in block and ".defer(" in block and "queueing_lock" in block
    assert "eax.admin_sign_in_check" in (ROOT / "eax" / "jobs.py").read_text()
    assert "'system'" in (ROOT / "migrations" / "sql" / "0018_notifications.sql").read_text()
