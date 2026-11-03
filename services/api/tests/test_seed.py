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
    assert sql.count("INSERT INTO core.model") == 2
    assert "INSERT INTO core.allowed_relationship" in sql
    assert "origin_guid" in sql
    assert "'sample-insurance'" not in sql  # keys are guids, never raw names
