"""Backups carry everything (owner, 10 Nov 2026, D410): every database and every volume with state in an infrastructure
backup, and every part of a model, a project and the organisation in an application backup. No database or Docker needed."""

from __future__ import annotations

import importlib.util
import io
import json
import re
import zipfile
from pathlib import Path

import yaml

from eax import model_ops as mo
from eax import org_backup as ob
from eax import project_backup as pb

ROOT = Path(__file__).resolve().parents[1]          # services/api
REPO = ROOT.parents[1]
COMPOSE = yaml.safe_load((REPO / "docker-compose.yml").read_text())
BACKUP_SH = (REPO / "services" / "backup" / "backup.sh").read_text()
RESTORE_SH = (REPO / "services" / "backup" / "restore.sh").read_text()


def _ops():
    spec = importlib.util.spec_from_file_location("ops_coverage_test", REPO / "services" / "ops" / "ops.py")
    ops = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ops)
    return ops


def _volume(mount: str) -> str:
    """The named volume of a compose mount ("${EAX_DOCS_DIR:-eax-docs}:/mayan" -> eax-docs)."""
    src = mount.split(":/")[0]
    m = re.match(r"^\$\{[A-Z_]+:-([a-z0-9./-]+)\}$", src)
    return m.group(1) if m else src


# ---------------------------------------------------------------- infrastructure


def test_every_named_volume_is_backed_up_or_said_not_needed():
    ops = _ops()
    volumes = set(COMPOSE["volumes"])
    backed = {vol for vol, _what in ops.FILE_SETS.values() if not vol.startswith("./")}   # ./persist: a folder (D558)
    assert volumes == backed | set(ops.NOT_NEEDED), (volumes - backed - set(ops.NOT_NEEDED), (backed | set(ops.NOT_NEEDED)) - volumes)
    assert not backed & set(ops.NOT_NEEDED)
    assert all(len(why) > 20 for why in ops.NOT_NEEDED.values())          # each with its reason


def test_the_backup_container_mounts_every_file_set_where_the_scripts_look():
    ops = _ops()
    mounts = {_volume(m): m.split(":")[-1].split()[0] for m in COMPOSE["services"]["backup"]["volumes"]}
    folders = {"documents": "/mayan", "tls": "/tls", "reports": "/superset-home", "imports": "/imports", "exports": "/exports",
               "persist": "/persist"}
    assert set(folders) == set(ops.FILE_SETS)
    for name, (vol, _what) in ops.FILE_SETS.items():
        assert mounts.get(vol) == folders[name], (name, vol)
        assert folders[name] in BACKUP_SH and folders[name] in RESTORE_SH, name
        assert re.search(rf"\b{name}\)\s+echo", RESTORE_SH), f"restore.sh: dest_of {name}"
    assert 'ALL_SETS="documents tls reports imports exports persist"' in RESTORE_SH
    for name in ops.FILE_SETS:                              # the restore plans name only sets the scripts know
        assert all(f in ops.FILE_SETS for plan in ops.RESTORE_WHAT.values() for f in plan["files"]), name
    assert set(ops.RESTORE_WHAT["full"]["files"]) == set(ops.FILE_SETS)


def test_every_service_with_a_database_is_in_the_backup():
    """A database on the main server is dumped by the loop over every database; one a service may have on a server of
    its own (an *_DB_HOST setting) is dumped from there: the backup container is told where, and backup.sh asks."""
    ops = _ops()
    services = COMPOSE["services"]
    on_main = set()
    elsewhere = set()
    for name, svc in services.items():
        env = svc.get("environment") or {}
        env = env if isinstance(env, dict) else dict(e.split("=", 1) for e in env)
        for k, v in env.items():
            if k.endswith("_DB_HOST") and k.startswith("EAX_"):
                elsewhere.add(k[len("EAX_"):-len("_DB_HOST")])
            if k in ("KC_DB_URL", "MAYAN_DATABASES") or k.endswith("_DB_NAME"):
                on_main.add(name)
            if k == "KC_DB_URL":
                assert "//${EAX_KEYCLOAK_DB_HOST:-db}:${EAX_KEYCLOAK_DB_PORT:-5432}/" in v   # the shared server unless set (R2.50)
            if k == "MAYAN_DATABASES":
                assert '"HOST":"${EAX_MAYAN_DB_HOST:-db}"' in v
    assert {"keycloak", "dms", "db"} <= on_main          # db: it makes the main database (EAX_DB_NAME)
    assert elsewhere == {"LIBRARY", "VIEWS", "SUPERSET"}
    # the backup container reads every database's setting (env_file, R2.50) and servers.sh finds those on their own
    # servers: the services' by host, EA Explorer's own by connection string
    assert services["backup"].get("env_file") == "work/eaexplorer.env"
    servers = (REPO / "services" / "backup" / "servers.sh").read_text()
    for kind in elsewhere | {"KEYCLOAK", "MAYAN"}:
        assert re.search(rf'"{kind} [^"]*"', servers), kind
    from eax import databases as dbs
    for d in dbs.DATABASES:
        if d.kind == "url":
            assert d.setting.removeprefix("EAX_").removesuffix("_DB_URL") in servers, d.setting
    # every database the first start makes, and the two services' own, is one the restore knows who uses
    initdb = (REPO / "deploy" / "postgres" / "initdb" / "01-databases.sh").read_text()
    made = set(re.findall(r"CREATE DATABASE (\w+)", initdb))
    assert made == {"keycloak", "superset", "mayan"}
    assert made | {"eaexplorer", "eaxlibrary", "eaxviews"} <= set(ops.USERS_OF)
    # nothing but scratch and in-between copies is left out of the dump loop
    loop = re.search(r"datname !~ '([^']+)'", BACKUP_SH).group(1)
    assert loop == "(__restoring|__before|_restore_test)$"


def test_restore_makes_missing_roles_and_goes_to_each_databases_server():
    for s in ("make_roles", "server_of", 'at "$DB" createdb', 'at "$DB" pg_restore', "globals-$DB.sql", 'on "$S" heal_dbs'):
        assert s in RESTORE_SH, s
    # the order: databases into copies, then file sets unpacked, then both swapped in; the helper restarts after
    order = [RESTORE_SH.index(s) for s in ("# ---------------------------------------------------------------- 1.",
                                           "# ---------------------------------------------------------------- 2.",
                                           "# ---------------------------------------------------------------- 3.")]
    assert order == sorted(order)
    assert 'pg_restore -C -l "$DUMPS/$DB.dump"' in RESTORE_SH          # the owner a dump names (it was missed without -C)


def test_the_manifest_says_what_is_in_it_and_what_is_not(tmp_path):
    ops = _ops()
    folder = tmp_path / "b"
    (folder / "databases").mkdir(parents=True)
    (folder / "files").mkdir()
    for n in ("eaexplorer", "keycloak", "superset", "mayan", "eaxlibrary", "eaxviews"):
        (folder / "databases" / f"{n}.dump").write_text(n)
    (folder / "databases" / "HOSTS").write_text("eaxlibrary lib.internal 5432\n")
    for n in ("documents", "tls", "reports"):
        (folder / "files" / f"{n}.tar.gz").write_text(n)
    parts = ops._parts(str(folder))
    c = ops.contents(parts)
    assert c["databases"]["eaxlibrary"] == "from lib.internal:5432" and c["databases"]["eaxviews"] == "from the main server"
    assert set(c["files"]) == {"documents", "tls", "reports"} and set(c["empty"]) == {"imports", "exports", "persist"}
    assert c["not_included"] == ops.NOT_NEEDED


def test_an_old_backup_still_restores_and_says_what_it_lacks(tmp_path, monkeypatch):
    from tests.test_backups_infra import _ops as fake_ops  # Docker replaced
    ops, _work, _backups, calls, _state = fake_ops(tmp_path, monkeypatch)
    m = ops._do_backup("old", "system", "scheduled", "0.12.0")          # documents only, as before D410
    r = ops._do_restore(m["name"], "full", "user_super_admin", "0.12.0")
    assert r["status"] == "ok" and r["files"] == ["documents"]
    assert any("does not have" in w and "reports' home" in w for w in r["warnings"])
    restore = next(c for c in calls if len(c) > 3 and c[3] == "restore.sh")
    assert restore[restore.index("--files") + 1] == "documents"


# ---------------------------------------------------------------- application: models, projects, the organisation


def test_entity_icons_travel_in_a_package():
    svg = b"<svg xmlns='http://www.w3.org/2000/svg'/>"
    png = b"\x89PNG\r\n\x1a\nxx"
    hist = {"metamodel_versions": [], "metamodel_changes": [],
            "icons": [{"key": "a-guid", "content_type": "image/svg+xml", "content": svg},
                      {"key": "b-guid", "content_type": "image/png", "content": png}],
            "views": {"drawn_views": [{"name": "Overview", "versions": [{"version_no": 1, "xml": "<mxfile/>"}]}], "own_views": []}}
    data, name, _ct = mo.write_package({"format": "eax-package/1", "model": {"name": "M"}}, {"entity_types": []},
                                       {"entities": {}, "relationships": []}, hist, "zip", "m")
    pkg = mo.read_package(data, name)
    got = {i["key"]: (i["content_type"], i["content"]) for i in pkg["icons"]}
    assert got == {"a-guid": ("image/svg+xml", svg), "b-guid": ("image/png", png)}
    assert pkg["views"]["drawn_views"][0]["versions"][0]["xml"] == "<mxfile/>"


def test_a_package_without_icons_reads_as_before():
    data, name, _ct = mo.write_package({"format": "eax-package/1", "model": {"name": "M"}}, {"entity_types": []},
                                       {"entities": {}, "relationships": []}, None, "zip", "m")
    assert mo.read_package(data, name)["icons"] is None


def test_restoring_a_model_over_itself_puts_its_views_and_icons_back():
    import inspect

    from eax import backups as bk
    src = inspect.getsource(bk._restore_over)
    assert "_views_back(" in src
    views_back = inspect.getsource(bk._views_back)
    assert "replace=True" in views_back and "load_icons" in views_back


def test_a_project_backup_carries_every_part():
    tables = {t for t, *_ in pb.TABLES}
    for t in ("documents", "canvases", "canvas_items", "key_questions", "stakeholders", "placeholder_views", "view_evidence",
              "project_models"):
        assert t in tables, t
    ev = next(x for x in pb.TABLES if x[0] == "view_evidence")
    assert ev[2] == {"item_id": "items", "question_id": "key_questions"}     # re-pointed at the restored rows
    assert "view_evidence" in pb.NEW_GUID


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)


class _Conn:
    """Enough of a connection for the organisation part: SELECTs answered from a dict, writes recorded."""

    def __init__(self, tables: dict, cols: dict):
        self.tables, self.cols, self.writes = tables, cols, []

    def execute(self, sql, params=None):
        q = str(sql)
        if "information_schema.columns" in q:
            return _Rows([(c, t) for c, t in self.cols.get(params["t"], {}).items()])
        m = re.search(r"FROM (core|proj|personal)\.(\w+)", q)
        if q.lstrip().startswith("SELECT") and m:
            return _Rows(self.tables.get(m.group(2), []))
        self.writes.append((q, params))
        return _Rows([])


def test_the_organisation_part_round_trip(monkeypatch):
    from eax import library_client as lc
    from eax import mayan
    from eax import projects as pj
    monkeypatch.setattr(pj, "_rows", lambda conn, sql, **k: conn.execute(sql).mappings().all())
    core = _Conn({"viewpoints": [{"id": 9, "code": "my-view", "guid": "g1", "name": "Mine", "spec": {"a": 1}}],
                  "user_skills": [{"username": "thandi", "skills": ["ArchiMate"]}]},          # personal schema (R2.53)
                 {"viewpoints": {"id": "int4", "code": "text", "guid": "uuid", "name": "text", "spec": "jsonb"},
                  "user_skills": {"username": "text", "skills": "jsonb"}})
    pc = _Conn({"board_members": [{"username": "sipho", "role": "chair"}],
                "project_templates": [{"code": "ours", "name": "Ours", "builtin": False}],
                "org_ref_entries": [{"id": 1, "guid": "e1", "mayan_document_id": 77, "file_name": "policy.pdf"}]},
               {"board_members": {"username": "text", "role": "text"},
                "project_templates": {"code": "text", "name": "text", "builtin": "bool"}})
    monkeypatch.setattr(lc, "export_org", lambda: {"format": "eax-library-org/1", "folders": [], "entries": [{"title": "Home"}]})
    monkeypatch.setattr(mayan, "download", lambda doc_id: (b"%PDF", "application/pdf", "policy.pdf"))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        info = ob.write(z, core, pc)
    assert info["counts"]["viewpoints"] == 1 and info["counts"]["library_entries"] == 1 and info["counts"]["reference_files"] == 1
    with zipfile.ZipFile(buf) as z:
        assert set(z.namelist()) == {"organisation/organisation.json", "organisation/library.json",
                                     "organisation/reference/e1/policy.pdf"}
    got = {}
    monkeypatch.setattr(lc, "import_org", lambda data, actor: got.setdefault("lib", (data, actor)) and {"entries": 1})
    core2, pc2 = _Conn({}, core.cols), _Conn({}, pc.cols)
    with zipfile.ZipFile(buf) as z:
        msg, problems = ob.restore(z, core2, pc2, "user_super_admin")
    assert problems == [] and msg.startswith("Organisation:")
    inserts = [q for q, _p in core2.writes + pc2.writes if q.lstrip().startswith("INSERT")]
    assert any("core.viewpoints" in q and "ON CONFLICT (code)" in q and "CAST(:spec AS jsonb)" in q for q in inserts)
    assert any("personal.user_skills" in q and "ON CONFLICT (username)" in q for q in inserts)   # R2.53, D632
    assert any("proj.project_templates" in q for q in inserts)
    assert not any("org_ref" in q for q in inserts)                       # carried, put back by an infrastructure restore
    vp = next(p for q, p in core2.writes if "core.viewpoints" in q)
    assert "id" not in vp and json.loads(vp["spec"]) == {"a": 1}
    assert got["lib"][0]["entries"] == [{"title": "Home"}] and got["lib"][1] == "user_super_admin"


def test_the_application_backup_writes_and_restores_the_organisation_part():
    import inspect

    from eax import backups as bk
    assert "_backup_organisation(conn, folder.parent, manifest)" in inspect.getsource(bk.application_backup)
    restore = inspect.getsource(bk.restore_application)
    assert "ob.restore(" in restore and "(d / ORG_FILE).is_file()" in restore     # an older backup without it still restores
    assert "ORG_FILE" in inspect.getsource(bk.application_zip) and "ORG_FILE" in inspect.getsource(bk.store_application_upload)


def test_the_enterprise_library_can_be_exported_and_put_back():
    lib = (REPO / "services" / "library" / "libsvc" / "library.py").read_text()
    app = (REPO / "services" / "library" / "libsvc" / "app.py").read_text()
    assert "def export_org(" in lib and "def import_org(" in lib and '"eax-library-org/1"' in lib
    assert "/internal/org/export" in app and "/internal/org/import" in app
