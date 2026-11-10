"""Phase 13.0.5 (D286): common analysis, what two or more models have in common."""

from pathlib import Path

import pytest

from eax import background as bg
from eax import commons as co
from eax.metamodel_edit import EditError

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT.parent / "web" / "src"


def _spec():
    return {"domains": [{"code": "S", "name": "Strategy"}], "pick_lists": [],
            "attributes": [{"code": "Owner", "name": "Owner"}],
            "entity_types": [{"code": "Capability", "name": "Capability", "domain": "S", "attributes": [{"attribute": "Owner"}]},
                             {"code": "Application", "name": "Application", "domain": "S", "attributes": []}],
            "relationship_types": [{"code": "serving", "name": "Serving"}], "allowed": []}


def _side(n, ents, rels=()):
    e = {}
    for g, code, name, did, owner in ents:
        e[g] = {"guid": g, "type_code": code, "entity_type": code, "name": name, "display_id": did, "origin": None, "values": {"Owner": owner},
                "description": "", "parent": None, "status": "published", "tags": [], "domain": "Strategy"}
    r = {f"r{n}{k}": {"guid": f"r{n}{k}", "type_code": "serving", "relationship_type": "Serving", "source": s, "target": t,
                      "source_name": e[s]["name"], "target_name": e[t]["name"], "name": ""} for k, (s, t) in enumerate(rels)}
    return {"kind": "model", "model_id": f"m{n}", "model": f"M{n}", "label": f"M{n} (now)", "spec": _spec(), "snapshot": {"entities": e, "relationships": r}}


def _three():
    a = _side(0, [("a1", "Capability", "Claims Handling", "CAP-1", "COO"), ("a2", "Capability", "Fraud Detection", "CAP-2", "CRO"),
                  ("a3", "Application", "Claims Engine", "APP-1", None)], [("a3", "a1")])
    b = _side(1, [("b1", "Capability", "claims handling", "CAP-9", "COO"), ("b2", "Capability", "Fraud Detection", "CAP-1", "CFO"),
                  ("b3", "Application", "Claims Engine", "APP-7", None)], [("b3", "b1")])
    c = _side(2, [("c1", "Capability", "Claims  Handling!", "CAP-1", "Ops"), ("c2", "Capability", "Broker Portal", "CAP-2", None),
                  ("c3", "Capability", "Fraud Detections", "CAP-3", None)])
    return [a, b, c]


def _st(**k):
    st = {"threshold": 3, "values": True, "relationships": True, "by_display_id": False,
          "types": {"Capability": ["name", "value:Owner"], "Application": ["name"]}, "relationship_types": ["serving"], "matches": [], "rejected": []}
    st.update(k)
    return st


def test_threshold_matching_values_relationships():
    r = co.analyse(_three(), _st())
    by = {i["name"]: i for i in r["items"]}
    assert by["Claims Handling"]["count"] == 3 and by["Claims Handling"]["common"]      # case, spaces and punctuation ignored
    assert by["Fraud Detection"]["count"] == 2 and not by["Fraud Detection"]["common"]
    assert by["Broker Portal"]["count"] == 1
    owner = next(d for d in by["Claims Handling"]["differs"] if d["field"] == "value:Owner")
    assert owner["values"] == {"0": "COO", "1": "COO", "2": "Ops"}
    rel = r["relationships"][0]
    assert rel["sides"] == [0, 1] and rel["count"] == 2 and not rel["common"]
    assert r["totals"]["in_all"] == 1 and r["totals"]["sides"] == 3
    r2 = co.analyse(_three(), _st(threshold=2))
    assert {i["name"] for i in r2["items"] if i["common"]} == {"Claims Handling", "Fraud Detection", "Claims Engine"}
    assert r2["relationships"][0]["common"]


def test_display_id_only_when_asked_and_suggestions():
    # with display IDs, CAP-1 in M1 (Fraud Detection) would wrongly match Claims Handling of M0
    r = co.analyse(_three(), _st(by_display_id=True))
    assert any(i["count"] >= 2 and i["members"].get("1", {}).get("name") == "Fraud Detection" and i["name"] == "Claims Handling" for i in r["items"])
    r = co.analyse(_three(), _st())
    s = [(x["a_name"], x["b_name"]) for x in r["suggestions"]]
    assert ("Fraud Detection", "Fraud Detections") in s
    sug = next(x for x in r["suggestions"] if x["b_name"] == "Fraud Detections")
    r = co.analyse(_three(), _st(matches=[[sug["a"], sug["b"]]]))
    assert next(i for i in r["items"] if i["name"] == "Fraud Detection")["count"] == 3
    r = co.analyse(_three(), _st(rejected=[[sug["a"], sug["b"]]]))
    assert ("Fraud Detection", "Fraud Detections") not in [(x["a_name"], x["b_name"]) for x in r["suggestions"]]


def test_settings_are_checked():
    info = {"types": [{"code": "Capability", "default": True, "fields": [{"code": "name", "default": True}]}], "relationship_types": []}
    assert co.clean_settings({"threshold": 9}, info, 3)["threshold"] == 3
    assert co.clean_settings({"threshold": 1}, info, 3)["threshold"] == 2
    with pytest.raises(EditError):
        co.clean_settings({"types": {}}, {"types": [], "relationship_types": []}, 3)


def test_migration_routes_and_screens():
    sql = (ROOT / "migrations" / "sql" / "0027_common_analysis.sql").read_text()
    for t in ("core.common_analyses", "core.common_items", "core.common_runs", "'0.14.5'", "common_analyses_name_idx"):
        assert t in sql
    api = (ROOT / "eax" / "api" / "commons.py").read_text()
    for r in ('"/commons/preview"', '"/commons"', '"/commons/<string:analysis_id>/suggestions"', '"/commons/<string:analysis_id>/tag"',
              '"/commons/<string:analysis_id>/make-model"', '"/commons/<string:analysis_id>/download"'):
        assert r in api
    assert "commons_blp" in (ROOT / "eax" / "app.py").read_text()
    for k in ("common.create", "common.refresh", "common.suggestions", "common.tag", "common.make_model", "common.download"):
        assert k in bg.WORK and k in bg.KINDS
    js = (WEB / "Commons.jsx").read_text()
    for s in ("function NewCommon", "function Setup", "function CommonPage", "function Suggestions", "function MakeModelDialog", "match by display ID"):
        assert s in js
    assert "Common analyses" in (WEB / "Versions.jsx").read_text()
