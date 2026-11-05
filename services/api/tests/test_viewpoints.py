"""Phase 8.2: viewpoints as data, the demo estate and the report catalogue (no database needed)."""

import pathlib
import re

from eax.report_defs import AUDIENCES, REPORTS, VIEWPOINTS
from eax.seed import archimate4 as A
from eax.seed import demo_estate as D
from eax.seed.build import expand_allowed
from eax.seed.catalog import catalog_sql

WEB = pathlib.Path(__file__).resolve().parents[2] / "web" / "src"


def test_viewpoints_use_archimate4_types():
    types = {t[0] for t in A.ENTITY_TYPES}
    rels = {r[0] for r in A.REL_TYPES}
    attrs = {a[0] for a in A.ATTRS}
    on_demand = {"Gap", "GapStatus"}   # VP-26 (D185): the Gap type and its attributes come with a model's first Gap entities
    for v in VIEWPOINTS:
        assert set(v["element_types"]) - on_demand <= types, (v["code"], set(v["element_types"]) - types)
        assert set(v["relationship_types"]) <= rels, v["code"]
        assert v["heat_attribute"] in attrs | on_demand, v["code"]
        assert v["concerns"] and v["stakeholders"] and v["purpose"], v["code"]
    assert [v["code"] for v in VIEWPOINTS] == [f"VP-{i:02d}" for i in range(1, 27)]
    cats = {v["category"].split(":")[0] for v in VIEWPOINTS}
    assert cats == {"Basic", "Motivation", "Strategy", "Implementation and migration"}


def test_demo_estate_keeps_to_the_metamodel():
    typ = {n: t for t, n, *_ in D.E}
    allowed = {(s, r, t) for s, r, t, _ in expand_allowed()}
    bad = [(a, k, b) for a, k, b in D.R if (typ[a], k, typ[b]) not in allowed]
    assert not bad, bad
    for t, n, _d, _p, attrs in D.E:
        assert set(attrs) <= {a for a, _m, _s in A.MAP[t]}, (n, set(attrs))
        if "Version" in attrs:
            assert re.match(r"^\d+(\.\d+){0,3}$", attrs["Version"]), n
    # every viewpoint has something to show in the demo estate
    present = {t for t, *_ in D.E}
    assert all(present & set(v["element_types"]) - {"Grouping"} for v in VIEWPOINTS)


def test_catalog_sql_loads_every_viewpoint_and_audience():
    sql = catalog_sql()
    assert sql.count("INSERT INTO core.viewpoints") == 26
    assert all(f"'{c}'" in sql for c, _n, _g in AUDIENCES)
    links = sql[sql.index("INSERT INTO core.report_audience_links"):]
    assert all(f"('{r['code']}'," in links for r in REPORTS)


def test_viewpoints_are_routed_in_the_web_app():
    meta = (WEB / "Metamodel.jsx").read_text(encoding="utf-8")
    assert '["viewpoints", "Viewpoints", null]' in meta and "<ViewpointsTab" in meta
    views = (WEB / "ModelViews.jsx").read_text(encoding="utf-8")
    assert '["valuestreams", "Value stream map"' in views and '["roadmap", "Roadmap"' in views
