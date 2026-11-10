"""Phase 4: the parts of model_ops that need no database (D108, D115, D116, D120)."""

import io
import json
import zipfile

import pytest

from eax import model_ops as mo
from eax.metamodel_edit import EditError


def _spec(**over):
    s = mo.empty_spec("Check", "Check", "1.0")
    s["domains"] = [{"code": "biz", "name": "Business"}]
    s["attributes"] = [{"code": "Owner", "name": "Owner", "data_type": "text"}]
    s["entity_types"] = [
        {"code": "App", "name": "Application", "domain": "biz", "attributes": [{"attribute": "Owner"}]},
        {"code": "Cap", "name": "Capability", "domain": "biz", "attributes": []},
    ]
    s["relationship_types"] = [{"code": "Serves", "name": "Serving", "attributes": []}]
    s["allowed"] = [{"source": "App", "relationship": "Serves", "target": "Cap"},
                    {"source": "Cap", "relationship": "Serves", "target": "Cap"}]
    s["rules"] = [{"entity_type": "App", "attribute": "Owner", "rule_type": "mandatory"},
                  {"entity_type": "Cap", "field": "name", "rule_type": "mandatory"}]
    s.update(over)
    return s


def test_spec_diff_same_is_empty():
    assert mo.spec_diff(_spec(), _spec()) == []


def test_spec_diff_added_removed_changed():
    a = _spec()
    b = _spec()
    b["entity_types"] = [dict(b["entity_types"][0], name="App"), {"code": "Goal", "name": "Goal", "domain": "biz", "attributes": []}]
    changes = {(d["section"], d["code"], d["change"]) for d in mo.spec_diff(a, b)}
    assert ("entity_types", "Goal", "added") in changes
    assert ("entity_types", "Cap", "removed") in changes
    assert ("entity_types", "App", "changed") in changes


def test_removing_an_entity_type_takes_its_allowed_relationships_and_rules():
    s = _spec()
    mo._remove_references(s, "entity_types", "cap")
    assert s["allowed"] == []
    assert [r["entity_type"] for r in s["rules"]] == ["App"]


def test_removing_a_relationship_type_takes_its_allowed_relationships():
    s = _spec()
    mo._remove_references(s, "relationship_types", "serves")
    assert s["allowed"] == []
    assert len(s["rules"]) == 2


def test_removing_an_attribute_takes_it_off_types_and_rules():
    s = _spec()
    mo._remove_references(s, "attributes", "owner")
    assert s["entity_types"][0]["attributes"] == []
    assert [r["entity_type"] for r in s["rules"]] == ["Cap"]


def _zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    return buf.getvalue()


def test_read_package_zip():
    data = _zip({
        "manifest.json": json.dumps({"format": "eax-package/1", "model": {"name": "Check", "kind": "project"},
                                     "built_on": {"name": "ArchiMate 4", "version": ""}}),
        "metamodel.json": json.dumps(_spec()),
        "entities/App.csv": "key,display_id,name,description,parent,status,Owner\r\n1,APP-1,Claims,,,active,Thandi\r\n",
        "relationships.csv": "source,type,target\r\n1,Serves,2\r\n",
    })
    pkg = mo.read_package(data, "check.zip")
    assert pkg["format"] == "zip"
    assert pkg["manifest"]["model"]["name"] == "Check"
    assert pkg["entities"]["App"][0]["Owner"] == "Thandi"
    assert len(pkg["relationships"]) == 1


def test_read_package_refuses_other_files():
    with pytest.raises(EditError):
        mo.read_package(b"not a zip", "x.txt")
    with pytest.raises(EditError):
        mo.read_package(_zip({"readme.txt": "hello"}), "x.zip")


def test_every_response_is_declared_with_a_schema():
    """flask-smorest dumps responses with a Schema; a bare marshmallow field has no dump() and the call
    ends in a 500 (phase 4: the metamodel drafts list failed this way)."""
    import pathlib
    import re
    api = pathlib.Path(__file__).resolve().parent.parent / "eax" / "api"
    bad = [f"{p.name}: {m.group(0)}" for p in api.glob("*.py")
           for m in re.finditer(r"@blp\.response\(\s*\d+\s*,\s*fields\.", p.read_text())]
    assert bad == []


def test_stand_in_ids_are_stable_and_negative():
    a = mo._synthetic_id("3f1c2e6a-1111-4222-8333-944455556666")
    assert a < 0 and a == mo._synthetic_id("3f1c2e6a-1111-4222-8333-944455556666")
    assert a != mo._synthetic_id("another row")


def test_content_levels():
    assert mo.CONTENT_LEVELS == ("metamodel", "content", "history")
