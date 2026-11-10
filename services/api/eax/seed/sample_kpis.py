"""KPI trends on the demo estate (owner, 10 Nov 2026, phase 24, D365, D436): laptop only, made once (a demo estate with
monthly snapshots already is left alone). Every name is invented.

Between them they show every state a KPI can be in:

* the standard KPIs with a year of monthly snapshots (the estate growing, orphans and end-of-life technology falling, the
  quality score rising), plus the snapshots its two tags kept (Baseline 2026 and Target 2028, taken by the tags themselves);
* the model's own KPIs: a count with a filter (Applications to eliminate) and a sum with a filter (Annual cost of SaaS
  applications), each with the same year of history;
* an own KPI added since the last snapshot (Capabilities without an owner): its value now only, no trend yet;
* an own KPI no longer kept (Applications on premises): its trend so far stays, marked as no longer kept;
* the other models: no snapshots yet (the first monthly one is taken by the job runner within the hour).

The history is made from today's values, stepped back month by month: the numbers are illustrative.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import text

from .. import kpis
from .demo_estate import DEMO_NAME

MONTHS = 12
OWN = [
    {"name": "Applications to eliminate", "kind": "count", "entity_type_code": "ApplicationComponent",
     "filter_attribute": "TimeClassification", "filter_op": "equals", "filter_value": "Eliminate",
     "description": "Applications classified Eliminate under TIME: the retirement backlog."},
    {"name": "Annual cost of SaaS applications", "kind": "sum", "entity_type_code": "ApplicationComponent",
     "attribute_code": "AnnualCost", "filter_attribute": "Hosting", "filter_op": "equals", "filter_value": "SaaS", "unit": "USD",
     "description": "What the applications bought as a service cost a year."},
]
NEW = {"name": "Capabilities without an owner", "kind": "count", "entity_type_code": "Capability", "filter_attribute": "Owner",
       "filter_op": "empty", "description": "Capabilities nobody owns yet (added this month: no trend yet)."}
RETIRED = {"name": "Applications on premises", "kind": "count", "entity_type_code": "ApplicationComponent",
           "filter_attribute": "Hosting", "filter_op": "equals", "filter_value": "On-premises",
           "description": "Kept until the cloud move was agreed; no longer kept."}
GROWING = {"entities", "entities_by_type", "applications_by_lifecycle", "total_cost"}


def _back(code: str, now: Decimal | None, step: int) -> Decimal | None:
    """The value `step` months ago (0 = this month), from today's."""
    if now is None:
        return None if code != "quality_score" else Decimal(55 + 1.5 * (MONTHS - 1 - step)).quantize(Decimal("0.01"))
    if code == "quality_score":
        return max(Decimal(0), (now - Decimal("1.6") * step)).quantize(Decimal("0.01"))
    if code == "orphans":
        return now + step
    if code in ("eol_technology", "eol_technology_soon"):
        return now + step // 4
    if code.startswith("own:") or code in GROWING or code == "applications_by_time":
        return (now * (Decimal(1) - Decimal("0.02") * step)).quantize(Decimal(1))
    return now


def run(conn) -> list[str]:
    """Makes the sample KPIs on the demo estate in this transaction (as the installer); [] when there is nothing to do."""
    m = conn.execute(text("SELECT id FROM core.models WHERE name = :n AND NOT is_deleted"), {"n": DEMO_NAME}).scalar()
    if not m:
        return []
    if conn.execute(text("SELECT 1 FROM core.kpi_definitions WHERE model_id = :m LIMIT 1"), {"m": m}).first():
        return []
    by = "user_model_admin"
    made = []
    for d in [*OWN, RETIRED]:
        g = conn.execute(text("""
            INSERT INTO core.kpi_definitions (model_id, name, kind, entity_type_code, attribute_code, filter_attribute, filter_op,
                                              filter_value, unit, description, created_by, modified_by, created_at)
            VALUES (:m, :name, :kind, :t, :a, :fa, :fo, :fv, :u, :d, :by, :by, now() - interval '13 months')
            RETURNING guid::text"""),
            {"m": m, "name": d["name"], "kind": d["kind"], "t": d["entity_type_code"], "a": d.get("attribute_code", ""),
             "fa": d.get("filter_attribute", ""), "fo": d.get("filter_op", ""), "fv": d.get("filter_value", ""),
             "u": d.get("unit", ""), "d": d.get("description", ""), "by": by}).scalar()
        made.append((d, g))
    now_rows = kpis.values_now(conn, m)
    have = {str(r["period"])[:10] for r in conn.execute(text(
        "SELECT period FROM core.kpi_snapshots WHERE model_id = :m AND reason = 'monthly'"), {"m": m}).mappings()}
    first = date.today().replace(day=1)
    taken = 0
    for step in range(MONTHS - 1, -1, -1):
        y, mo = first.year, first.month - step
        while mo <= 0:
            y, mo = y - 1, mo + 12
        period = date(y, mo, 1)
        if str(period) in have:
            continue
        rows = [{**r, "value": _back(r["kpi"], r["value"], step)} for r in now_rows]
        kpis.take(conn, m, "monthly", period=period, at=datetime.combine(period, time(1, 7), UTC) + timedelta(minutes=0),
                  rows=rows)
        taken += 1
    # added since the last snapshot: a value now, no trend yet
    conn.execute(text("""
        INSERT INTO core.kpi_definitions (model_id, name, kind, entity_type_code, filter_attribute, filter_op, description,
                                          created_by, modified_by)
        VALUES (:m, :name, 'count', :t, :fa, :fo, :d, :by, :by)"""),
        {"m": m, "name": NEW["name"], "t": NEW["entity_type_code"], "fa": NEW["filter_attribute"], "fo": NEW["filter_op"],
         "d": NEW["description"], "by": by})
    # no longer kept: its trend so far stays
    conn.execute(text("UPDATE core.kpi_definitions SET is_deleted = true, modified_at = now() - interval '2 months' "
                      "WHERE model_id = :m AND guid = CAST(:g AS uuid)"), {"m": m, "g": made[-1][1]})
    conn.execute(text("""DELETE FROM core.kpi_values v USING core.kpi_snapshots s
                          WHERE v.snapshot_id = s.id AND s.model_id = :m AND v.kpi = :k AND s.period > :p"""),
                 {"m": m, "k": f"own:{made[-1][1]}", "p": first - timedelta(days=60)})
    return [f"KPI trends on the demo estate: {taken} monthly snapshots and {len(OWN) + 2} own KPIs"] if taken else []
