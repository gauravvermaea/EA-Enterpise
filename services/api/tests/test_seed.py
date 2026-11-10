"""The ArchiMate 4 seed builder (no database needed)."""

from pathlib import Path

from eax.seed import archimate4 as A
from eax.seed import build


def test_counts():
    assert len(A.SPEC_TYPES) == 42                     # the ArchiMate 4 Specification's elements
    assert len(A.ENTITY_TYPES) == 42 + len(A.EXTENSIONS) + len(A.CONNECTORS)   # extensions (D345), the junction (D397)
    assert all(A.EXTENSION_DESCRIPTIONS[c].startswith("EA Explorer extension") for c, *_ in A.EXTENSIONS)
    assert len(A.REL_TYPES) == 11


def test_guids_are_stable():
    assert build.gid("model", "x") == build.gid("model", "x")
    assert build.TEMPLATE_ID != build.SAMPLE_ID


def test_table_and_column_names_are_unique_and_valid():
    tables = [build.snake(c) for c, *_ in A.ENTITY_TYPES]
    columns = [build.snake(c) for c, *_ in A.ATTRS]
    assert len(set(tables)) == len(tables)
    assert len(set(columns)) == len(columns)
    assert build.snake("ApplicationComponent") == "application_component"
    assert build.snake("GoLiveDate") == "go_live_date"


def test_every_sample_relationship_is_allowed():
    allowed = {(s, r, t) for s, r, t, _ in build.expand_allowed()}
    types = {name: code for code, name, *_ in A.SAMPLE_ENTITIES}
    for src, rel, tgt in A.SAMPLE_RELS:
        assert (types[src], rel, types[tgt]) in allowed, (src, rel, tgt)
    from eax.seed import demo_estate as D
    types = {name: code for code, name, *_ in D.E}
    for src, rel, tgt in D.R:
        assert (types[src], rel, types[tgt]) in allowed, (src, rel, tgt)


def test_laptop_rules_demo_and_history_keep_to_the_rules():
    """Karoo Re's rules demo and the sample model's history steps (loaded after the start) only add allowed relationships."""
    allowed = {(s, r, t) for s, r, t, _ in build.expand_allowed()}
    types = {name: code for code, name, *_ in A.SAMPLE_ENTITIES}
    for _key, t, name, *_rest in build.RULE_DEMO_ENTITIES:
        types.setdefault(name, t)
    for _key, t, name, _desc, _attrs, links in build.RULE_DEMO_ENTITIES:
        for rel, other, out in links:
            assert ((t, rel, types[other]) if out else (types[other], rel, t)) in allowed, (name, rel, other)
    for _actor, _label, steps in build.HISTORY_DEMO:
        for st in steps:
            if st[0] in ("add", "remove"):
                assert (types[st[1]], st[2], types[st[3]]) in allowed, st


def test_archimate4_rules_follow_the_guide():
    """The owner's ArchiMate 4 guide (D393): a few rules it is explicit about, either way."""
    allowed = {(s, r, t) for s, r, t, _ in build.expand_allowed()}
    for rule in [("Facility", "Assignment", "BusinessActor"), ("Material", "Realization", "BusinessObject"),
                 ("DataObject", "Realization", "BusinessObject"), ("DistributionNetwork", "Aggregation", "BusinessActor"),
                 ("BusinessActor", "Assignment", "Stakeholder"), ("Process", "Aggregation", "Function"),
                 ("Function", "Composition", "Process"), ("Artifact", "Realization", "Device"),
                 ("Deliverable", "Realization", "Requirement"), ("Plateau", "Aggregation", "Goal"),
                 ("Resource", "Assignment", "ValueStream"), ("Capability", "Realization", "Outcome")]:
        assert rule in allowed, rule
    for rule in [("ApplicationComponent", "Realization", "Capability"), ("Artifact", "Realization", "BusinessObject"),
                 ("Role", "Serving", "ApplicationComponent"), ("BusinessActor", "Assignment", "ApplicationComponent"),
                 ("Capability", "Realization", "Goal"), ("ValueStream", "Serving", "Capability"),
                 ("Process", "Realization", "Resource")]:
        assert rule not in allowed, rule
    aggregation = {(s, t) for s, r, t in allowed if r == "Aggregation"}
    assert aggregation == {(s, t) for s, r, t in allowed if r == "Composition"}


def test_every_sample_attribute_applies_to_its_type():
    for type_code, name, _desc, attrs in A.SAMPLE_ENTITIES:
        mapped = {a for a, *_ in A.MAP[type_code]}
        assert set(attrs) <= mapped, (name, set(attrs) - mapped)


def test_seed_sql_shape():
    sql = build.seed_sql(with_template=True, with_sample=True)
    assert sql.count("INSERT INTO core.models") == 6  # Root, ArchiMate 4, root-principle-model, TOGAF 10, insurance reference model, sample
    assert "INSERT INTO core.allowed_relationships" in sql
    assert "origin_guid" in sql
    assert "'sample-insurance'" not in sql  # keys are guids, never raw names


def test_insurance_reference_model_is_consistent():
    """Every relationship is allowed by ArchiMate 4, every parent exists, nothing names Meridian."""
    from eax.seed import insurance as I
    allowed = {(s, r, t) for s, r, t, _ in build.expand_allowed()}
    types = {key: type_code for key, type_code, *_ in I.ENTITIES}
    assert len(types) == len(I.ENTITIES), "keys are unique"
    for src, rel, tgt, _name in I.RELATIONSHIPS:
        assert (types[src], rel, types[tgt]) in allowed, (src, rel, tgt)
    for key, _t, name, desc, parent, attrs in I.ENTITIES:
        assert parent is None or parent in types, key
        assert "meridian" not in f"{name} {desc}".lower(), key
        mapped = {a for a, *_ in A.MAP[_t]}
        assert set(attrs) <= mapped, (key, set(attrs) - mapped)


def test_history_demo_has_four_steps_by_different_people():
    """D110: the laptop history demo saves four versions, each step its own actor and label."""
    from eax.seed.build import history_demo_steps
    steps = history_demo_steps()
    assert len(steps) == 4
    assert [a for a, _ in steps] == ["user_architect", "user_model_sub_admin", "user_architect", "user_model_admin"]
    for actor, sql in steps:
        assert f"set_config('eax.actor', '{actor}', true)" in sql
        assert "Laptop history demo" in sql
    assert "is_deleted = true" in steps[2][1]   # a relationship removed


def test_root_principle_model():
    """D270, D271: a model of principles only, created from ArchiMate 4; names and categories, the text filled in later."""
    sql = build.principles_sql()
    assert "'root-principle-model'" in sql and "'Principles 1.0'" in sql and "'reference'" in sql
    names = [n for _c, ns in build.PRINCIPLES for n in ns]
    assert len(names) == 20 and len(set(names)) == 20
    assert sql.count("INSERT INTO core.entity_types") == 1 and "'Principle'" in sql
    for attr in ("PrincipleStatement", "PrincipleRationale", "PrincipleImplications", "PrincipleCategory", "PrincipleSource"):
        assert attr in sql
    assert build.seed_sql(with_template=False, with_insurance=False, with_sample=True, with_principles=False).count("root-principle-model") == 0
    # the sample model's step at start-up loads only the sample model: not the TOGAF 10 metamodel again (duplicate guid)
    src = (Path(build.__file__).parent / "later.py").read_text(encoding="utf-8")
    assert "with_sample=True, with_togaf10=False," in src
    only = build.seed_sql(with_template=False, with_insurance=False, with_sample=True, with_principles=False, with_togaf10=False)
    assert build.TOGAF10_ID not in only and build.SAMPLE_ID in only


def test_industry_reference_models_are_consistent():
    """Phase 39 (D470): every industry reference model keeps to the ArchiMate 4 rules, every parent and end exists,
    keys are unique, attributes apply to their types, and nothing says Meridian or objective."""
    import re

    from eax.seed import industries as IND
    allowed = {(s, r, t) for s, r, t, _ in build.expand_allowed()}
    assert [c for c, *_ in IND.MODELS] == ["healthcare", "manufacturing", "pharmaceuticals", "retail"]
    for code, name, _version, desc, mod in IND.MODELS:
        types = {key: type_code for key, type_code, *_ in mod.ENTITIES}
        assert len(types) == len(mod.ENTITIES), (code, "keys are unique")
        assert sum(1 for t in types.values() if t == "Capability") >= 50, code
        assert {"ValueStream", "ApplicationComponent", "BusinessObject"} <= set(types.values()), code
        for key, t, ename, edesc, parent, attrs in mod.ENTITIES:
            assert ename and (parent is None or parent in types), (code, key)
            mapped = {a for a, *_ in A.MAP[t]}
            assert set(attrs) <= mapped, (code, key, set(attrs) - mapped)
            assert not re.search(r"meridian|objective", f"{ename} {edesc}", re.I), (code, key)
        triples = [(s, r, t) for s, r, t, _n in mod.RELATIONSHIPS]
        assert len(triples) == len(set(triples)), (code, "one relationship per source, type and target")
        for src, rel, tgt, _n in mod.RELATIONSHIPS:
            assert (types[src], rel, types[tgt]) in allowed, (code, src, rel, tgt)
        assert not re.search(r"meridian|objective", f"{name} {desc}", re.I)


def test_industry_reference_models_load():
    """The industry models are loaded on request only (the seed loads the missing ones), each its own locked
    reference model with its own guid."""
    from eax.seed import industries as IND
    assert "Healthcare reference model" not in build.seed_sql()
    sql = build.seed_sql(with_template=False, with_insurance=False, with_sample=False, with_principles=False,
                         with_togaf10=False, with_industries={"retail"})
    assert sql.count("INSERT INTO core.models") == 1 and "'Retail reference model'" in sql and "'reference'" in sql
    sql = build.seed_sql(with_template=False, with_insurance=False, with_sample=False, with_principles=False,
                         with_togaf10=False, with_industries=True)
    assert sql.count("INSERT INTO core.models") == len(IND.MODELS)
    guids = {build.gid("model", IND.key(c)) for c, *_ in IND.MODELS}
    assert len(guids) == 4 and build.INSURANCE_ID not in guids
