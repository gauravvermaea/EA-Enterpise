"""The ArchiMate 4 seed builder (no database needed)."""

from eax.seed import archimate4 as A
from eax.seed import build


def test_counts():
    assert len(A.ENTITY_TYPES) == 42
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


def test_every_sample_attribute_applies_to_its_type():
    for type_code, name, _desc, attrs in A.SAMPLE_ENTITIES:
        mapped = {a for a, *_ in A.MAP[type_code]}
        assert set(attrs) <= mapped, (name, set(attrs) - mapped)


def test_seed_sql_shape():
    sql = build.seed_sql(with_template=True, with_sample=True)
    assert sql.count("INSERT INTO core.models") == 4  # Root, ArchiMate 4, insurance reference model, sample
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
