"""Faster text comparisons (R3.7, D665): a hashed-name index for exact matches, trigram indexes for "contains"; indexes
only (D248). Checked on a 200,000-row copy on 13 Nov 2026: both kinds of query use the indexes (BitmapOr)."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SQL = (REPO / "services/api/migrations/sql/0070_text_keys.sql").read_text()


def _statements():
    return [s.strip() for s in re.sub(r"--[^\n]*", "", SQL).split(";") if s.strip()]


def test_indexes_only_no_logic():
    for s in _statements():
        assert s.startswith("CREATE INDEX IF NOT EXISTS"), s
    for word in ("TRIGGER", "FUNCTION", "GENERATED", "ALTER TABLE"):
        assert word not in SQL.upper().replace("-- ", "# "), word


def test_the_hash_key_and_the_trigram_indexes():
    s = " ".join(_statements())
    assert "entities_name_key_idx ON core.entities (model_id, (md5(lower(name))::uuid)) WHERE NOT is_deleted" in s
    assert "attribute_values_value_key_idx" in s and "(md5(value_text)::uuid)" in s
    for col in ("display_id", "description"):
        assert f"USING gin ({col} gin_trgm_ops)" in s
    assert "USING gin (old_name gin_trgm_ops)" in s and "USING gin (old_display_id gin_trgm_ops)" in s


def test_the_migration_drops_exactly_what_it_makes():
    from importlib import util
    spec = util.spec_from_file_location("m0070", REPO / "services/api/migrations/versions/0070_text_keys.py")
    src = spec.origin and Path(spec.origin).read_text()
    made = set(re.findall(r"EXISTS (\w+) ON", SQL))
    dropped = {n.split(".")[1] for n in re.findall(r'"(core\.\w+)"', src)}
    assert made == dropped and len(made) == 7
    assert 'down_revision = "0069_api_cases"' in src


def test_name_match_compares_the_key_then_the_name():
    from eax import repository as repo
    s = repo.name_match("e", "n")
    assert "md5(lower(e.name))::uuid = md5(lower(CAST(:n AS text)))::uuid" in s       # the index's own expression
    assert "lower(e.name) = lower(CAST(:n AS text))" in s                           # no false match on a shared hash


def test_lookups_by_name_use_it():
    repo_src = (REPO / "services/api/eax/repository.py").read_text()
    assert "f\"({name_match('e', 'e')} OR lower(e.display_id) = lower(:e))\"" in repo_src
    assert 'repo.name_match("e", "n")' in (REPO / "services/api/eax/scenarios.py").read_text()


def test_the_self_test_checks_the_indexes_are_there():
    from eax.testing import db_checks
    names = [n for n, _, _ in db_checks.CHECKS]
    assert "the text comparison indexes are there (R3.7)" in names
    q = dict((n, q) for n, q, _ in db_checks.CHECKS)["the text comparison indexes are there (R3.7)"]
    for idx in re.findall(r"EXISTS (\w+) ON", SQL):
        assert f"'{idx}'" in q
