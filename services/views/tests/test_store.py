"""The views service's store against a real database (skipped without one): versions, conflicts, keeping versions,
tags, copies, the model's own views and a model's removal (D354, D404 to D407)."""

import os
import uuid

import pytest

from viewsvc import drawio

psycopg = pytest.importorskip("psycopg")
DB = os.environ.get("EAX_VIEWS_TEST_DB")
pytestmark = pytest.mark.skipif(not DB, reason="set EAX_VIEWS_TEST_DB (a database with 0001_views applied) to run")

M, M2 = str(uuid.uuid4()), str(uuid.uuid4())
E1, E2 = str(uuid.uuid4()), str(uuid.uuid4())


def _xml(*ents):
    cells = "".join(f'<object id="c{i}" label="E{i}" ea_id="{e}" ea_type="ApplicationComponent"><mxCell vertex="1" parent="1"/></object>'
                    for i, e in enumerate(ents))
    return f'<mxfile><diagram id="d" name="V"><mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>{cells}</root></mxGraphModel></diagram></mxfile>'


@pytest.fixture()
def conn():
    from viewsvc import config, db
    config.get_settings.cache_clear()
    with db.connect() as c:
        yield c
        c.rollback()


def test_versions_and_the_conflict(conn):
    from viewsvc import store as S
    v = S.create(conn, M, "ann", {"name": "Landscape", "xml": _xml(E1)}, marker="2026-11-01T00:00:00+00:00")
    assert v["version"] == 1 and v["summary"]["entities"] == 1
    S.save(conn, M, "bob", v["id"], {"xml": _xml(E1, E2), "base_version": 1})
    with pytest.raises(drawio.Refused) as exc:                     # ann saves on version 1: bob saved since
        S.save(conn, M, "ann", v["id"], {"xml": _xml(E2), "base_version": 1})
    assert exc.value.status == 409 and exc.value.details["conflict"]["saved_by"] == "bob"
    got = S.save(conn, M, "ann", v["id"], {"xml": _xml(E2), "base_version": 1, "force": True})
    assert got["version"] == 3
    assert [x["version"] for x in S.versions(conn, M, v["id"])["versions"]] == [3, 2, 1]
    listed = S.list_views(conn, M, marker="2026-12-01T00:00:00+00:00")["views"]
    assert listed[0]["model_changed_since"] is True
    with pytest.raises(drawio.Refused):                             # names are unique in a model
        S.create(conn, M, "ann", {"name": "landscape"})


def test_tags_hold_versions_and_copies_bind_to_the_other_model(conn):
    from viewsvc import store as S
    v = S.create(conn, M, "ann", {"name": "Held", "xml": _xml(E1, E2)})
    tag = str(uuid.uuid4())
    held = S.hold_for_tag(conn, M, tag)
    assert any(h["name"] == "Held" and h["version"] == 1 for h in held)
    S.save(conn, M, "ann", v["id"], {"xml": _xml(E1), "base_version": 1})
    assert S.tag_view(conn, M, tag, "Held")["version"] == 1
    S.add_own(conn, M, "ann", {"name": "Our apps", "element_types": ["ApplicationComponent"], "copied_from": "VP-01"})
    got = S.copy_model(conn, M, M2, "ann", {E1: E2}, {})
    assert got["drawn_views"] >= 1 and got["own_views"] == 1
    copy = S.get_view(conn, M2, "Held")
    assert copy["version"] == 1 and E2 in copy["xml"] and E1 not in copy["xml"]
    assert S.own_views(conn, M2)["views"][0]["code"].startswith("MV-")
    gone = S.delete_model(conn, M2, "ann")
    assert gone["drawn_views"] >= 1 and S.list_views(conn, M2)["views"] == []


def test_keeping_versions_never_drops_a_held_or_the_latest(conn, monkeypatch):
    from viewsvc import config
    from viewsvc import store as S
    v = S.create(conn, M, "ann", {"name": "Pruned", "xml": _xml(E1)})
    tag = str(uuid.uuid4())
    S.hold_for_tag(conn, M, tag)                                    # version 1 held
    monkeypatch.setenv("EAX_VIEWS_KEEP_VERSIONS", "2")
    config.get_settings.cache_clear()
    for n in range(2, 6):
        S.save(conn, M, "ann", v["id"], {"xml": _xml(E1, E2) if n % 2 else _xml(E2), "base_version": n - 1})
    kept = [x["version"] for x in S.versions(conn, M, v["id"])["versions"]]
    assert kept == [5, 4, 1]                                        # the last two, and the one the tag holds
    config.get_settings.cache_clear()


def test_own_views_by_code_name_or_id(conn):
    from viewsvc import store as S
    v = S.add_own(conn, M, "ann", {"name": "Claims apps", "element_types": ["ApplicationComponent"], "copied_from": "VP-03"})
    for key in (v["code"], v["id"], "claims apps"):
        assert S.own_view(conn, M, key)["id"] == v["id"]
    S.change_own(conn, M, "bob", v["code"], {"purpose": "Ours", "element_types": ["ApplicationComponent", "DataObject"]})
    got = S.own_view(conn, M, v["code"])
    assert got["purpose"] == "Ours" and got["copied_from"] == "VP-03" and len(got["element_types"]) == 2
    with pytest.raises(drawio.Refused):
        S.add_own(conn, M, "ann", {"name": "Empty", "element_types": []})
    S.delete_own(conn, M, "ann", v["code"])
    with pytest.raises(drawio.Refused):
        S.own_view(conn, M, v["code"])


def test_a_model_backup_put_back_over_itself_replaces_its_views(conn):
    """D410: the model's views now go and the backup's come back, with their versions and its own views."""
    from viewsvc import store as S
    m = str(uuid.uuid4())
    v = S.create(conn, m, "ann", {"name": "Kept", "xml": _xml(E1)})
    S.save(conn, m, "ann", v["id"], {"xml": _xml(E1, E2), "base_version": 1})
    S.add_own(conn, m, "ann", {"name": "Our apps", "element_types": ["ApplicationComponent"]})
    backup = S.export_model(conn, m)
    S.create(conn, m, "bob", {"name": "Made after the backup", "xml": _xml(E2)})
    S.save(conn, m, "bob", v["id"], {"xml": _xml(E2), "base_version": 2})
    S.import_model(conn, m, backup, "admin", replace=True)
    names = sorted(x["name"] for x in S.list_views(conn, m)["views"])
    assert names == ["Kept"]
    kept = S.list_views(conn, m)["views"][0]
    assert [x["version"] for x in S.versions(conn, m, kept["id"])["versions"]] == [2, 1]
    assert [o["name"] for o in S.own_views(conn, m)["views"]] == ["Our apps"]
