"""The views service's draw.io handling (D405): reading a view's file and binding a copy to another model's entities."""

import pytest

from viewsvc import drawio

A, B, J = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222", "33333333-3333-3333-3333-333333333333"
R = "44444444-4444-4444-4444-444444444444"
A2, R2 = "aaaaaaaa-1111-1111-1111-111111111111", "bbbbbbbb-4444-4444-4444-444444444444"


def _xml(hidden: str = "") -> str:
    h = f' ea_hidden="{hidden}"' if hidden else ""
    return f"""<mxfile><diagram id="d" name="V"><mxGraphModel><root>
<object id="0"{h}><mxCell/></object><mxCell id="1" parent="0"/>
<object id="a" label="Claims" ea_id="{A}" ea_type="ApplicationComponent"><mxCell vertex="1" parent="1"/></object>
<object id="b" label="Portal" ea_id="{B}" ea_type="ApplicationComponent"><mxCell vertex="1" parent="1"/></object>
<object id="p" label="Rules engine" ea_type="ApplicationComponent" ea_placeholder="1"><mxCell vertex="1" parent="1"/></object>
<object id="j" ea_junction="{J}" ea_junction_kind="Or"><mxCell vertex="1" parent="1"/></object>
<object id="e" ea_rel="Serving" ea_rel_id="{R}"><mxCell edge="1" parent="1" source="a" target="b"/></object>
<object id="u" ea_rel="Flow" ea_uncommitted="1"><mxCell edge="1" parent="1" source="b" target="p"/></object>
</root></mxGraphModel></diagram></mxfile>"""


def test_parse_reads_objects_lines_and_placeholders():
    p = drawio.parse(_xml())
    assert p["entities"] == sorted([A, B, J])
    assert p["placeholders"] == 1
    assert {o["junction"] for o in p["objects"] if o["type"] == "Junction"} == {"or"}
    serving = next(r for r in p["relationships"] if r["type"] == "Serving")
    assert (serving["source"], serving["target"], serving["id"]) == (A, B, R)
    s = drawio.summary(p)
    assert s["uncommitted_relationships"] == 1 and s["objects"] == 4 and s["relationships"] == 2


def test_bad_files_are_refused():
    for bad in ("", "<html/>", "<mxfile", '<!DOCTYPE x [<!ENTITY e "x">]><mxfile>&e;</mxfile>'):
        with pytest.raises(drawio.Refused):
            drawio.parse(bad)
    with pytest.raises(drawio.Refused) as exc:
        drawio.parse("<mxfile>" + " " * (drawio.MAX_XML + 1) + "</mxfile>")
    assert exc.value.status == 413
    assert drawio.parse(drawio.BLANK)["objects"] == []


def test_rebind_maps_what_the_other_model_has_and_makes_placeholders_of_the_rest():
    hidden = f'[{{&quot;rel&quot;:&quot;Serving&quot;,&quot;id&quot;:&quot;{R}&quot;,&quot;source&quot;:&quot;{A}&quot;}}]'
    out = drawio.rebind(_xml(hidden), {A: A2}, {R: R2})
    p = drawio.parse(out)
    assert A2 in p["entities"] and A not in p["entities"]
    assert B not in out and p["placeholders"] == 2                # the portal is not in the other model
    assert J not in out                                           # nor the junction: left unbound
    assert next(r for r in p["relationships"] if r["type"] == "Serving")["id"] == R2
    assert p["hidden"][0]["id"] == R2 and p["hidden"][0]["source"] == A2


def test_rebind_drops_relationship_ids_the_other_model_lacks():
    out = drawio.rebind(_xml(), {A: A2, B: B}, {})
    assert R not in out
    assert drawio.is_guid(A) and not drawio.is_guid("VP-01")
