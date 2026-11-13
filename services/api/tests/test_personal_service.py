"""R2.53 (D632; owner, 12 Nov 2026, 21:43 and 13 Nov 2026): each person's data in the personal schema and served by the
personal data service. Checked on PostgreSQL on 13 Nov 2026: a notification with its model's name, its webhook payload,
read; a request sent, listed, commented; a saved view and two favourites listed with their names; skills and a setting
kept; the same with EAX_PERSONAL_DB_URL pointing at another existing database (ensure and copy first); with the personal
schema unreachable, a notification waited in core.personal_outbox and was sent by flush when it was back."""

from __future__ import annotations

import inspect
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
MOVED = ("notifications", "notification_recipients", "requests", "request_comments", "favourites", "saved_views")


def test_the_migration():
    sql = (REPO / "services/api/migrations/sql/0056_personal_schema.sql").read_text()
    for t in MOVED:
        assert re.search(rf"ALTER TABLE IF EXISTS core\.{t}\s+SET SCHEMA personal;", sql), t
    assert re.search(r"ALTER TABLE IF EXISTS proj\.user_skills\s+SET SCHEMA personal;", sql)
    for fk in ("saved_views_model_id_fkey", "favourites_model_id_fkey", "notifications_model_id_fkey",
               "webhook_deliveries_notification_id_fkey"):
        assert f"DROP CONSTRAINT IF EXISTS {fk};" in sql, fk            # nothing crosses into or out of the schema
    assert "CREATE TABLE IF NOT EXISTS personal.settings" in sql and "CREATE TABLE IF NOT EXISTS core.personal_outbox" in sql
    assert "CREATE DATABASE" not in sql.upper()


def test_no_code_names_them_where_they_were():
    pat = re.compile(r"core\.(" + "|".join(MOVED) + r")\b|proj\.user_skills\b")
    bad = [str(f.relative_to(REPO)) for root in ("services/api/eax", "services/ops", "eaxcli") for f in (REPO / root).rglob("*.py")
           if "migrations" not in f.parts and pat.search(f.read_text(errors="ignore"))]
    assert not bad, bad


def test_no_query_joins_the_personal_schema_to_the_repository():
    for name in ("notify", "tickets", "workspace", "skills", "surveys", "personal"):
        src = (REPO / f"services/api/eax/{name}.py").read_text()
        for q in re.findall(r'"""(.*?)"""', src, re.S) + re.findall(r'"([^"\n]*FROM personal[^"\n]*)"', src):
            if "personal." in q:
                assert not re.search(r"\b(core|proj|audit)\.\w+", q), (name, q[:160])


def test_a_notification_waits_while_the_service_is_away(monkeypatch):
    from eax import notify
    from eax import personal as P

    def away(conn, n, people):
        raise P.Unavailable("connection refused")
    queued = []
    monkeypatch.setattr(P, "write_notification", away)
    monkeypatch.setattr(P, "queue", lambda conn, payload, why="": queued.append((payload, why)))
    monkeypatch.setattr(notify, "_rows", lambda conn, sql, **p: [])
    out = notify.create(object(), kind="x", category="system", title="Hello", actor="system", recipients=["thandi"])
    assert out is None and queued and queued[0][0]["people"] == ["thandi"] and queued[0][0]["notification"]["title"] == "Hello"
    assert "connection refused" in queued[0][1]
    assert "personal.flush(conn)" in (REPO / "services/api/eax/jobs.py").read_text()


def test_the_routes_are_the_personal_services():
    for f, paths in (("notifications.py", ("/notifications", "/notifications/counts", "/requests", "/requests/<rid>/status")),
                     ("grids.py", ("/saved-views", "/favourites")), ("projects.py", ("/skills",)), ("personal.py", ("/settings",))):
        src = (REPO / "services/api/eax/api" / f).read_text()
        for p in paths:
            assert (f'@personal_blp.route("{p}")' in src) or (f == "personal.py" and f'@blp.route("{p}")' in src), (f, p)
    assert 'Blueprint("personal", __name__, url_prefix="/api/v1/me"' in (REPO / "services/api/eax/api/personal.py").read_text()
    from eax import service_split as ss
    assert ss.SERVICES["personal"]["blueprints"] == ("personal",)


def test_a_purged_model_takes_its_personal_rows():
    from eax.testing import fixtures
    src = inspect.getsource(fixtures._purge_models)
    assert src.index("personal.forget_models(conn, model_ids)") < src.index('DELETE FROM core.models WHERE id = ANY(:ids)')


def test_the_screens_and_the_front_door():
    web = REPO / "services/web/src"
    for f in ("Notifications.jsx", "PinButton.jsx", "GridPages.jsx", "Areas.jsx"):
        src = (web / f).read_text()
        assert not re.search(r"/api/v1/(notifications|requests|saved-views|favourites)", src), f
    tpl = (REPO / "deploy/proxy/templates/default.conf.template").read_text()
    assert tpl.count("error_page 502 504 /eax-unavailable-personal.json;") == 3
    import json
    msg = json.loads((REPO / "deploy/proxy/static/eax-unavailable-personal.json").read_text())["message"]
    assert "rest of EA Explorer works" in msg


def test_databases_knows_the_personal_tables():
    from eax import databases as dbs
    assert dbs.TABLES["personal"][0] == "personal.notifications" and "personal.settings" in dbs.TABLES["personal"]
