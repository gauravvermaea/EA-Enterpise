"""Drawn views (phases 28 and 29, D354, D397 to D403): notation, the draw.io file, icons, heat map bands, junction rules,
the migration and the routes. No database needed."""

from pathlib import Path

import pytest

from eax import drawn_views as dv
from eax import junctions, notation
from eax.metamodel_edit import EditError

ROOT = Path(__file__).resolve().parents[1]
E1, E2, E3 = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222", "33333333-3333-4333-8333-333333333333"
R1 = "44444444-4444-4444-8444-444444444444"


def test_every_archimate_element_has_a_look():
    from eax.seed import archimate4 as A
    for code in A.SPEC_TYPES:
        assert code in notation.ELEMENTS, code
        lk = notation.look(code, "B5FFFF")
        assert "mxgraph.archimate3" in lk["box"] and "fillColor=#B5FFFF" in lk["box"]
    assert notation.default_notation("Junction") == "Junction"
    assert notation.default_notation("ValueStreamStage") == ""              # an extension: a plain box
    plain = notation.look("", "")
    assert "rounded=1" in plain["box"] and notation.DEFAULT_COLOUR in plain["box"]
    assert notation.look("Junction", "")["junction"] is True


def test_colours_and_notations_are_checked():
    assert notation.clean_colour("#ecd678") == "ECD678"
    assert notation.clean_colour("") == ""
    for bad in ("red", "12345", "GGGGGG"):
        with pytest.raises(ValueError):
            notation.clean_colour(bad)
    assert notation.clean_notation("Capability") == "Capability"
    with pytest.raises(ValueError):
        notation.clean_notation("Spaceship")
    assert notation.type_look({"notation": "Goal", "fill_colour": "", "domain_colour": "CCCCFF"})["colour"] == "CCCCFF"
    assert notation.type_look({"notation": "Goal", "fill_colour": "ABCDEF", "domain_colour": "CCCCFF"})["colour"] == "ABCDEF"


def test_relationship_lines():
    assert "diamondThin" in notation.line("Composition") and "startFill=1" in notation.line("Composition")
    assert "startFill=0" in notation.line("Aggregation")
    assert "dashed=1" in notation.line("Realization") and "endFill=0" in notation.line("Realization")
    assert notation.line("Unknown").endswith("endArrow=open;")


def _ents():
    look = notation.look("ApplicationComponent", "B5FFFF")
    return [{"id": E1, "name": "Claims Platform", "type": "ApplicationComponent", "domain": "Application", "look": look},
            {"id": E2, "name": "Payments Hub", "type": "ApplicationComponent", "domain": "Application", "look": look,
             "icon": "data:image/svg+xml;base64,PHN2Zy8+"},
            {"id": E3, "name": "", "type": "Junction", "domain": "Common", "junction": "Or"}]


def test_build_and_parse_round_trip():
    rels = [{"id": R1, "type": "Flow", "source": E1, "target": E2},
            {"id": "55555555-5555-4555-8555-555555555555", "type": "Serving", "source": E2, "target": E1, "committed": False}]
    hidden = [{"rel": "Realization", "id": "66666666-6666-4666-8666-666666666666", "source": E1, "target": E3}]
    xml = dv.build_xml(_ents(), rels, placeholders=[{"type": "Capability", "name": "Not yet modelled"}], hidden=hidden)
    p = dv.parse(xml)
    assert sorted(p["entities"]) == sorted([E1, E2, E3])
    assert len(p["relationships"]) == 2
    assert [r["uncommitted"] for r in p["relationships"]].count(True) == 1
    assert p["placeholders"] == 1
    assert p["hidden"][0]["id"] == hidden[0]["id"]
    assert "image=data:image/svg+xml" in xml                                   # the entity's own icon
    assert notation.JUNCTION_STYLES["Or"] in xml and f'ea_junction="{E3}" ea_junction_kind="or"' in xml


def test_a_hidden_relationship_is_not_drawn():
    rels = [{"id": R1, "type": "Flow", "source": E1, "target": E2}]
    xml = dv.build_xml(_ents()[:2], rels, hidden=[{"rel": "Flow", "id": R1, "source": E1, "target": E2}])
    assert dv.parse(xml)["relationships"] == []


def test_layout_bands_by_domain():
    ents = [{"id": f"m{i}", "domain": "Motivation"} for i in range(2)] + [{"id": f"a{i}", "domain": "Application"} for i in range(8)]
    pos = dv.layout(ents)
    assert max(pos[f"m{i}"][1] for i in range(2)) < min(pos[f"a{i}"][1] for i in range(8))   # motivation above application
    assert len({pos[f"a{i}"] for i in range(8)}) == 8                                     # nothing on top of anything
    assert pos["a6"][1] > pos["a0"][1]                                                    # a new row after PER_ROW


def test_compressed_diagrams_are_read():
    import base64
    import urllib.parse
    import zlib
    inner = dv.build_xml(_ents()[:1], [])
    model = inner[inner.index("<mxGraphModel"):inner.index("</mxGraphModel>") + len("</mxGraphModel>")]
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    packed = base64.b64encode(c.compress(urllib.parse.quote(model).encode()) + c.flush()).decode()
    xml = f'<mxfile><diagram id="d" name="Page">{packed}</diagram></mxfile>'
    assert dv.parse(xml)["entities"] == [E1]


def test_bad_files_are_refused():
    for bad in ("not xml", '<!DOCTYPE x [<!ENTITY a "b">]><mxfile/>'):
        with pytest.raises(EditError):
            dv.parse(bad)


def test_icons_are_checked():
    good = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 2"><circle cx="1" cy="1" r="1" fill="#C62828"/></svg>'
    assert dv.check_icon(good, "x.svg") == "image/svg+xml"
    assert dv.check_icon(b"\x89PNG\r\n\x1a\n" + b"0" * 20, "x.png") == "image/png"
    for bad in (b'<svg xmlns="http://www.w3.org/2000/svg"><script>1</script></svg>',
                b'<svg xmlns="http://www.w3.org/2000/svg" onload="x()"/>',
                b'<svg xmlns="http://www.w3.org/2000/svg"><a href="http://example.org"><rect/></a></svg>',
                b'<svg xmlns="http://www.w3.org/2000/svg"><rect style="fill:url(http://example.org/x)"/></svg>',
                b'<svg xmlns="http://www.w3.org/2000/svg"><foreignObject/></svg>',
                b'<svg xmlns="http://www.w3.org/2000/svg"><image href="data:image/png;base64,AAAA"/></svg>',
                b'<!DOCTYPE svg [<!ENTITY x "y">]><svg xmlns="http://www.w3.org/2000/svg">&x;</svg>',
                b"GIF89a", b""):
        with pytest.raises(EditError):
            dv.check_icon(bad, "x.svg")
    with pytest.raises(EditError) as e:
        dv.check_icon(b"\x89PNG\r\n\x1a\n" + b"0" * 70000, "x.png")
    assert e.value.status == 413
    assert dv._blob("\\x414243") == b"ABC" and dv._blob(memoryview(b"AB")) == b"AB"


def test_heat_map_bands():
    assert dv.bands(0, 10) == [(0, 2), (2, 4), (4, 6), (6, 8), (8, 10)]
    assert dv.bands(5, 5) == [(5, 5)]
    assert dv.bands(1, 5)[2] == (2.6, 3.4)                                     # no float noise
    assert dv._num(100000) == "100,000" and dv._num(2.6) == "2.6"


def test_junction_kind():
    assert junctions.kind_of({"JunctionKind": "Or"}) == "Or"
    assert junctions.kind_of({"Junction Kind": "or"}) == "Or"
    assert junctions.kind_of({}) == "And" and junctions.kind_of(None) == "And"


def test_junction_reaches_every_type_in_the_seed():
    """The metamodel lets every relationship type (but Specialization) reach a junction and leave it (D397): the real
    rules are in eax.junctions (D248)."""
    from eax.seed import archimate4 as A
    from eax.seed import build
    allowed = {(s, r, t) for s, r, t, _ in build.expand_allowed()}
    rels = {r for r, *_ in A.REL_TYPES} - {"Specialization"}
    for r in rels:
        assert ("ApplicationComponent", r, "Junction") in allowed, r
        assert ("Junction", r, "Capability") in allowed, r
    assert ("ApplicationComponent", "Specialization", "Junction") not in allowed
    assert "JunctionKind" in {a for a, *_ in A.MAP["Junction"]}


def test_migration_is_rows_only():
    sql = (ROOT / "migrations" / "sql" / "0033_drawn_views.sql").read_text()
    assert "'0.16.0'" in sql and "0033_drawn_views" in sql
    for word in ("CREATE TRIGGER", "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", "LANGUAGE plpgsql"):
        assert word not in sql.upper().replace("DO $$", ""), word                # D248: no logic in the database
    assert "REFERENCES core." not in sql.split("CREATE TABLE proj.view_evidence")[1]   # D266: nothing crosses from proj
    for t in ("core.entity_icons", "proj.view_evidence"):
        assert f"CREATE TABLE {t}" in sql
    for t in ("core.drawn_views", "core.drawn_view_versions"):              # the views service's own database (D405)
        assert f"CREATE TABLE {t}" not in sql
    ev = sql.split("CREATE TABLE proj.view_evidence")[1].split("\n);")[0]
    assert "document_id" not in ev and "version_no" in ev                     # a link only (D408)
    assert 'version = "0.1' in (ROOT / "version.toml").read_text()
    py = (ROOT / "migrations" / "versions" / "0033_drawn_views.py").read_text()
    assert 'down_revision = "0032_repository_tags"' in py


def test_routes_and_tools():
    api = (ROOT / "eax" / "api" / "drawn_views.py").read_text()
    for path in ("/drawn-views/access", "/drawn-views/check",
                 "/tags/<string:tag>/drawn-views/<string:view>", "/drawn-views/resync", "/drawn-views/setup", "/drawn-views/relationships-of",
                 "/drawn-views/allowed", "/drawn-views/generate", "/heat-map", "/entities/<string:entity>/icon",
                 "/projects/<string:project>/view-evidence\"", "/view-evidence/<string:evidence>"):
        assert path in api, path
    assert api.count('@require_auth("model.content")') == 4                   # icon set and remove (the views service saves, D405);
    assert "/drawn-views/change" in api and "/drawn-views/commit" in api      # a change made on the view, the person's commits (D413)
    for gone in ("/drawn-views/<string:view>/versions", "SaveConflict", "f.filename if f"):
        assert gone not in api, gone
    assert "views/render" in (ROOT / "eax" / "api" / "views.py").read_text()
    assert "drawn_views" in (ROOT / "eax" / "app.py").read_text()
    mcp = (ROOT / "eax" / "mcp_build.py").read_text()
    for t in ("async def list_drawn_views", "async def get_drawn_view", "async def create_drawn_view"):
        assert t in mcp
    assert "may_draw" in mcp and "vc.list_views" in mcp and "vc.get_view" in mcp
    later = (ROOT / "eax" / "seed" / "later.py").read_text()
    assert "sample_drawn_views" in later


def test_seed_views_use_names_in_the_demo_estate():
    from eax.seed import demo_estate as D
    from eax.seed import sample_drawn_views as S
    names = {n for _t, n, *_ in D.E}
    for n in set(S.LANDSCAPE + S.CHANNELS + S.EARLIER + S.SKETCH):
        assert n in names, n
    assert any(t == "Junction" for t, *_ in D.E)
    assert dv.check_icon(S.PHONE_SVG, "phone.svg") == "image/svg+xml"


def test_the_views_service_is_reached_for_tags_copies_merges_packages_and_deletes():
    src = {n: (ROOT / "eax" / f"{n}.py").read_text() for n in ("tags", "model_ops", "merge", "drawn_views")}
    assert "vc.hold_for_tag" in src["tags"] and "vc.tag_view" in src["tags"]
    assert "dv.snapshot" not in src["tags"]
    for x in ("vc.export_model", "vc.import_model", "vc.delete_model", "views/drawn_views.json"):
        assert x in src["model_ops"], x
    assert "copy_views" in src["merge"] and "vc.copy_model" in src["drawn_views"]


def test_views_client_falls_back_when_the_service_is_off(monkeypatch):
    from eax import views_client as vc
    monkeypatch.setenv("EAX_SERVICE_VIEWS", "off")
    assert not vc.service_on()
    try:
        vc.list_views("x")
        raise AssertionError("expected ViewsDown")
    except vc.ViewsDown as exc:
        assert "switched off" in str(exc)
    monkeypatch.setenv("EAX_SERVICE_VIEWS", "on")
    monkeypatch.setenv("EAX_DEPLOYMENT", "server")
    monkeypatch.delenv("EAX_VIEWS_KEY", raising=False)
    assert vc._key() == ""                       # no laptop key on a server


def test_a_relationship_name_is_the_line_label():
    """D412: a named relationship shows its name on the line; no name, no label in the file (the canvas shows the type, D460)."""
    rels = [{"id": R1, "type": "Flow", "source": E1, "target": E2, "name": "sends claims"},
            {"id": "55555555-5555-4555-8555-555555555555", "type": "Serving", "source": E2, "target": E1}]
    xml = dv.build_xml(_ents()[:2], rels)
    assert 'label="sends claims"' in xml and f'ea_rel_id="{R1}"' in xml
    assert 'label="" ea_rel="Serving"' in xml
    assert "coalesce(r.name, '') AS name" in (ROOT / "eax" / "drawn_views.py").read_text()


def test_view_pending_is_only_the_persons_changes_on_the_view(monkeypatch):
    """D412: the view's Commit button sees the person's pending changes whose target is on the view, nothing else."""
    from types import SimpleNamespace

    from eax import commits as cm
    rows = [{"id": "c1", "label": "Add Flow", "target": R1, "target_kind": "relationship", "op": "add"},
            {"id": "c2", "label": "Elsewhere", "target": "77777777-7777-4777-8777-777777777777", "target_kind": "relationship", "op": "add"}]
    monkeypatch.setattr(dv.repo, "get_model", lambda c, m: {"_id": 1})
    monkeypatch.setattr(dv, "_rows", lambda conn, sql, **kw: rows if kw.get("a") == "anna" else [])
    monkeypatch.setattr(cm, "_model", lambda c, m: {"_id": 1})
    monkeypatch.setattr(cm, "uses_commits", lambda m: True)
    monkeypatch.setattr(cm, "may_commit", lambda c, u, m: False)
    out = dv.view_pending(None, "m", SimpleNamespace(username="Anna"), [R1, E1])
    assert out["count"] == 1 and out["changes"][0]["id"] == "c1" and out["may_commit"] is False
    assert dv.view_pending(None, "m", SimpleNamespace(username="Anna"), [])["count"] == 0
    assert "/drawn-views/pending" in (ROOT / "eax" / "api" / "drawn_views.py").read_text()


def test_the_stencil_is_in_archimate_order():
    """D412: domains as the owner's ArchiMate 4 guide lists them (and TOGAF's), others after alphabetically; relationships
    in their sort order (ArchiMate's), extensions marked."""
    doms = ["Implementation & Migration", "Business", "Zeta", "Common", "Motivation", "Alpha", "Strategy", "Technology", "Application"]
    assert sorted(doms, key=dv.stencil_domain_key) == ["Motivation", "Strategy", "Common", "Business", "Application", "Technology",
                                                       "Implementation & Migration", "Alpha", "Zeta"]
    togaf = ["Governance", "Data", "Business", "Implementation and Migration", "Motivation", "Strategy", "Application", "Technology"]
    assert sorted(togaf, key=dv.stencil_domain_key) == ["Motivation", "Strategy", "Business", "Data", "Application", "Technology",
                                                        "Implementation and Migration", "Governance"]
    src = (ROOT / "eax" / "drawn_views.py").read_text()
    assert "ORDER BY sort_order, name" in src and '"extension"' in src and '"domains": domains' in src


def _two_way(monkeypatch, committer=False, commits=True, junction=False):
    """D413: change_now with the commits module stubbed: what it records, commits and refuses."""
    from types import SimpleNamespace

    from eax import commits as cm
    seen = {"record": [], "commit": [], "apply": []}
    monkeypatch.setattr(cm, "_model", lambda c, m: {"_id": 1, "id": "m"})
    monkeypatch.setattr(cm, "uses_commits", lambda m: commits)
    monkeypatch.setattr(cm, "may_commit", lambda c, u, m: committer)
    monkeypatch.setattr(dv.repo, "_find_type", lambda c, m, t: {"is_connector": junction and str(t).lower() == "junction"})
    monkeypatch.setattr(cm, "record", lambda c, m, a, op, args, answer="result": seen["record"].append((op, args, answer))
                        or {"id": R1, "pending": True, "change": "ch-1", "change_label": "Relate", "note": "x"})
    monkeypatch.setattr(cm, "commit", lambda c, m, u, **kw: seen["commit"].append(kw) or {"commit": "k-1", "number": 7, "committed": 1, "skipped": 0})
    monkeypatch.setattr(cm, "_resolve_refs", lambda c, m, op, args: args)
    monkeypatch.setattr(cm, "_apply", lambda c, m, op, args, actor: seen["apply"].append((op, args)) or {"id": R1})
    return seen, SimpleNamespace(username="Anna")


def test_a_relationship_drawn_is_committed_at_once(monkeypatch):
    """D413: anyone who may change the model; recorded then committed as the person, with the view's message; never outside."""
    seen, anna = _two_way(monkeypatch)
    out = dv.change_now(None, "m", anna, "relationship.create",
                        {"data": {"source": E1, "target": E2, "relationship_type": "Flow", "allow_outside": True}}, "Claims sketch")
    assert out["committed"] is True and out["pending"] is False and out["number"] == 7 and "note" not in out
    op, args, _ = seen["record"][0]
    assert op == "relationship.create" and args["data"]["allow_outside"] is False
    assert seen["commit"][0] == {"change_ids": ["ch-1"], "message": "Drawn on view Claims sketch", "relationships_only": True}
    dv.change_now(None, "m", anna, "relationship.delete", {"relationship": R1}, "Claims sketch")
    assert seen["commit"][1]["message"] == "Deleted on drawn view Claims sketch"
    dv.change_now(None, "m", anna, "relationship.create", {"data": {}}, "V", message="  My own words ")
    assert seen["commit"][2]["message"] == "My own words"


def test_entities_from_the_drawing_are_for_committers_only(monkeypatch):
    seen, anna = _two_way(monkeypatch, committer=False)
    for op in ("entity.update", "entity.create"):
        with pytest.raises(EditError) as e:
            dv.change_now(None, "m", anna, op, {"entity": E1, "data": {"name": "x", "entity_type": "Process"}}, "V")
        assert e.value.status == 403
    assert not seen["record"]
    with pytest.raises(EditError):
        dv.change_now(None, "m", anna, "entity.delete", {"entity": E1}, "V")          # never from a drawn view
    seen, anna = _two_way(monkeypatch, committer=True)
    dv.change_now(None, "m", anna, "entity.update", {"entity": E1, "data": {"name": "New"}}, "Claims sketch")
    assert seen["record"][0][2] == "entity" and seen["commit"][0]["message"] == "Changed on drawn view Claims sketch"


def test_a_junction_needs_no_committer(monkeypatch):
    seen, anna = _two_way(monkeypatch, committer=False, junction=True)
    dv.change_now(None, "m", anna, "entity.create", {"data": {"entity_type": "Junction", "name": "Or junction"}}, "V")
    assert seen["commit"][0]["message"] == "Created on drawn view V"


def test_a_library_model_being_built_saves_straight_away(monkeypatch):
    seen, anna = _two_way(monkeypatch, commits=False)
    out = dv.change_now(None, "m", anna, "relationship.create", {"data": {"source": E1, "target": E2, "relationship_type": "Flow"}}, "V")
    assert seen["apply"] and not seen["record"] and out["committed"] is True and out["commit"] is None


def test_commit_lets_a_drawn_view_commit_relationships_without_a_committer():
    """D413: commits.commit(relationships_only=True) skips the committer check only when every change is a relationship or a
    junction; drawn_free says which."""
    src = (ROOT / "eax" / "commits.py").read_text()
    assert "relationships_only: bool = False" in src and "def drawn_free(" in src and "is_connector" in src
    from eax import commits as cm
    assert cm.drawn_free(None, {}, "relationship.create", {}) and cm.drawn_free(None, {}, "relationship.delete", {})
    assert not cm.drawn_free(None, {}, "entity.update", {}) and not cm.drawn_free(None, {}, "entity.delete", {})
