"""Phase 12.1 (D255, D256): the start-up in two tiers, the start-up status, and pictures opened in draw.io."""

from pathlib import Path

import yaml

from eax import startup_status as ss
from eax.seed import build

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def test_migration_and_version():
    sql = (ROOT / "migrations" / "sql" / "0021_startup.sql").read_text()
    assert "'0.13.1'" in sql and "CREATE TABLE core.startup_parts" in sql
    assert "TRIGGER" not in sql.upper() and "FUNCTION" not in sql.upper()     # no logic in the database (D248)
    assert 'version = "0.13.1"' in (ROOT / "version.toml").read_text()


def test_the_test_models_load_step_by_step():
    steps = build.test_model_steps()
    assert [k for k, *_ in steps] == ["fynbos-group", "fynbos-life-commercial", "karoo-re", "lean", "demo-estate", "quality-demo"]
    for _key, label, check, sql in steps:
        assert label and check.startswith("SELECT 1") and sql.startswith("SELECT set_config('eax.actor'")
    assert build.test_models_sql() == "".join(sql for *_x, sql in steps)


def test_the_core_seed_leaves_the_sample_for_later():
    main = (ROOT / "eax" / "seed" / "__main__.py").read_text()
    assert "with_sample=False" in main and "test_models_sql" not in main
    later = (ROOT / "eax" / "seed" / "later.py").read_text()
    for what in ("Sample insurance model", "test_model_steps", "versions_demo", "first_measurements", "core.startup_parts"):
        assert what in later
    entry = (ROOT / "entrypoint.sh").read_text()
    assert "python -m eax.startup once later -- python -m eax.seed.later &" in entry
    assert entry.index("gunicorn") < entry.index("eax.seed.later")      # after the API has started


def test_container_states():
    cs = ss.container_state
    assert cs({"service": "api", "state": "running", "status": "Up 2 minutes (healthy)"}) == "up"
    assert cs({"service": "api", "state": "running", "status": "Up 5 seconds (health: starting)"}) == "starting"
    assert cs({"service": "dms", "state": "running", "status": "Up 1 minute (unhealthy)"}) == "down"
    assert cs({"service": "drawio", "state": "created", "status": "Created"}) == "starting"
    assert cs({"service": "dms", "state": "exited", "status": "Exited (1) 1 minute ago"}) == "down"
    assert cs({"service": "reports-init", "state": "running", "status": "Up 30 seconds"}) == "starting"
    assert cs({"service": "reports-init", "state": "exited", "status": "Exited (0) 2 minutes ago"}) == "up"
    assert cs({"service": "reports-init", "state": "exited", "status": "Exited (2) 2 minutes ago"}) == "down"


def test_part_states():
    now = ss.STARTED + 60
    up, off, down = {"status": "up", "detail": "OK"}, {"status": "off", "detail": "switched off"}, {"status": "down", "detail": "refused"}
    assert ss._part_state(up, None, ["drawio"], now)[0] == "up"
    assert ss._part_state(off, [], ["drawio"], now)[0] == "off"
    assert ss._part_state(down, None, ["drawio"], now)[0] == "starting"                 # no helper, just started
    assert ss._part_state(down, None, ["drawio"], ss.STARTED + 3600)[0] == "down"       # no helper, long after
    running_init = [{"service": "reports-init", "state": "running", "status": "Up 10 seconds"}]
    assert ss._part_state(down, running_init, ["reports-init", "reports"], now) == ("starting", "reports-init: setting up")
    failed = [{"service": "dms-broker", "state": "running", "status": "Up"}, {"service": "dms", "state": "exited", "status": "Exited (1)"}]
    assert ss._part_state(down, failed, ["dms-broker", "dms"], now)[0] == "down"
    assert ss._finish({"parts": [{"status": "up"}], "later": {"status": "starting"}})["overall"] == "starting"
    assert ss._finish({"parts": [{"status": "up"}, {"status": "off"}], "later": None})["overall"] == "up"


def test_compose_and_scripts_start_in_two_tiers():
    compose = yaml.safe_load((REPO / "docker-compose.yml").read_text())
    assert "healthcheck" in compose["services"]["keycloak"] and "healthcheck" in compose["services"]["api"]
    ps1, sh = (REPO / "eax.ps1").read_text(), (REPO / "eax.sh").read_text()
    for core in ("db", "setup", "proxy", "web", "keycloak", "api"):
        assert f'"{core}"' in ps1.split("$CoreServices = @(")[1].split(")")[0]
        assert core in sh.split('CORE_SERVICES="')[1].split('"')[0].split()
    assert "Wait-Core" in ps1 and "start-later" in ps1 and "--no-deps" in ps1
    assert "wait_core" in sh and "start-later" in sh and "--no-deps" in sh
    init = (REPO / "deploy" / "superset" / "superset-init.sh").read_text()
    assert "http://api:8000/api/startup" in init and init.index("api/startup") < init.index("python /app/eax/eax_reports_init.py")


def test_pictures_open_in_drawio():
    web = REPO / "services" / "web" / "src"
    ex = (web / "exporting.js").read_text()
    assert "export function openDrawio(" in ex and "/drawio/?title=" in ex and "#R" in ex and "deflate-raw" in ex
    for f in web.glob("*.jsx"):
        text = f.read_text()
        assert "downloadDrawio" not in text, f.name
        assert ">.drawio</button>" not in text, f.name
