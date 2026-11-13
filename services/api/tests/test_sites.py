"""Sites (R2.1, D646; owner, 13 Nov 2026): one shared list in the farm schema, Local first, a green, amber or red health
from each site's public heartbeat, only Super Admins change it, a deployed site added when its deployment finishes."""

from __future__ import annotations

from pathlib import Path

import pytest

API = Path(__file__).resolve().parents[1]
WEB = API.parent / "web" / "src"


def test_health_from_a_heartbeat():
    from eax import sites
    assert sites.health_of(None) == ("red", "does not answer", "")
    assert sites.health_of({"status": "ok", "database": {"version": "1.1.0"}}) == ("green", "working", "1.1.0")
    assert sites.health_of({"status": "warning"})[0] == "amber"
    assert sites.health_of({"status": "ok", "maintenance": {"what": "restore"}})[0] == "amber"
    assert sites.health_of({"status": "degraded"})[0] == "red"


class _Conn:
    """A tiny farm.sites in memory, enough for the module's statements."""
    def __init__(self):
        self.rows = []

    def execute(self, sql, p=None):
        q, p = str(sql), p or {}
        out = []
        if q.startswith("INSERT INTO farm.sites"):
            row = {"id": f"g{len(self.rows)}", "guid": f"g{len(self.rows)}", "name": p.get("name", "Local"),
                   "url": p.get("url") or p.get("u"), "note": p.get("note", "This site"), "source": p.get("source", "local"),
                   "deployment": p.get("dep"), "health": "unknown", "created_by": p.get("by", "system")}
            self.rows.append(row)
            out = [{"guid": row["guid"]}]
        elif "WHERE source = 'local'" in q:
            out = [r for r in self.rows if r["source"] == "local"]
        elif "lower(name) = lower(:n) OR lower(url) = lower(:u)" in q:
            out = [r for r in self.rows if r["name"].lower() == p["n"].lower() or r["url"].lower() == p["u"].lower()]
        elif "lower(url) = lower(:u) OR deployment = :d" in q:
            out = [r for r in self.rows if r["url"].lower() == p["u"].lower() or r["deployment"] == p["d"]]
        elif "lower(name) = lower(:n)" in q:
            out = [r for r in self.rows if r["name"].lower() == p["n"].lower()]
        elif "WHERE guid = CAST(:g AS uuid)" in q and q.startswith("SELECT"):
            out = [r for r in self.rows if r["guid"] == p["g"]]
        elif q.startswith("SELECT"):
            out = list(self.rows)
        return type("R", (), {"mappings": lambda s: type("M", (), {"all": lambda s2: out})(),
                              "scalar_one": lambda s: out[0]["guid"]})()


@pytest.fixture()
def farm(monkeypatch):
    from eax import sites
    c = _Conn()
    monkeypatch.setattr(sites, "_db", lambda conn: c)
    monkeypatch.setattr(sites, "local_url", lambda: "https://localhost")
    return sites, c


SA = type("U", (), {"username": "sa", "roles": ("super-admin",)})()
BOB = type("U", (), {"username": "bob", "roles": ("user",)})()


def test_local_is_always_there_and_only_super_admins_change_the_list(farm):
    sites, c = farm
    rows = sites.listing(None)
    assert [(r["name"], r["source"]) for r in rows] == [("Local", "local")]
    from eax.metamodel_edit import EditError
    with pytest.raises(EditError, match="Only a Super Admin"):
        sites.create(None, BOB, {"name": "Prod", "url": "https://ea.example.org"})
    sites.create(None, SA, {"name": "Prod", "url": "https://ea.example.org/"})
    assert c.rows[-1]["url"] == "https://ea.example.org"
    with pytest.raises(EditError, match="already a site"):
        sites.create(None, SA, {"name": "prod", "url": "https://other.example.org"})
    with pytest.raises(EditError, match="web address"):
        sites.create(None, SA, {"name": "Bad", "url": "ftp://x"})


def test_a_finished_deployment_adds_its_site_once(farm):
    sites, c = farm
    runs = [{"run_id": "r1", "target": "ea2.example.org", "status": "done", "plan": False, "started_by": "sa"},
            {"run_id": "r2", "target": "ea3.example.org", "status": "failed"},
            {"run_id": "r3", "target": "ea4.example.org", "status": "done", "plan": True},
            {"run_id": "r4", "target": "aws:box", "status": "done"}]
    assert sites.from_deployments(None, runs) == 1
    assert (c.rows[-1]["name"], c.rows[-1]["url"], c.rows[-1]["source"]) == ("ea2", "https://ea2.example.org", "deployed")
    assert sites.from_deployments(None, runs) == 0


def test_everyone_sees_sites_in_the_picker_and_the_job_checks_them():
    jobs = (API / "eax" / "jobs.py").read_text()
    assert 'name="eax.sites_health"' in jobs and '@app.periodic(cron="*/5 * * * *")' in jobs
    admin = (API / "eax" / "api" / "admin.py").read_text()
    i = admin.index('@blp.route("/sites")')
    assert "@require_auth()" in admin[i:i + 400]                     # anyone signed in reads it
    assert "sites.from_deployments" in (API / "eax" / "deploys.py").read_text()
    from eax import databases
    assert databases.TABLES["farm"] == ("farm.sites",) and databases.BY_KEY["farm"].setting == "EAX_FARM_DB_URL"
    sql = (API / "migrations" / "sql" / "0061_farm_sites.sql").read_text()
    assert "CREATE SCHEMA IF NOT EXISTS farm" in sql and "TRIGGER" not in sql.upper()
    assert 'kind === "farm-sites"' in (WEB / "TopMenu.jsx").read_text()
    assert "function SitesTable" in (WEB / "Farm.jsx").read_text()


def test_include_archived_finds_archived_models_by_what_they_hold(monkeypatch):
    """R2.41 (D647): Find with Include archived searches the archive database; deleted ones stay out, for everyone."""
    import contextlib

    from eax import archive
    seen = {}

    class AC:
        def execute(self, sql, p):
            seen["sql"], seen["p"] = str(sql), p
            rows = [{"id": 1, "kind": "model", "guid": "g", "name": "Old CRM", "summary": {"description": "d"},
                     "admins": ["bob"], "moved_at": None, "contents": "Application Component: CRM\nBusiness Actor: Sales"},
                    {"id": 2, "kind": "project", "guid": "h", "name": "P", "summary": {}, "admins": ["eve"], "moved_at": None,
                     "contents": "Model: CRM landscape"}]
            return type("R", (), {"mappings": lambda s: rows})()
    monkeypatch.setattr(archive, "beside", lambda key, conn: contextlib.nullcontext(AC()))
    out = archive.search(None, BOB, "crm")
    assert "state = 'archived'" in seen["sql"] and seen["p"]["l"] == "%crm%"
    assert [o["name"] for o in out] == ["Old CRM"] and out[0]["matches"] == ["Application Component: CRM"]
    assert len(archive.search(None, SA, "crm")) == 2 and archive.search(None, SA, "") == []
    grids = (API / "eax" / "api" / "grids.py").read_text()
    assert 'a.get("archived") in ("1", "true", "yes")' in grids
    assert "Include archived" in (WEB / "GridPages.jsx").read_text() and "<ArchivedRows" in (WEB / "Areas.jsx").read_text()
    mig = (API / "migrations" / "sql" / "0062_archive_contents.sql").read_text()
    assert "ADD COLUMN IF NOT EXISTS contents text" in mig


def test_every_foreign_key_has_an_index_but_the_listed_few():
    """R2.24 part 4 (D648; owner, 13 Nov 2026: "Index everything as you see fit"; "There will never be cross DB or cross
    schema foreign keys"): one migration indexes every foreign key but status_code on the five busiest tables; the
    database check fails on any other unindexed one, and on any foreign key across schemas."""
    from eax.testing import db_checks as d
    sql = (API / "migrations" / "sql" / "0063_foreign_key_indexes.sql").read_text()
    for t in ("entities", "relationships", "attribute_values", "allowed_relationships", "item_attributes"):
        assert f"core.{t}.status_code" in d.FK_INDEX_EXCEPTIONS and f"'{t}'" in sql
    assert len(d.FK_INDEX_EXCEPTIONS) == 5
    assert "library_models" in sql and "IS NOT NULL" in sql and "CREATE TRIGGER" not in sql.upper()
    checks = {n: (q, o) for n, q, o in d.CHECKS}
    q, o = checks["foreign keys have an index (speed)"]
    assert o == "failed" and "core.entities.status_code" in q and "('core', 'proj')" not in q   # every schema now
    q, o = checks["no foreign key crosses schemas"]
    assert o == "failed" and "t.relnamespace <> p.relnamespace" in q
    from eax.testing import health
    assert health.importance("db", "foreign keys have an index (speed)") == "non-critical"   # speed, not function
    assert health.importance("db", "no foreign key crosses schemas") == "critical"


def test_two_models_made_at_once_do_not_collide_in_model_ancestors():
    """The owner's full test (13 Nov 2026): "duplicate key value violates unique constraint model_ancestors_pkey" when the
    self-test made its models while the sample data was still loading. The rebuild takes its turn and skips pairs
    already there (D651)."""
    sql = (API / "migrations" / "sql" / "0065_model_ancestors_concurrency.sql").read_text()
    body = sql[sql.index("CREATE OR REPLACE FUNCTION core.refresh_model_ancestors()"):]
    assert body.index("pg_advisory_xact_lock") < body.index("DELETE FROM core.model_ancestors")
    assert "ON CONFLICT (model_id, ancestor_id) DO NOTHING" in body
