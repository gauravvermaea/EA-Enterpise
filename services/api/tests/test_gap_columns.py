"""Gap and common analyses read their own tables' columns (owner, 12 Nov 2026: making a gap analysis said "column
"domain" does not exist"). core.gap_items and core.common_items keep the domain in a column named layer; only the
reporting views (rpt.*) call it domain."""

import re
from pathlib import Path

EAX = Path(__file__).resolve().parents[1] / "eax"


def test_no_query_reads_a_domain_column_from_the_analysis_tables():
    bad = []
    for f in ("gaps.py", "commons.py"):
        src = (EAX / f).read_text(encoding="utf-8")
        for sql in re.findall(r'"""(.*?)"""', src, re.S):
            # every "domain" left once "AS domain" (the answer's own name) is taken out is a column read by that name
            if re.search(r"FROM core\.(gap|common)_items", sql) and re.search(r"\bdomain\b", re.sub(r"\bAS domain\b", "", sql)):
                bad.append(f"{f}: {' '.join(sql.split())[:120]}")
    assert not bad, bad
    assert "layer AS domain" in (EAX / "gaps.py").read_text(encoding="utf-8")
    assert "layer AS domain" in (EAX / "commons.py").read_text(encoding="utf-8")
