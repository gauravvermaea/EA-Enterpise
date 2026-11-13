"""R2.52, the first step (owner, 12 Nov 2026: measure, then "we will discuss and implement"): `eax databases speed`
lists the code's text comparisons and times real queries of each kind on the database; it changes nothing."""

from __future__ import annotations

import inspect
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_the_code_scan_finds_the_comparisons(tmp_path):
    from eax import textspeed as ts
    (tmp_path / "a.py").write_text('q = "SELECT 1 FROM core.entities e WHERE lower(e.name) = lower(:n) AND e.display_id ILIKE :q"\n'
                                   'r = "WHERE m.code = :c AND m.code = :d"\n')
    got = {(c["column"], c["kind"]): c["places"] for c in ts.scan(tmp_path)}
    assert got == {("name", "lower"): 1, ("display_id", "contains"): 1, ("code", "exact"): 2}
    assert {c["column"] for c in ts.scan()} >= {"name", "code", "username"}          # the real code


def test_measuring_reads_only_and_reports_options():
    from eax import textspeed as ts
    src = inspect.getsource(ts.measure)
    assert "EXPLAIN (ANALYZE" in src and "SELECT 1 FROM" in src
    assert not any(w in src.upper() for w in ("INSERT ", "UPDATE ", "DELETE ", "CREATE INDEX"))
    text = ts.report([{"column": "name", "kind": "lower", "places": 3, "files": {"x.py": 3}}],
                     [{"table": "core.t", "column": "name", "kind": "contains", "rows": 10, "ms": 1.5, "uses_index": False,
                       "plan": "Seq Scan", "indexes": [], "used_for": "Find"}])
    assert "NO (Seq Scan)" in text and "trigram index" in text and "nothing changed" in text
    assert '"speed"' in (REPO / "services/api/eax/databases.py").read_text()
    assert "$ {eax} databases speed" in (REPO / "eaxcli/help.txt").read_text()
