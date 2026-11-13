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
    for what in ("Sample insurance model", "test_model_steps", "versions_demo", "first_measurements", "operations.startup_parts"):
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
    # the set-up holds Reports back only for what the server needs; the content waits for the sample data, in the
    # background, once Reports has started (R2.39)
    init = (REPO / "deploy" / "superset" / "superset-init.sh").read_text()
    content = (REPO / "deploy" / "superset" / "reports-content.sh").read_text()
    start = (REPO / "deploy" / "superset" / "reports-start.sh").read_text()
    assert "superset db upgrade" in init and "eax_import_reports" not in init and "api/startup" not in init
    assert "http://api:8000/api/startup" in content and content.index("api/startup") < content.index("python /app/eax/eax_reports_init.py")
    assert 'json.load(r).get("parts", [])' in content            # the public answer lists the parts, "later" among them
    assert "reports-content.sh" in start and start.index("&") < start.index("exec")
    assert compose["services"]["reports"]["command"] == ["/bin/sh", "/app/eax/reports-start.sh"]


def test_pictures_save_as_drawn_views():
    """D408 (replaces D256): no picture opens a loose copy in draw.io; each saves as a drawn view or downloads."""
    web = REPO / "services" / "web" / "src"
    ex = (web / "exporting.js").read_text()
    assert "export function openDrawio(" not in ex and "export function drawioXml(" in ex and "export function tidy(" in ex
    for f in web.glob("*.jsx"):
        assert "openDrawio" not in f.read_text(), f.name


def test_the_helper_starts_reports_left_created_after_its_set_up(tmp_path, monkeypatch):
    """R2.23 (owner, 12 Nov 2026): after a clean restart Reports stayed "reports: Created" (its set-up had finished, but
    the `eax up` waiting to start it had ended); the operations helper starts it, unless Reports is switched off or its
    set-up did not finish well."""
    import importlib.util
    from pathlib import Path
    work = tmp_path / "work"
    work.mkdir()
    (work / "eaexplorer.env").write_text("EAX_TIMEZONE=UTC\n")
    for k in ("EAX_WORK_MOUNT", "EAX_BACKUP_MOUNT", "EAX_REPO_MOUNT"):
        monkeypatch.setenv(k, str(work))
    spec = importlib.util.spec_from_file_location("ops_after_setup", Path(__file__).resolve().parents[2] / "ops" / "ops.py")
    ops = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ops)
    rows = [{"service": "reports-init", "name": "eaexplorer-reports-init-1", "state": "exited", "status": "Exited (0) 2 minutes ago"},
            {"service": "reports", "name": "eaexplorer-reports-1", "state": "created", "status": "Created"}]
    assert ops.created_after_setup(rows, {"reports": True}) == ["eaexplorer-reports-1"]
    assert ops.created_after_setup(rows, {"reports": False}) == []                      # switched off: left created
    rows[0]["status"] = "Exited (1) 2 minutes ago"
    assert ops.created_after_setup(rows, {"reports": True}) == []                       # its set-up failed
    rows[0]["state"], rows[0]["status"] = "running", "Up 1 minute"
    assert ops.created_after_setup(rows, {"reports": True}) == []                       # still setting up


def test_a_loader_that_stopped_is_shown_as_stopped_not_loading_for_ever():
    """R2.39 (owner, 12 Nov 2026: the API ran out of memory; Sample data stayed at "loading 9 of 29"): a part that has
    not moved for STALE_MINUTES is shown as stopped, saying the next start (or the job) carries on."""
    from eax import startup_status as ss

    class Conn:
        def __init__(self, row):
            self.row = row

        def execute(self, *a, **k):
            row = self.row

            class R:
                def mappings(self):
                    return self

                def first(self):
                    return row
            return R()
    later = ss._later(Conn({"part": "later", "name": "Sample data", "state": "starting", "done": 9, "total": 29,
                            "detail": "", "started_at": None, "finished_at": None, "stale": True}))
    assert later["status"] == "down" and "stopped at 9 of 29" in later["detail"]
    packs = ss._packs(Conn({"state": "starting", "done": 0, "total": 97, "detail": "", "stale": True}))
    assert packs["status"] == "down" and "stopped at 0 of 97" in packs["detail"]


def test_the_api_has_room_on_a_laptop():
    """R2.39: 768 MB was not enough for the API servers, the job runner and the start-up work together."""
    import yaml
    laptop = yaml.safe_load((REPO / "deploy" / "compose" / "docker-compose.laptop.yml").read_text())
    assert laptop["services"]["api"]["deploy"]["resources"]["limits"]["memory"] == "2g"
