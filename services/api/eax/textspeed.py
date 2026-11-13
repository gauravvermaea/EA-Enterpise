"""How fast the database compares text (R2.52, first step; owner, 12 Nov 2026: "db indexing speed, if we do where on
strings ..."; "we will discuss and implement"): measure before choosing. Two parts:

  1. the code: every comparison of a text column in the SQL of eax/ (exact, case-insensitive, contains), how many
     places use each, and where
  2. the database: for the comparisons that matter (names, display ids, attribute values, users, codes), the rows in
     the table, the indexes that could serve them, and the time and plan of a real query of each kind (EXPLAIN
     ANALYZE, read only)

Then each kind is discussed with the owner (B-tree or hash for exact, lower() for case-insensitive, pg_trgm for
contains, tsvector for words in long text, a hash column for very long values; R2.52's options) and indexes added,
measured again. Nothing is changed here.

  python -m eax.textspeed            (eax databases speed)
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy import text

HERE = Path(__file__).resolve().parent
_CMP = re.compile(r"(lower\()?\b([a-z]{1,4})\.([a-z_]+)\)?\s*(=|ILIKE|LIKE|~\*)\s*", re.I)
TEXTY = {"name", "display_id", "code", "value_text", "username", "title", "old_name", "old_display_id", "label", "path",
         "tag", "kind_code", "status_code", "ident", "owner", "description"}

# the comparisons measured on the database: table, column, kind, what uses it
CANDIDATES = [
    ("core.entities", "name", "exact", "finding an entity by name (imports, MCP, links)"),
    ("core.entities", "name", "lower", "case-insensitive name matches (dedupe, imports)"),
    ("core.entities", "name", "contains", "Find and search"),
    ("core.entities", "display_id", "contains", "Find by display id"),
    ("core.entity_aliases", "old_name", "lower", "old names after a merge (finding by an old name)"),
    ("core.attribute_values", "value_text", "exact", "attribute values (filters, matching)"),
    ("core.attribute_values", "value_text", "contains", "searching attribute values"),
    ("core.models", "name", "exact", "a model by name"),
    ("core.known_users", "username", "lower", "a person by user name"),
    ("core.entity_types", "code", "exact", "an entity type by code"),
]


# as the application asks: within one model (the largest) and leaving out what was deleted, so the indexes made for
# those queries can be used
SCOPE = {"core.entities": " AND model_id = :big AND NOT is_deleted", "core.attribute_values": " AND NOT is_deleted",
         "core.models": " AND NOT is_deleted", "core.entity_types": " AND model_id = :big"}


def scan(root: Path = HERE) -> list[dict]:
    """Every comparison of a text-like column in eax/'s SQL: column, kind, how many places, the files."""
    found: dict[tuple[str, str], dict] = {}
    for f in sorted(root.rglob("*.py")):
        if "tests" in f.parts or f.name == "textspeed.py":
            continue
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            for m in _CMP.finditer(line):
                col = m.group(3).lower()
                if col not in TEXTY:
                    continue
                kind = "lower" if m.group(1) else "contains" if m.group(4).upper() in ("ILIKE", "LIKE", "~*") else "exact"
                d = found.setdefault((col, kind), {"column": col, "kind": kind, "places": 0, "files": defaultdict(int)})
                d["places"] += 1
                d["files"][str(f.relative_to(root))] += 1
    out = []
    for d in sorted(found.values(), key=lambda x: -x["places"]):
        out.append({**d, "files": dict(sorted(d["files"].items(), key=lambda kv: -kv[1])[:6])})
    return out


def _indexes(conn, table: str, column: str) -> list[str]:
    rows = conn.execute(text("""SELECT i.relname, pg_get_indexdef(i.oid) FROM pg_index x JOIN pg_class i ON i.oid = x.indexrelid
                                 WHERE x.indrelid = to_regclass(:t)"""), {"t": table}).all()
    return [f"{n}: {d.split(' USING ', 1)[-1]}" for n, d in rows if re.search(rf"\b{column}\b", d)]


def _sample(conn, table: str, column: str) -> str | None:
    return conn.execute(text(f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL AND length({column}) > 3 "   # noqa: S608 - fixed names
                             f"ORDER BY {column} OFFSET (SELECT count(*) / 2 FROM {table}) LIMIT 1")).scalar() or \
        conn.execute(text(f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL LIMIT 1")).scalar()  # noqa: S608


def measure(conn) -> list[dict]:
    """Each candidate: rows, indexes on the column, a real query's time and whether it used an index."""
    out = []
    conn.execute(text("SELECT set_config('eax.rls_bypass', 'on', true)"))
    big = conn.execute(text("SELECT model_id FROM core.entities GROUP BY 1 ORDER BY count(*) DESC LIMIT 1")).scalar() or 0
    for table, column, kind, used in CANDIDATES:
        row = {"table": table, "column": column, "kind": kind, "used_for": used}
        try:
            row["rows"] = int(conn.execute(text(f"SELECT count(*) FROM {table}")).scalar() or 0)   # noqa: S608
            row["indexes"] = _indexes(conn, table, column)
            v = _sample(conn, table, column)
            if v is None:
                row["note"] = "no values to try"
                out.append(row)
                continue
            where = {"exact": f"{column} = :v", "lower": f"lower({column}) = lower(:v)",
                     "contains": f"{column} ILIKE '%' || :v || '%'"}[kind]
            probe = str(v)[:40] if kind != "contains" else str(v)[1:6]
            scope = SCOPE.get(table, "")
            for _ in range(2):                       # the second run: the data in memory, as most queries find it
                plan = conn.execute(text(f"EXPLAIN (ANALYZE, FORMAT JSON) SELECT 1 FROM {table} WHERE {where}{scope}"),  # noqa: S608
                                    {"v": probe, **({"big": big} if ":big" in scope else {})}).scalar()
            top = (plan[0] if isinstance(plan, list) else plan)
            node, nodes = top["Plan"], []
            stack = [node]
            while stack:
                n = stack.pop()
                nodes.append(n["Node Type"])
                stack += n.get("Plans") or []
            row.update(ms=round(top.get("Execution Time", 0), 2), plan=" > ".join(nodes),
                       uses_index=any("Index" in n or "Bitmap" in n for n in nodes))
        except Exception as exc:  # noqa: BLE001 - one comparison that cannot be measured is said, the rest go on
            row["note"] = str(exc).splitlines()[0][:160]
        out.append(row)
    return out


OPTIONS = {"exact": "B-tree index on the column (or hash for very long values)",
           "lower": "B-tree index on lower(column)", "contains": "trigram index (pg_trgm, GIN)"}


def report(code: list[dict], db: list[dict]) -> str:
    lines = ["Text comparisons (R2.52): measured, nothing changed. Discuss each kind, then add indexes and measure again.", "",
             "In the database:", f"  {'table.column':<34}{'kind':<10}{'rows':>8}{'ms':>9}  index used?  indexes on it / what uses it"]
    for r in db:
        if r.get("note"):
            lines.append(f"  {r['table'] + '.' + r['column']:<34}{r['kind']:<10}  {r['note']}")
            continue
        lines.append(f"  {r['table'] + '.' + r['column']:<34}{r['kind']:<10}{r['rows']:>8}{r['ms']:>9}  "
                     f"{'yes' if r['uses_index'] else 'NO (' + r['plan'] + ')':<12} {'; '.join(r['indexes']) or 'none'}")
        if not r["uses_index"]:
            lines.append(f"  {'':<34}{'':<10}  option: {OPTIONS[r['kind']]}  ({r['used_for']})")
    lines += ["", "In the code (eax/): each text column compared, by kind, and where most:"]
    for c in code[:25]:
        lines.append(f"  {c['column']:<16}{c['kind']:<10}{c['places']:>4} place(s)  " + ", ".join(f"{f} ({n})" for f, n in c["files"].items()))
    return "\n".join(lines)


def main() -> int:
    from .db import get_engine
    with get_engine().begin() as conn:
        db = measure(conn)
    print(report(scan(), db))
    return 0


if __name__ == "__main__":
    sys.exit(main())
